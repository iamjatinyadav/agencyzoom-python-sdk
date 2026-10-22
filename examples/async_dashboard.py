"""Fetch several independent resources concurrently with the async client."""

from __future__ import annotations

import asyncio

from agencyzoom import AsyncAgencyZoom


async def main() -> None:
    async with AsyncAgencyZoom() as client:
        sales, pipelines, open_tasks = await asyncio.gather(
            client.dashboard.sales_data(period="mtd"),
            client.pipelines.list_with_stages("lead"),
            client.tasks.search(status=0, page_size=1),
        )
        print("Sales data:", sales.model_dump(exclude_none=True))
        print("Pipelines:", [p.name for p in pipelines])
        print("Open tasks:", open_tasks.total_count)


if __name__ == "__main__":
    asyncio.run(main())
