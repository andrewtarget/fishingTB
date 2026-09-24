"""Home: follow feed, followed forums, search — mouse-friendly."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, ListItem, ListView, Static

from fishingtb.config import add_recent_forum, load_config
from fishingtb.feeds.follow import get_follow_feed, get_followed_forums
from fishingtb.models import ForumItem, ThreadItem
from fishingtb.ui.widgets import CamouflageInput, StatusBar, ToolBar


class ForumScreen(Screen):
    """Main hub after login."""

    BINDINGS = [
        Binding("slash", "focus_input", "Search"),
        Binding("1", "show_feed", "Feed"),
        Binding("2", "show_forums", "Forums"),
        Binding("3", "show_search", "Search"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "open_setup", "Credentials"),
        Binding("grave_accent", "app.boss", "Boss", priority=True, show=False),
    ]

    CSS = """
    ForumScreen {
        padding: 0 1;
    }
    #home-header {
        height: 1;
        text-style: bold;
        padding: 0 1;
    }
    #tab-bar {
        height: 1;
        padding: 0 1;
        margin-bottom: 1;
    }
    #tab-bar Button {
        margin-right: 1;
    }
    #tab-bar Button.-active {
        color: #4ea1ff;
        text-style: underline;
        background: transparent;
    }
    #content {
        height: 1fr;
    }
    #feed-list, #forum-list {
        height: 1fr;
        border: tall $primary 20%;
    }
    #search-pane {
        height: 1fr;
        padding: 0 1;
    }
    #forum-input {
        margin-bottom: 1;
    }
    #recent-label {
        color: $text-muted;
    }
    #recent-list {
        height: 1fr;
        border: tall $primary 20%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.tab = "feed"  # feed | forums | search
        self.forums: list[ForumItem] = []
        self.feed: list[ThreadItem] = []
        self._loading_feed = False
        self._loading_forums = False

    def compose(self) -> ComposeResult:
        yield Label("Home", id="home-header")
        with Horizontal(id="tab-bar"):
            yield Button("关注动态", id="tab-feed")
            yield Button("关注的吧", id="tab-forums")
            yield Button("搜索吧", id="tab-search")
            yield Button("刷新", id="btn-refresh")
            yield Button("登录", id="btn-login")
        with Vertical(id="content"):
            yield ListView(id="feed-list")
            yield ListView(id="forum-list")
            with Vertical(id="search-pane"):
                yield CamouflageInput(
                    placeholder="输入吧名后回车，或点最近访问",
                    id="forum-input",
                )
                yield Static("最近访问", id="recent-label", markup=False)
                yield ListView(id="recent-list")
        with ToolBar(id="home-tools"):
            yield Button("打开选中", id="btn-open")
            yield Button("凭证设置", id="btn-setup")
        yield StatusBar(id="status")

    def on_mount(self) -> None:
        user = ""
        if self.app.session.started:
            user = self.app.session.nick_name or self.app.session.user_name
        self.query_one("#home-header", Label).update(f"fishingTB · {user}")
        self._reload_recent()
        self._show_tab("feed")
        self.reload_current()

    def _set_status(self, text: str) -> None:
        self.query_one("#status", StatusBar).set_status(text)

    def _reload_recent(self) -> None:
        lv = self.query_one("#recent-list", ListView)
        lv.clear()
        for name in load_config().get("recent_forums", []):
            lv.append(ListItem(Label(name, markup=False), name=name))

    def _show_tab(self, tab: str) -> None:
        self.tab = tab
        feed = self.query_one("#feed-list", ListView)
        forums = self.query_one("#forum-list", ListView)
        search = self.query_one("#search-pane", Vertical)
        feed.display = tab == "feed"
        forums.display = tab == "forums"
        search.display = tab == "search"
        for tid, name in (
            ("tab-feed", "feed"),
            ("tab-forums", "forums"),
            ("tab-search", "search"),
        ):
            btn = self.query_one(f"#{tid}", Button)
            if name == tab:
                btn.add_class("-active")
            else:
                btn.remove_class("-active")
        if tab == "search":
            self.query_one("#forum-input", CamouflageInput).focus()

    def action_show_feed(self) -> None:
        self._show_tab("feed")
        if not self.feed:
            self.reload_current()

    def action_show_forums(self) -> None:
        self._show_tab("forums")
        if self.forums:
            self._paint_forum_list()
        elif not self._loading_forums:
            self.load_forums()

    @work
    async def _paint_forum_list(self) -> None:
        await self._render_forum_list()
        if self.tab == "forums" and self.forums:
            self._set_status(
                f"关注 {len(self.forums)} 个吧 · 单击打开 · 或点「打开选中」"
            )

    def action_show_search(self) -> None:
        self._show_tab("search")

    def action_focus_input(self) -> None:
        self._show_tab("search")

    def action_refresh(self) -> None:
        self.reload_current()

    def action_open_setup(self) -> None:
        self.app.push_setup()

    def action_open_login(self) -> None:
        self.app.push_login()

    @on(Button.Pressed, "#tab-feed")
    def on_tab_feed(self) -> None:
        self.action_show_feed()

    @on(Button.Pressed, "#tab-forums")
    def on_tab_forums(self) -> None:
        self.action_show_forums()

    @on(Button.Pressed, "#tab-search")
    def on_tab_search(self) -> None:
        self.action_show_search()

    @on(Button.Pressed, "#btn-refresh")
    def on_btn_refresh(self) -> None:
        self.reload_current()

    @on(Button.Pressed, "#btn-login")
    def on_btn_login(self) -> None:
        self.app.push_login()

    @on(Button.Pressed, "#btn-setup")
    def on_btn_setup(self) -> None:
        self.app.push_setup()

    @on(Button.Pressed, "#btn-open")
    def on_btn_open(self) -> None:
        self._open_highlighted()

    def reload_current(self) -> None:
        if self.tab == "feed":
            self.load_feed()
        elif self.tab == "forums":
            self.load_forums()
        else:
            self._reload_recent()
            self._set_status("输入吧名回车 · 或点击最近访问 · 鼠标可点按钮")

    async def _render_forum_list(self) -> None:
        lv = self.query_one("#forum-list", ListView)
        await lv.clear()
        for f in self.forums:
            await lv.append(ListItem(Label(f.label, markup=False), name=f.fname))

    @work(exclusive=True)
    async def load_forums(self) -> None:
        if self._loading_forums:
            return
        self._loading_forums = True
        self._set_status("加载关注的吧…")
        try:
            self.forums = await get_followed_forums(self.app.session)
            await self._render_forum_list()
            if self.forums:
                self._set_status(
                    f"关注 {len(self.forums)} 个吧 · 单击打开 · 或点「打开选中」"
                )
            else:
                self._set_status(
                    "关注列表为空 — 若贴吧里确实有关注，请 /login 重新扫码登录"
                )
        except Exception as e:
            self._set_status(f"关注列表失败: {e}")
            self.app.notify(str(e), severity="error")
        finally:
            self._loading_forums = False

    @work(exclusive=True)
    async def load_feed(self) -> None:
        if self._loading_feed:
            return
        self._loading_feed = True
        self._set_status("加载关注动态（聚合多个吧）…")
        try:
            if not self.forums:
                self.forums = await get_followed_forums(self.app.session)
                if self.tab == "forums":
                    await self._render_forum_list()
            self.feed = await get_follow_feed(
                self.app.session,
                forum_limit=25,
                per_forum=10,
                forums=self.forums,
            )
            lv = self.query_one("#feed-list", ListView)
            await lv.clear()
            for t in self.feed:
                await lv.append(ListItem(Label(t.list_label, markup=False), name=str(t.tid)))
            if self.feed:
                self._set_status(
                    f"动态 {len(self.feed)} 条（来自 {min(25, len(self.forums))} 个吧）"
                    " · 单击打开帖子"
                )
            elif self.forums:
                self._set_status(
                    f"暂无动态（已关注 {len(self.forums)} 个吧）· 可点「关注的吧」进单吧"
                )
            else:
                self._set_status("暂无关注吧 — 请 /login 重新登录或搜索吧名进入")
        except Exception as e:
            self._set_status(f"动态加载失败: {e}")
            self.app.notify(str(e), severity="error")
        finally:
            self._loading_feed = False

    def _open_highlighted(self) -> None:
        if self.tab == "feed":
            lv = self.query_one("#feed-list", ListView)
            idx = lv.index
            if idx is None or idx < 0 or idx >= len(self.feed):
                self._set_status("请先用鼠标点选一条动态")
                return
            t = self.feed[idx]
            self.app.open_thread_detail(t.tid, title=t.display_title, fname=t.fname)
        elif self.tab == "forums":
            lv = self.query_one("#forum-list", ListView)
            idx = lv.index
            if idx is None or idx < 0 or idx >= len(self.forums):
                self._set_status("请先用鼠标点选一个吧")
                return
            self._open_forum(self.forums[idx].fname)
        else:
            lv = self.query_one("#recent-list", ListView)
            item = lv.highlighted_child
            if item and isinstance(item.name, str) and item.name:
                self._open_forum(item.name)

    @on(ListView.Selected, "#feed-list")
    def on_feed_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if item is None or not item.name:
            return
        tid = int(item.name)
        thread = next((t for t in self.feed if t.tid == tid), None)
        if thread:
            self.app.open_thread_detail(
                thread.tid, title=thread.display_title, fname=thread.fname
            )

    @on(ListView.Selected, "#forum-list")
    def on_forum_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if item and isinstance(item.name, str) and item.name:
            self._open_forum(item.name)

    @on(ListView.Selected, "#recent-list")
    def on_recent_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if item and isinstance(item.name, str) and item.name:
            self._open_forum(item.name)

    @on(CamouflageInput.Submitted, "#forum-input")
    def on_input_submitted(self, event: CamouflageInput.Submitted) -> None:
        raw = event.value.strip()
        if raw.lower() in ("/login", "login"):
            self.query_one("#forum-input", CamouflageInput).value = ""
            self.app.push_login()
            return
        if raw.lower() in ("/setup", "setup"):
            self.query_one("#forum-input", CamouflageInput).value = ""
            self.app.push_setup()
            return
        self._open_forum(raw)

    def _open_forum(self, fname: str) -> None:
        fname = fname.strip()
        if fname.endswith("吧") and len(fname) > 1:
            fname = fname[:-1]
        if not fname:
            self._set_status("吧名为空")
            return
        add_recent_forum(fname)
        self._reload_recent()
        self.app.open_thread_list(fname)
