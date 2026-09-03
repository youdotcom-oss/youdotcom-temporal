from __future__ import annotations

import asyncio

from hello_background_research_workflow import HelloBackgroundResearch
from hello_search_workflow import HelloSearch
from temporalio.client import Client
from temporalio.worker import Worker

from youdotcom_temporal import YouPlugin


async def main() -> None:
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue="you-search",
        # Register both hello workflows so the same worker can serve
        # run_workflow.py (sync search) and run_background_research_workflow.py
        # (research_helpers.research_and_wait_async — see its docstring).
        workflows=[HelloSearch, HelloBackgroundResearch],
        plugins=[YouPlugin()],
    )
    print("Worker started on task queue: you-search (HelloSearch + HelloBackgroundResearch)")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
