"""Lightweight view models for TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
class PostItem:
    pid: int
    floor: int
    author: str
    text: str
    img_count: int = 0
    image_urls: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        parts: list[str] = []
        if self.text.strip():
            parts.append(self.text.strip())
        if self.img_count and not self.image_urls:
            parts.append(f"[图片 x{self.img_count}]")
        return "\n".join(parts)
