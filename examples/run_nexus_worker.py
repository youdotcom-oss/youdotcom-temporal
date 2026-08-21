"""Handler-side Worker for the YouDotCom Nexus Service.

This Worker hosts the Nexus Service handler, the backing Workflows, and the
You.com Activities (registered by ``YouPlugin``). Run it in the *handler*
Namespace, then point a Nexus Endpoint at this Worker's Task Queue so callers in
other Namespaces can reach the Operations.

``YouPlugin`` registers the Activities the backing Workflows call, so the
handler Worker needs it. Operations return the You.com SDK's pydantic response
models, so the Client needs ``pydantic_data_converter`` -- on the caller side
too.

Setup (two terminals, local dev server with Nexus enabled)::

    # 1. Start the Temporal dev server (Nexus is enabled by default).
    temporal server start-dev

    # 2. Create a handler Namespace and a Nexus Endpoint targeting this Worker.
    temporal operator namespace create --namespace you-handler
    temporal operator nexus endpoint create \
        --name you-nexus-endpoint \
        --target-namespace you-handler \
        --target-task-queue you-nexus

    # 3. Run this handler Worker (terminal 2).
    YDC_API_KEY=your-key python examples/run_nexus_worker.py

A caller Workflow in a different Namespace invokes an Operation through the
Endpoint. Callers import from ``youdotcom_temporal.contract``, which carries the
types and none of the handler. No plugin and no sandbox escape are needed, and
the caller's Client needs the same pydantic converter this Worker uses::

    from datetime import timedelta
    from temporalio import workflow

    from youdotcom_temporal.contract import (
        SearchRequest,
        SearchResponse,
        YouDotComService,
    )
    from youdotcom_temporal.models import SearchInput

    NEXUS_ENDPOINT = "you-nexus-endpoint"

    @workflow.defn
    class CallerWorkflow:
        @workflow.run
        async def run(self, query: str) -> SearchResponse:
            nexus_client = workflow.create_nexus_client(
                service=YouDotComService, endpoint=NEXUS_ENDPOINT
            )
            # Exceeds the handler-side worst case for search
            # (_SEARCH_STC 120s x 3 attempts).
            out = await nexus_client.execute_operation(
                YouDotComService.search,
                SearchRequest(
                    input=SearchInput(query=query, count=10),
                    # Optional: a retried StartOperation attaches to the run
                    # already in flight instead of paying for a second call.
                    idempotency_key=f"search:{query}",
                ),
                schedule_to_close_timeout=timedelta(minutes=10),
            )
            out.results.web[0].title   # typed all the way down
            return out

See the Temporal Python Nexus quickstart for the full caller-side setup:
https://docs.temporal.io/develop/python/nexus/quickstart
"""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from youdotcom_temporal import YouPlugin
from youdotcom_temporal.nexus import you_nexus_service_handler
from youdotcom_temporal.workflows import you_nexus_workflows

HANDLER_NAMESPACE = "you-handler"
TASK_QUEUE = "you-nexus"


async def main() -> None:
    client = await Client.connect(
        "localhost:7233",
        namespace=HANDLER_NAMESPACE,
        data_converter=pydantic_data_converter,
    )
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=you_nexus_workflows(),
        nexus_service_handlers=[you_nexus_service_handler()],
        plugins=[YouPlugin()],
    )
    print(
        f"Handler Worker started in namespace {HANDLER_NAMESPACE!r} "
        f"on task queue {TASK_QUEUE!r} (YouDotCom Nexus Service)"
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
