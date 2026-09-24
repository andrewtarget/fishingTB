"""Shared TUI widgets."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input, Static


class StatusBar(Static):
    """Bottom status / hint line."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def set_status(self, text: str) -> None:
        self.update(text)


class CamouflageInput(Input):
    """Input that yields the boss key to the app instead of inserting `."""

    BINDINGS = [
        Binding("grave_accent", "app.boss", "Boss", priority=True, show=False),
    ]


class ToolBar(Horizontal):
    """Clickable text-link action bar."""

    DEFAULT_CSS = """
    ToolBar {
        height: 1;
        align: left middle;
        padding: 0 1;
        background: transparent;
    }
    ToolBar Button {
        margin-right: 1;
        min-width: 0;
        height: 1;
    }
    """
