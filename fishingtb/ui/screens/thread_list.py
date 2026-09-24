"""Hot/recommended threads for one forum — mouse-friendly list."""

from __future__ import annotations

from aiotieba.enums import ThreadSortType
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, ListItem, ListView

from fishingtb.feeds.forum import DEFAULT_THREAD_RN, get_forum_threads
from fishingtb.models import ThreadItem
from fishingtb.ui.widgets import StatusBar, ToolBar


class ThreadListScreen(Screen):
    BINDINGS = [
        Binding("b", "go_back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("left_square_bracket", "prev_page", "Prev"),
        Binding("right_square_bracket", "next_page", "Next"),
        Binding("s", "toggle_sort", "Sort"),
        Binding("grave_accent", "app.boss", "Boss", priority=True, show=False),
    ]

    CSS = """
    ThreadListScreen {
        padding: 0 1;
    }
    #list-header {
        height: 1;
        text-style: bold;
        padding: 0 1;
    }
    #thread-list {
        height: 1fr;
        border: round $primary;
    }
    """

    def __init__(self, fname: str) -> None:
        super().__init__()
        self.fname = fname
        self.page = 1
        self.has_more = False
        self.sort = ThreadSortType.HOT
        self.threads: list[ThreadItem] = []
        self._loading = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("", id="list-header")
            yield ListView(id="thread-list")
            with ToolBar():
                yield Button("返回", id="btn-back")
                yield Button("刷新", id="btn-refresh")
                yield Button("热门/回复", id="btn-sort")
                yield Button("上一页", id="btn-prev")
                yield Button("下一页", id="btn-next")
                yield Button("打开", id="btn-open")
            yield StatusBar(id="status")

    def on_mount(self) -> None:
        self._update_header()
        self.load_page()

    def _sort_label(self) -> str:
        return "热门" if self.sort == ThreadSortType.HOT else "最新回复"

    def _update_header(self) -> None:
        self.query_one("#list-header", Label).update(
            f"{self.fname}吧 · {self._sort_label()} · 第 {self.page} 页"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#status", StatusBar).set_status(text)

    @work(exclusive=True)
    async def load_page(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._set_status("加载中…")
        self._update_header()
        try:
            items, has_more = await get_forum_threads(
                self.app.session,
                self.fname,
                pn=self.page,
                rn=DEFAULT_THREAD_RN,
                sort=self.sort,
            )
            self.threads = items
            self.has_more = has_more
            lv = self.query_one("#thread-list", ListView)
            await lv.clear()
            for t in items:
                await lv.append(ListItem(Label(t.list_label, markup=False), name=str(t.tid)))
            self._set_status(
                f"{len(items)} 帖 · 单击或「打开」进帖 · 鼠标点底部按钮翻页"
            )
            if not items:
                self._set_status(f"第 {self.page} 页无帖，试试换排序或上一页")
        except Exception as e:
            self._set_status(f"错误: {e}")
            self.app.notify(str(e), severity="error")
        finally:
            self._loading = False

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
            self._set_status("没有更多了")
            return
        self.page += 1
        self.load_page()

    def action_toggle_sort(self) -> None:
        self.sort = (
            ThreadSortType.REPLY
            if self.sort == ThreadSortType.HOT
            else ThreadSortType.HOT
        )
        self.page = 1
        self.load_page()

    def _open_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.threads):
            return
        t = self.threads[idx]
        self.app.open_thread_detail(t.tid, title=t.display_title, fname=self.fname)

    @on(ListView.Selected, "#thread-list")
    def on_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if item is None or not item.name:
            return
        tid = int(item.name)
        thread = next((t for t in self.threads if t.tid == tid), None)
        if thread:
            self.app.open_thread_detail(
                thread.tid, title=thread.display_title, fname=self.fname
            )

    @on(Button.Pressed, "#btn-back")
    def on_back(self) -> None:
        self.action_go_back()

    @on(Button.Pressed, "#btn-refresh")
    def on_refresh(self) -> None:
        self.action_refresh()

    @on(Button.Pressed, "#btn-sort")
    def on_sort(self) -> None:
        self.action_toggle_sort()

    @on(Button.Pressed, "#btn-prev")
    def on_prev(self) -> None:
        self.action_prev_page()

    @on(Button.Pressed, "#btn-next")
    def on_next(self) -> None:
        self.action_next_page()

    @on(Button.Pressed, "#btn-open")
    def on_open(self) -> None:
        lv = self.query_one("#thread-list", ListView)
        idx = lv.index
        if idx is None:
            self._set_status("请先点选一条帖子")
            return
        self._open_index(idx)
