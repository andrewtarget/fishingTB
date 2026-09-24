"""Followed forums and aggregated follow feed."""

from __future__ import annotations

import asyncio

from aiotieba.enums import ThreadSortType

from fishingtb.feeds.forum import get_forum_threads
from fishingtb.models import ForumItem, ThreadItem
from fishingtb.session import TiebaSession


def _forum_to_item(forum) -> ForumItem:
    name = (
        getattr(forum, "fname", None)
        or getattr(forum, "name", None)
        or getattr(forum, "forum_name", None)
        or ""
    )
    fid = int(getattr(forum, "fid", 0) or getattr(forum, "forum_id", 0) or 0)
    level = int(getattr(forum, "level", 0) or getattr(forum, "user_level", 0) or 0)
    return ForumItem(fname=str(name), fid=fid, level=level)


async def get_followed_forums(
    session: TiebaSession,
    *,
    max_pages: int = 5,
) -> list[ForumItem]:
    """
    Load current user's followed forums.
    Prefer get_self_follow_forums (needs STOKEN); fallback to get_follow_forums(user_id).
    """
    client = session.client
    items: list[ForumItem] = []
    seen: set[str] = set()

    # Path 1: self follow list (STOKEN)
    try:
        for pn in range(1, max_pages + 1):
            forums = await client.get_self_follow_forums(pn=pn, rn=200)
            err = getattr(forums, "err", None)
            if err is not None:
                raise RuntimeError(str(err))
            batch = list(forums) if forums else []
            if not batch:
                break
            for f in batch:
                item = _forum_to_item(f)
                if item.fname and item.fname not in seen:
                    seen.add(item.fname)
                    items.append(item)
            if not getattr(forums, "has_more", False):
                break
        if items:
            return items
    except Exception:
        items.clear()
        seen.clear()

    # Path 2: follow forums by user_id (BDUSS only)
    user = await client.get_self_info()
    uid = getattr(user, "user_id", 0) or 0
    if not uid:
        raise RuntimeError("Cannot resolve user_id for follow list")

    for pn in range(1, max_pages + 1):
        forums = await client.get_follow_forums(uid, pn=pn, rn=50)
        err = getattr(forums, "err", None)
        if err is not None:
            raise RuntimeError(f"Failed to load follows: {err}")
        batch = list(forums) if forums else []
        if not batch:
            break
        for f in batch:
            item = _forum_to_item(f)
            if item.fname and item.fname not in seen:
                seen.add(item.fname)
                items.append(item)
        if not getattr(forums, "has_more", True) or len(batch) < 50:
            break

    return items


async def get_follow_feed(
    session: TiebaSession,
    *,
    forum_limit: int = 20,
    per_forum: int = 8,
    forums: list[ForumItem] | None = None,
) -> list[ThreadItem]:
    """
    Aggregate recent threads from followed forums (reply-time order).
    """
    if forums is None:
        forums = await get_followed_forums(session)
    if not forums:
        return []

    selected = forums[:forum_limit]

    async def _one(fname: str) -> list[ThreadItem]:
        try:
            items, _ = await get_forum_threads(
                session,
                fname,
                pn=1,
                rn=per_forum,
                sort=ThreadSortType.REPLY,
            )
            return items
        except Exception:
            return []

    results = await asyncio.gather(*[_one(f.fname) for f in selected])
    merged: list[ThreadItem] = []
    for batch in results:
        merged.extend(batch)
    merged.sort(key=lambda t: t.last_time, reverse=True)
    return merged
