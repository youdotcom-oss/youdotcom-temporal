from __future__ import annotations

import asyncio

from hello_search_workflow import HelloSearch
from temporalio.client import Client


async def main() -> None:
    client = await Client.connect("localhost:7233")
    result = await client.execute_workflow(
        HelloSearch.run,
        "what is the capital of france",
        id="hello-search-workflow",
        task_queue="you-search",
    )
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
