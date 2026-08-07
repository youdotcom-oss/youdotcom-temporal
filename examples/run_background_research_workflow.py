from __future__ import annotations

import asyncio
import uuid

from hello_background_research_workflow import HelloBackgroundResearch
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy


async def main() -> None:
    client = await Client.connect("localhost:7233")
    workflow_id = f"hello-background-research-{uuid.uuid4().hex[:8]}"
    result = await client.execute_workflow(
        HelloBackgroundResearch.run,
        "Compare quantum computing approaches for breaking RSA-2048",
        id=workflow_id,
        task_queue="you-search",
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
