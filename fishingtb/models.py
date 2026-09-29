"""Lightweight view models for TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


def format_event_time(ts: int, *, now: datetime | None = None) -> str:
    """Human-readable post/comment time from 10-digit Unix seconds."""
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(ts)
    except (OSError, OverflowError, ValueError):
        return ""
    ref = now or datetime.now()
    clock = dt.strftime("%H:%M")
    if dt.date() == ref.date():
        return f"今天 {clock}"
    if dt.date() == ref.date() - timedelta(days=1):
        return f"昨天 {clock}"
    if dt.year == ref.year:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M")


@dataclass
class ForumItem:
    fname: str
    fid: int = 0
    level: int = 0

    @property
    def label(self) -> str:
        if self.level:
            return f"{self.fname}吧  Lv.{self.level}"
        return f"{self.fname}吧"


@dataclass
class ThreadItem:
    tid: int
    title: str
    text: str
    reply_num: int
    view_num: int
    last_time: int
    author: str
    fname: str = ""

    @property
    def last_time_str(self) -> str:
        if not self.last_time:
            return ""
        try:
            return datetime.fromtimestamp(self.last_time).strftime("%m-%d %H:%M")
        except (OSError, OverflowError, ValueError):
            return ""

    @property
    def display_title(self) -> str:
        return self.title.strip() or (
            self.text[:40] + ("…" if len(self.text) > 40 else "")
        )

    @property
    def list_label(self) -> str:
        title = self.display_title.replace("\n", " ")
        if len(title) > 42:
            title = title[:41] + "…"
        forum = f"[{self.fname}] " if self.fname else ""
        return (
            f"{forum}{title}  ·{self.reply_num}回复  "
            f"{self.last_time_str}  {self.author}"
        )


@dataclass
class CommentItem:
    author: str
    text: str
    create_time: int = 0
    author_tags: list[str] = field(default_factory=list)

    @property
    def author_line(self) -> str:
        line = self.author
        if self.author_tags:
            line = f"{line} · {' · '.join(self.author_tags)}"
        return line

    @property
    def time_str(self) -> str:
        return format_event_time(self.create_time)


@dataclass
class PostItem:
    pid: int
    floor: int
    author: str
    text: str
    img_count: int = 0
    image_urls: list[str] = field(default_factory=list)
    comments: list[CommentItem] = field(default_factory=list)
    author_tags: list[str] = field(default_factory=list)
    create_time: int = 0

    @property
    def meta_main(self) -> str:
        head = f"#{self.floor} · {self.author}"
        if not self.author_tags:
            return head
        return f"{head} · {' · '.join(self.author_tags)}"

    @property
    def meta_line(self) -> str:
        """Plain meta without time (for tests and simple callers)."""
        return self.meta_main

    @property
    def time_str(self) -> str:
        return format_event_time(self.create_time)

    @property
    def body(self) -> str:
        parts: list[str] = []
        if self.text.strip():
            parts.append(self.text.strip())
        if self.img_count and not self.image_urls:
            parts.append(f"[图片 x{self.img_count}]")
        return "\n".join(parts)
