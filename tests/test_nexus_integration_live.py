"""Nexus round trip against the real You.com API.

``test_nexus_integration`` proves the Nexus wiring with mocked responses. That
leaves one thing unproven: real API payloads crossing the Nexus boundary. A
mock returns a two-key dict; a real ``search`` response is a large nested
document that has to survive ``model_dump(mode="json")``, the Temporal payload
converter, the Operation completion callback, and deserialization on the caller
side.

Only the fast Operations run here. ``research``, ``finance_research`` and
``research_background`` take minutes to hours and cost real money per call, so
they stay mocked; the Activity layer already covers them in
``test_integration``.

Run with: uv run pytest -m integration
"""

from __future__ import annotations

import json
import os
import shutil
import uuid

import pytest
from _nexus_caller_workflows import (
    CallAnswer,
    CallContents,
    CallContentsMany,
    CallSearch,
    caller_workflows,
)
from temporalio.worker import Worker
from test_nexus_integration import (  # reuse the topology helpers
    CALLER_QUEUE,
    HANDLER_QUEUE,
    _create_endpoint,
    _start_server,
)

from youdotcom_temporal import YouPlugin
from youdotcom_temporal.nexus import you_nexus_service_handler
from youdotcom_temporal.workflows import you_nexus_workflows

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("YDC_API_KEY"),
        reason="hits the real You.com API; requires YDC_API_KEY",
    ),
    pytest.mark.skipif(
        shutil.which("temporal") is None,
        reason="needs the local Temporal dev server CLI",
    ),
]

# Temporal refuses payloads over 2 MiB and warns above 512 KiB. Measured worst
# cases: search count=100 ~107 KB, contents with 5 large pages ~281 KB.
_WARN_BYTES = 512 * 1024
_LIMIT_BYTES = 2 * 1024 * 1024


@pytest.fixture
async def live_nexus_env():
    """Real Endpoint and Workers, with no mocking of the You.com client."""
    env = await _start_server()
    async with env:
        await _create_endpoint(env.client, env.client.namespace, HANDLER_QUEUE)
        async with Worker(
            env.client,
            task_queue=HANDLER_QUEUE,
            workflows=you_nexus_workflows(),
            nexus_service_handlers=[you_nexus_service_handler()],
            plugins=[YouPlugin()],
        ):
            async with Worker(
                env.client, task_queue=CALLER_QUEUE, workflows=caller_workflows()
            ):
                yield env


@pytest.mark.parametrize(
    "caller,arg,probe",
    [
        (CallSearch, "temporal workflow engine", "search"),
        (CallAnswer, "what is a Temporal workflow?", "answer"),
        (CallContents, "https://temporal.io", "contents"),
    ],
    ids=["search", "answer", "contents"],
)
async def test_live_operation_round_trips(live_nexus_env, caller, arg, probe):
    """A real You.com response survives the whole Nexus path to the caller."""
    result = await live_nexus_env.client.execute_workflow(
        caller.run,
        arg,
        id=f"nexus-live-{probe}-{uuid.uuid4()}",
        task_queue=CALLER_QUEUE,
    )

    # The payload made it across intact as typed models, and is genuinely
    # JSON-serializable -- anything model_dump could not encode would fail here.
    # `contents` is the one Operation with a dataclass envelope around SDK
    # models, so it serializes element by element.
    if probe == "contents":
        # The elements are the contents endpoint's own model, so every field
        # it returns must survive. Validating against the wrong SDK model
        # (the search extraction shape) silently dropped url/title/metadata.
        assert result.results[0].url == arg
        assert result.results[0].title
        payload = [c.model_dump(mode="json") for c in result.results]
    else:
        assert hasattr(result, "model_dump"), f"{probe} did not come back typed"
        payload = result.model_dump(mode="json")
    encoded = json.dumps(payload).encode()
    assert len(encoded) > 200, f"{probe} returned a suspiciously small payload"
    assert len(encoded) < _LIMIT_BYTES, (
        f"{probe} payload is {len(encoded)} bytes, over Temporal's {_LIMIT_BYTES}"
    )
    if len(encoded) > _WARN_BYTES:
        pytest.fail(
            f"{probe} payload {len(encoded)} bytes exceeds Temporal's "
            f"{_WARN_BYTES} warning threshold; callers should expect blob warnings"
        )


async def test_live_contents_at_fan_out_stays_under_the_payload_limit(live_nexus_env):
    """`contents` at fan-out produces our largest payload; guard the ceiling.

    The result carries full page text per URL, so this is the Operation most
    likely to grow past Temporal's blob limits. Five content-heavy pages is a
    realistic upper-middle case for the 10-URL maximum.
    """
    urls = [
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://en.wikipedia.org/wiki/Distributed_computing",
        "https://en.wikipedia.org/wiki/Database",
        "https://en.wikipedia.org/wiki/Operating_system",
        "https://en.wikipedia.org/wiki/Computer_network",
    ]
    result = await live_nexus_env.client.execute_workflow(
        CallContentsMany.run,
        urls,
        id=f"nexus-live-contents-fanout-{uuid.uuid4()}",
        task_queue=CALLER_QUEUE,
    )

    assert len(result.results) == len(urls)
    encoded = json.dumps(
        [c.model_dump(mode="json") for c in result.results]
    ).encode()
    assert len(encoded) < _LIMIT_BYTES, (
        f"contents payload {len(encoded):,} bytes exceeds Temporal's "
        f"{_LIMIT_BYTES:,}; the Operation cannot return this much"
    )
    print(
        f"\ncontents x{len(urls)}: {len(encoded):,} bytes "
        f"({100 * len(encoded) / _LIMIT_BYTES:.1f}% of the 2 MiB limit)"
    )
