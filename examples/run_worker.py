from __future__ import annotations

import asyncio

from hello_search_workflow import HelloSearch
from temporalio.client import Client
from temporalio.worker import Worker

from youdotcom_temporal import YouPlugin


async def main() -> None:
    client = await Client.connect("localhost:7233", plugins=[YouPlugin()])
    worker = Worker(
        client,
        task_queue="you-search",
        workflows=[HelloSearch],
        plugins=[YouPlugin()],
    )
    print("Worker started on task queue: you-search")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
