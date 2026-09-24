"""Live API smoke: guest get_threads (no BDUSS required for public forums)."""

from __future__ import annotations

import asyncio

import aiotieba
from aiotieba.enums import ThreadSortType

from fishingtb.feeds.forum import get_forum_threads
from fishingtb.session import TiebaSession


async def main() -> None:
    # Guest client — may work for public forum listing
    async with aiotieba.Client() as client:
        threads = await client.get_threads("python", pn=1, rn=5, sort=ThreadSortType.HOT)
        print("guest threads", len(threads))
        if threads:
            t = threads[0]
            print("sample", getattr(t, "tid", None), getattr(t, "title", "")[:40])

    # Session wrapper without credentials should fail start
    session = TiebaSession()
    try:
        await session.start("")
        print("ERROR: empty start should fail")
    except ValueError as e:
        print("empty start ok:", e)


if __name__ == "__main__":
    asyncio.run(main())
