"""In-terminal image preview — Sixel when available, else half-block fallback."""

from __future__ import annotations

import webbrowser

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from fishingtb.media.images import PREVIEW_MAX_SIDE, fetch_image, warm_image_bytes
from fishingtb.media.terminal_image import (
    create_image_widget,
    display_bounds,
    resolve_image_renderer,
)
from fishingtb.ui.widgets import StatusBar, ToolBar


class ImagePreviewScreen(ModalScreen[None]):
    """Lazy-load one image into the terminal; optional prev/next gallery."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("b", "close", "Close"),
        Binding("left", "prev", "Prev"),
        Binding("right", "next", "Next"),
        Binding("o", "browser", "Browser"),
        Binding("grave_accent", "app.boss", "Boss", priority=True, show=False),
    ]

    CSS = """
    ImagePreviewScreen {
        align: center middle;
        background: $background 80%;
    }
    #preview-box {
        width: 96%;
        height: 92%;
        background: $surface;
        border: tall $primary 30%;
        padding: 0 1;
    }
    #preview-title {
        height: 1;
        color: $text-muted;
    }
    #preview-host {
        height: 1fr;
        width: 100%;
        overflow: hidden;
        align: center middle;
    }
    #preview-hint {
        height: 1;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        urls: list[str],
        *,
        index: int = 0,
        title_prefix: str = "图片预览",
        hint: str | None = None,
        gallery: bool | None = None,
    ) -> None:
        super().__init__()
        self.urls = [u for u in urls if u]
        self.index = max(0, min(index, len(self.urls) - 1)) if self.urls else 0
        self._loading = False
        self.title_prefix = title_prefix
        self.hint_text = hint or "←/→ 切换 · Esc 关闭 · o 浏览器打开"
        self.gallery = gallery if gallery is not None else len(self.urls) > 1

    def compose(self) -> ComposeResult:
        with Vertical(id="preview-box"):
            yield Static("", id="preview-title", markup=False)
            yield Container(id="preview-host")
            yield Static(self.hint_text, id="preview-hint", markup=False)
            with ToolBar():
                if self.gallery:
                    yield Button("上一张", id="btn-prev")
                    yield Button("下一张", id="btn-next")
                yield Button("浏览器", id="btn-browser")
                yield Button("关闭", id="btn-close")
            yield StatusBar(id="status")

    def on_mount(self) -> None:
        self.call_after_refresh(self.load_current)

    def _host_cells(self) -> tuple[int, int]:
        """Actual preview pane size — never guess a taller box than this."""
        host = self.query_one("#preview-host", Container)
        w = host.content_size.width
        h = host.content_size.height
        if w < 8 or h < 4:
            return display_bounds(self.app.size, mode="full")
        return (max(8, w), max(4, h))

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", StatusBar).set_status(msg)

    def _set_title(self) -> None:
        if not self.urls:
            self.query_one("#preview-title", Static).update(f"{self.title_prefix} · 无图片")
            return
        if self.gallery:
            n = len(self.urls)
            self.query_one("#preview-title", Static).update(
                f"{self.title_prefix}  {self.index + 1}/{n}"
            )
        else:
            self.query_one("#preview-title", Static).update(self.title_prefix)

    def _neighbor_urls(self) -> list[str]:
        if not self.urls:
            return []
        n = len(self.urls)
        out: list[str] = []
        for offset in (1, -1):
            i = (self.index + offset) % n
            out.append(self.urls[i])
        return out

    @work(exclusive=True)
    async def load_current(self) -> None:
        if not self.urls:
            self._set_status("无图片可预览")
            return
        if self._loading:
            return
        self._loading = True
        self._set_title()
        self._set_status("加载图片中…")
        url = self.urls[self.index]
        host = self.query_one("#preview-host", Container)
        await host.remove_children()
        await host.mount(Static("加载中…", markup=False))
        try:
            mw, mh = self._host_cells()
            self._set_status("下载图片…")
            pil = await fetch_image(url, max_side=PREVIEW_MAX_SIDE, priority=True)
            self._set_status("渲染图片…")
            widget = await create_image_widget(
                pil,
                max_width=mw,
                max_height=mh,
                mode="full",
            )
            await host.remove_children()
            await host.mount(widget)
            renderer = resolve_image_renderer()
            tag = type(widget).__name__
            if renderer == "sixel" and tag == "Image":
                tag = "Sixel"
            self._set_status(f"已加载 · {pil.width}x{pil.height} · {tag}")
            self._warm_neighbors()
        except Exception as e:
            await host.remove_children()
            await host.mount(Static(f"加载失败: {e}\n按 o 用浏览器打开", markup=False))
            self._set_status(f"失败: {e}")
            self.app.notify(str(e), severity="error")
        finally:
            self._loading = False

    @work
    async def _warm_neighbors(self) -> None:
        if not self.gallery:
            return
        await warm_image_bytes(self._neighbor_urls(), limit=2)

    def action_close(self) -> None:
        self.dismiss()

    def action_prev(self) -> None:
        if len(self.urls) <= 1:
            return
        self.index = (self.index - 1) % len(self.urls)
        self.load_current()

    def action_next(self) -> None:
        if len(self.urls) <= 1:
            return
        self.index = (self.index + 1) % len(self.urls)
        self.load_current()

    def action_browser(self) -> None:
        if not self.urls:
            return
        webbrowser.open(self.urls[self.index])
        self._set_status("已在浏览器打开当前图")

    @on(Button.Pressed, "#btn-prev")
    def on_prev(self) -> None:
        self.action_prev()

    @on(Button.Pressed, "#btn-next")
    def on_next(self) -> None:
        self.action_next()

    @on(Button.Pressed, "#btn-browser")
    def on_browser(self) -> None:
        self.action_browser()

    @on(Button.Pressed, "#btn-close")
    def on_close(self) -> None:
        self.action_close()
