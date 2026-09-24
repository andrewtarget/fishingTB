"""Single-forum thread list and post detail via aiotieba."""

from __future__ import annotations

from aiotieba.enums import ThreadSortType

from fishingtb.models import PostItem, ThreadItem
from fishingtb.session import TiebaSession

DEFAULT_THREAD_RN = 50
DEFAULT_POST_RN = 40


def _author_name(obj) -> str:
    user = getattr(obj, "user", None) or getattr(obj, "author", None)
    if user is None:
        return ""
    return (
        getattr(user, "nick_name_new", None)
        or getattr(user, "nick_name", None)
        or getattr(user, "user_name", None)
        or str(getattr(user, "user_id", "") or "")
    )


def _thread_to_item(thread, fname: str) -> ThreadItem:
    title = getattr(thread, "title", "") or ""
    text = getattr(thread, "text", "") or ""
    forum = fname
    for attr in ("fname", "forum_name"):
        val = getattr(thread, attr, None)
        if isinstance(val, str) and val.strip():
            forum = val.strip()
            break
    nested = getattr(thread, "forum", None)
    if nested is not None:
        n = getattr(nested, "fname", None) or getattr(nested, "name", None)
        if n:
            forum = str(n)
    return ThreadItem(
        tid=int(getattr(thread, "tid", 0) or 0),
        title=title,
        text=text,
        reply_num=int(getattr(thread, "reply_num", 0) or 0),
        view_num=int(getattr(thread, "view_num", 0) or 0),
        last_time=int(getattr(thread, "last_time", 0) or 0),
        author=_author_name(thread),
        fname=forum or fname,
    )


def _extract_images(post) -> list[str]:
    contents = getattr(post, "contents", None)
    if contents is None:
        return []
    urls: list[str] = []
    imgs = getattr(contents, "imgs", None) or []
    for im in imgs:
        url = (
            getattr(im, "src", None)
            or getattr(im, "big_src", None)
            or getattr(im, "origin_src", None)
            or ""
        )
        if url:
            urls.append(str(url))
    return urls


def _extract_post_text(post) -> str:
    """Build plain text from post; avoid empty body when fragments exist."""
    text = (getattr(post, "text", None) or "").strip()
    if text:
        return text

    contents = getattr(post, "contents", None)
    if contents is None:
        return ""

    ctext = (getattr(contents, "text", None) or "").strip()
    if ctext:
        return ctext

    parts: list[str] = []
    for frag in getattr(contents, "texts", None) or []:
        t = (getattr(frag, "text", None) or "").strip()
        if t:
            parts.append(t)
    for frag in getattr(contents, "objs", None) or []:
        name = type(frag).__name__.lower()
        if "text" in name:
            t = (getattr(frag, "text", None) or "").strip()
            if t:
                parts.append(t)
        elif "link" in name:
            t = (getattr(frag, "text", None) or getattr(frag, "url", None) or "").strip()
            if t:
                parts.append(t)
        elif "at" in name:
            t = (getattr(frag, "text", None) or "").strip()
            if t:
                parts.append(t)
    return "\n".join(parts).strip()


def _post_to_item(post) -> PostItem:
    text = _extract_post_text(post)
    comments: list[str] = []
    for c in getattr(post, "comments", None) or []:
        ctext = _extract_post_text(c) if hasattr(c, "contents") else (
            (getattr(c, "text", "") or "").strip()
        )
        if ctext:
            author = _author_name(c)
            comments.append(f"  └ {author}: {ctext[:200]}")
    urls = _extract_images(post)
    return PostItem(
        pid=int(getattr(post, "pid", 0) or 0),
        floor=int(getattr(post, "floor", 0) or 0),
        author=_author_name(post),
        text=text,
        img_count=len(urls),
        image_urls=urls,
        comments=comments,
    )


async def get_forum_threads(
    session: TiebaSession,
    fname: str,
    *,
    pn: int = 1,
    rn: int = DEFAULT_THREAD_RN,
    sort: ThreadSortType = ThreadSortType.HOT,
) -> tuple[list[ThreadItem], bool]:
    """Fetch one page of forum threads. Returns (items, has_more)."""
    threads = await session.client.get_threads(fname, pn=pn, rn=rn, sort=sort)
    err = getattr(threads, "err", None)
    if err is not None:
        raise RuntimeError(f"Failed to load forum '{fname}': {err}")

    items = [_thread_to_item(t, fname) for t in threads if getattr(t, "tid", 0)]
    has_more = len(items) >= min(rn, 20)
    page = getattr(threads, "page", None)
    if page is not None:
        has_more = bool(getattr(page, "has_more", has_more))
    return items, has_more


async def get_thread_posts(
    session: TiebaSession,
    tid: int,
    *,
    pn: int = 1,
    rn: int = DEFAULT_POST_RN,
) -> tuple[list[PostItem], bool, str]:
    """Fetch one page of posts. Returns (items, has_more, thread_title)."""
    posts = await session.client.get_posts(
        tid,
        pn=pn,
        rn=rn,
        with_comments=True,
        comment_rn=5,
    )
    err = getattr(posts, "err", None)
    if err is not None:
        raise RuntimeError(f"Failed to load thread {tid}: {err}")

    title = ""
    thread = getattr(posts, "thread", None)
    if thread is not None:
        title = getattr(thread, "title", "") or getattr(thread, "text", "") or ""

    items = [_post_to_item(p) for p in posts]
    # Ensure floor 1 shows title when body is thin
    if items and title:
        first = items[0]
        if first.floor <= 1 and title not in first.text:
            first.text = f"{title}\n\n{first.text}".strip() if first.text else title

    has_more = len(items) >= min(rn, 20)
    page = getattr(posts, "page", None)
    if page is not None:
        has_more = bool(getattr(page, "has_more", has_more))
    return items, has_more, title
