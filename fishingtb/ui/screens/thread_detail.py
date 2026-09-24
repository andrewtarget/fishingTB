"""Read floors — quiet text links + modal image preview."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from fishingtb.feeds.forum import DEFAULT_POST_RN, get_thread_posts
from fishingtb.media.images import warm_image_bytes
from fishingtb.models import PostItem
from fishingtb.ui.screens.image_preview import ImagePreviewScreen
from fishingtb.ui.widgets import StatusBar, ToolBar


class ThreadDetailScreen(Screen):
    BINDINGS = [
        Binding("b", "go_back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("left_square_bracket", "prev_page", "Prev"),
        Binding("right_square_bracket", "next_page", "Next"),
        Binding("j", "scroll_down", "Down"),
        Binding("k", "scroll_up", "Up"),
        Binding("p", "preview_page_images", "Gallery"),
        Binding("grave_accent", "app.boss", "Boss", priority=True, show=False),
    ]

    CSS = """
    ThreadDetailScreen {
        padding: 0 1;
    }
    #detail-header {
        height: auto;
        max-height: 3;
        text-style: bold;
        padding: 0 1;
        border-bottom: tall $primary 20%;
    }
    #posts-scroll {
        height: 1fr;
    }
    .post-block {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1 1 1;
        border-bottom: tall $surface;
    }
    .post-meta {
        height: auto;
        color: $text-muted;
    }
    .post-body {
        height: auto;
        width: 100%;
        color: $text;
    }
    .post-comment {
        height: auto;
        color: $text-muted;
    }
    .img-row {
        height: 1;
        margin-top: 0;
    }
    .img-row Button {
        margin-right: 1;
    }
    """

    def __init__(self, tid: int, *, title: str = "", fname: str = "") -> None:
        super().__init__()
        self.tid = tid
        self.title_text = title
        self.fname = fname
        self.page = 1
        self.has_more = False
        self.posts: list[PostItem] = []
        self._loading = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("", id="detail-header")
            yield VerticalScroll(id="posts-scroll")
            with ToolBar():
                yield Button("返回", id="btn-back")
                yield Button("刷新", id="btn-refresh")
                yield Button("上一页", id="btn-prev")
                yield Button("下一页", id="btn-next")
                yield Button("预览本页图", id="btn-all-imgs")
            yield StatusBar(id="status")

    def on_mount(self) -> None:
        self._update_header()
        self.load_page()

    def _update_header(self) -> None:
        title = self.title_text or f"tid={self.tid}"
        if len(title) > 60:
            title = title[:59] + "…"
        prefix = f"{self.fname}吧 · " if self.fname else ""
        self.query_one("#detail-header", Label).update(
            f"{prefix}{title} · 第 {self.page} 页"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#status", StatusBar).set_status(text)

    def _page_image_urls(self) -> list[str]:
        return [u for p in self.posts for u in p.image_urls]

    @work(exclusive=True)
    async def load_page(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._set_status("加载楼层…")
        try:
            items, has_more, api_title = await get_thread_posts(
                self.app.session,
                self.tid,
                pn=self.page,
                rn=DEFAULT_POST_RN,
            )
            if api_title:
                self.title_text = api_title
            self.posts = items
            self.has_more = has_more
            self._update_header()
            scroll = self.query_one("#posts-scroll", VerticalScroll)
            await scroll.remove_children()
            img_total = 0
            for p in items:
                block = Vertical(classes="post-block")
                await scroll.mount(block)
                await block.mount(
                    Static(
                        f"#{p.floor} · {p.author}",
                        classes="post-meta",
                        markup=False,
                    )
                )
                body = p.body if p.body.strip() else "(无文字内容)"
                await block.mount(
                    Static(body, classes="post-body", markup=False, expand=True)
                )
                if p.image_urls:
                    row = Horizontal(classes="img-row")
                    await block.mount(row)
                    for i, url in enumerate(p.image_urls, 1):
                        img_total += 1
                        btn = Button(
                            f"[图{i}]",
                            classes="img-btn",
                            id=f"img-{p.pid}-{i}",
                        )
                        setattr(btn, "image_url", url)
                        await row.mount(btn)
                for c in p.comments:
                    await block.mount(
                        Static(c, classes="post-comment", markup=False)
                    )
            nonempty = sum(1 for p in items if p.text.strip() or p.image_urls)
            self._set_status(
                f"{len(items)} 楼（有内容 {nonempty}）· 图 {img_total} · 点 [图N] 预览"
            )
            if not items:
                self._set_status("本页无楼层")
            scroll.scroll_home(animate=False)
            self._prefetch_page_images()
        except Exception as e:
            self._set_status(f"错误: {e}")
            self.app.notify(str(e), severity="error")
        finally:
            self._loading = False

    @work
    async def _prefetch_page_images(self) -> None:
        await warm_image_bytes(self._page_image_urls())

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_page()

    def action_prev_page(self) -> None:
        if self.page <= 1:
            return
        self.page -= 1
        self.load_page()

    def action_next_page(self) -> None:
        if not self.has_more:
            self._set_status("没有更多楼层")
            return
        self.page += 1
        self.load_page()

    def action_scroll_down(self) -> None:
        self.query_one("#posts-scroll", VerticalScroll).scroll_relative(y=5)

    def action_scroll_up(self) -> None:
        self.query_one("#posts-scroll", VerticalScroll).scroll_relative(y=-5)

    def action_preview_page_images(self) -> None:
        self._open_preview(self._page_image_urls(), index=0)

    def _open_preview(self, urls: list[str], *, index: int = 0) -> None:
        if not urls:
            self._set_status("没有图片")
            return
        self.app.push_screen(ImagePreviewScreen(urls, index=index))

    @on(Button.Pressed, ".img-btn")
    def on_img_btn(self, event: Button.Pressed) -> None:
        url = getattr(event.button, "image_url", None)
        if not url:
            return
        urls = self._page_image_urls()
        try:
            index = urls.index(str(url))
        except ValueError:
            urls = [str(url)]
            index = 0
        self._open_preview(urls, index=index)

    @on(Button.Pressed, "#btn-all-imgs")
    def on_all_imgs(self) -> None:
        self._open_preview(self._page_image_urls(), index=0)

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.action_go_back()

    @on(Button.Pressed, "#btn-refresh")
    def on_refresh(self) -> None:
        self.action_refresh()

    @on(Button.Pressed, "#btn-prev")
    def on_prev(self) -> None:
        self.action_prev_page()

    @on(Button.Pressed, "#btn-next")
    def on_next(self) -> None:
        self.action_next_page()
