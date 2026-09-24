"""Textual application: screens, session, boss key."""

from __future__ import annotations

from textual import events
from textual.app import App
from textual.binding import Binding

from fishingtb.config import has_bduss, load_config
from fishingtb.media.images import close_image_client
from fishingtb.session import TiebaSession
from fishingtb.ui.screens.boss import BossScreen
from fishingtb.ui.screens.forum import ForumScreen
from fishingtb.ui.screens.login import LoginScreen
from fishingtb.ui.screens.setup import SetupScreen
from fishingtb.ui.screens.thread_detail import ThreadDetailScreen
from fishingtb.ui.screens.thread_list import ThreadListScreen


class FishingApp(App[None]):
    TITLE = "npm run dev"
    CSS = """
    Screen {
        background: $background;
    }

    /* Quiet text-link buttons — no filled chrome */
    Button {
        background: transparent;
        border: none;
        height: 1;
        min-width: 0;
        width: auto;
        padding: 0 1;
        color: $text-muted;
        text-style: none;
    }
    Button:hover {
        background: transparent;
        border: none;
        color: #4ea1ff;
        text-style: underline;
    }
    Button:focus {
        background: transparent;
        border: none;
        color: #4ea1ff;
        text-style: underline;
    }
    Button.-active {
        background: transparent;
        border: none;
        color: #4ea1ff;
        text-style: underline;
    }
    Button.primary,
    Button.-primary {
        background: transparent;
        border: none;
        color: #4ea1ff;
    }
    Button.primary:hover,
    Button.-primary:hover {
        color: #7cbcff;
        text-style: underline;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.session = TiebaSession()

    async def on_mount(self) -> None:
        cfg = load_config()
        self.title = cfg.get("terminal_title") or "npm run dev"

        if not has_bduss():
            # Prefer QR login on first run
            self.push_screen(LoginScreen())
            return

        try:
            await self.session.start()
            await self.session.verify()
            self.push_screen(ForumScreen())
        except Exception as e:
            self.notify(f"Login failed: {e}", severity="error")
            self.push_screen(LoginScreen())

    async def on_unmount(self) -> None:
        await self.session.close()
        await close_image_client()

    def on_key(self, event: events.Key) -> None:
        # Boss key must intercept before Input consumes the backtick character.
        if event.key != "grave_accent":
            return
        if isinstance(self.screen, BossScreen):
            return
        event.prevent_default()
        event.stop()
        self.action_boss()

    def action_boss(self) -> None:
        if isinstance(self.screen, BossScreen):
            return
        self.push_screen(BossScreen())

    def push_setup(self) -> None:
        self.push_screen(SetupScreen())

    def push_login(self) -> None:
        self.push_screen(LoginScreen())

    def switch_to_forum(self) -> None:
        """After successful setup/login, replace current screen with forum home."""
        self.switch_screen(ForumScreen())

    def open_thread_list(self, fname: str) -> None:
        self.push_screen(ThreadListScreen(fname))

    def open_thread_detail(self, tid: int, *, title: str = "", fname: str = "") -> None:
        self.push_screen(ThreadDetailScreen(tid, title=title, fname=fname))
