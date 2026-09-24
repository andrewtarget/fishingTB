"""QR login screen — terminal modal QR preview."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from fishingtb.auth.qr_login import (
    QRLoginCancelled,
    QRLoginError,
    QRLoginTimeout,
    qr_login,
)
from fishingtb.config import clear_login_credentials, has_bduss, load_config, save_config
from fishingtb.ui.screens.image_preview import ImagePreviewScreen
from fishingtb.ui.widgets import StatusBar


class QrReady(Message):
    """Show QR in ImagePreviewScreen on the UI thread."""

    def __init__(self, img_url: str, login_id: int) -> None:
        super().__init__()
        self.img_url = img_url
        self.login_id = login_id


class LoginScreen(Screen):
    """Scan Baidu App QR to obtain BDUSS / STOKEN automatically."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("l", "logout", "Logout", show=False),
        Binding("o", "show_qr", "ShowQR", show=False),
        Binding("grave_accent", "app.boss", "Boss", priority=True, show=False),
    ]

    CSS = """
    LoginScreen {
        align: center middle;
    }
    #login-box {
        width: 80;
        height: auto;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #login-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    #login-status {
        min-height: 5;
        margin-bottom: 1;
    }
    #login-actions {
        height: auto;
        layout: horizontal;
    }
    #login-actions Button {
        margin-right: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = False
        self._login_seq = 0
        self._active_logins = 0
        self._last_qr_url = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="login-box"):
            yield Label("登录 /login")
            yield Static(
                "点「扫码登录」会在终端内弹窗显示二维码\n"
                "可多次点击，每次新开一个码 · o 重新打开最近二维码",
                id="login-hint",
            )
            yield Static("准备就绪。", id="login-status")
            with Vertical(id="login-actions"):
                yield Button("扫码登录", variant="primary", id="start")
                yield Button("显示二维码", id="show-qr")
                yield Button("登出", id="logout")
                yield Button("返回", id="cancel")
        yield StatusBar(id="status")

    def on_mount(self) -> None:
        self.query_one("#status", StatusBar).set_status(
            "终端内扫码 · o 显示最近二维码"
        )
        self._refresh_logged_in_hint()
        self._update_leave_button()

    def _can_go_back(self) -> bool:
        """Only return to the previous screen when already logged in and login was opened on top."""
        return self.app.session.started and len(self.app.screen_stack) > 1

    def _update_leave_button(self) -> None:
        btn = self.query_one("#cancel", Button)
        btn.label = "返回" if self._can_go_back() else "退出"

    def _refresh_logged_in_hint(self) -> None:
        btn = self.query_one("#logout", Button)
        if not has_bduss() and not self.app.session.started:
            btn.disabled = True
            return
        btn.disabled = False
        name = self.app.session.nick_name or self.app.session.user_name
        if name:
            self._set_msg(f"当前已登录：{name}\n可重新扫码换号，或点「登出」")
        elif has_bduss():
            self._set_msg("当前已保存登录凭证\n可重新扫码换号，或点「登出」")
        self._update_leave_button()

    def on_qr_ready(self, event: QrReady) -> None:
        self._last_qr_url = event.img_url
        self.app.push_screen(
            ImagePreviewScreen(
                [event.img_url],
                title_prefix=f"扫码登录 #{event.login_id}",
                hint="百度 App 扫码并在手机确认 · Esc 关弹窗（后台仍等待）",
                gallery=False,
            )
        )
        self._set_msg(f"#{event.login_id} 已在终端弹窗显示二维码，请扫码")

    def action_cancel(self) -> None:
        self._cancelled = True
        if self._can_go_back():
            self.app.pop_screen()
        else:
            self.app.exit()

    def action_logout(self) -> None:
        if not has_bduss() and not self.app.session.started:
            self._set_msg("当前未登录")
            return
        self._do_logout()

    def action_show_qr(self) -> None:
        self._show_last_qr()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self._start()
        elif event.button.id == "show-qr":
            self._show_last_qr()
        elif event.button.id == "logout":
            self.action_logout()
        elif event.button.id == "cancel":
            self.action_cancel()

    def _set_msg(self, text: str) -> None:
        self.query_one("#login-status", Static).update(text)
        self.query_one("#status", StatusBar).set_status(text.split("\n")[0][:80])

    def _show_last_qr(self) -> None:
        if not self._last_qr_url:
            self.app.notify("请先点「扫码登录」", severity="warning")
            return
        self.app.push_screen(
            ImagePreviewScreen(
                [self._last_qr_url],
                title_prefix="扫码登录",
                hint="百度 App 扫码 · Esc 关闭",
                gallery=False,
            )
        )

    def _start(self) -> None:
        self._login_seq += 1
        login_id = self._login_seq
        self._active_logins += 1
        self._set_msg(f"#{login_id} 正在获取二维码…（进行中 {self._active_logins} 个）")
        self._run_login(login_id)

    @work
    async def _do_logout(self) -> None:
        self._cancelled = True
        self._set_msg("正在登出…")
        try:
            await self.app.session.close()
            clear_login_credentials()
            self.app.notify("已登出")
            self.app.switch_screen(LoginScreen())
        except Exception as e:
            self._set_msg(f"登出失败: {e}")
            self.app.notify(str(e), severity="error")

    @work
    async def _run_login(self, login_id: int) -> None:
        async def progress(msg: str) -> None:
            self._set_msg(f"#{login_id} {msg}")

        def on_qr_ready(img_url: str) -> None:
            self.post_message(QrReady(img_url, login_id))

        try:
            tokens = await qr_login(
                timeout=180.0,
                progress=progress,
                should_cancel=lambda: self._cancelled,
                on_qr_ready=on_qr_ready,
            )
            cfg = load_config()
            cfg["bduss"] = tokens.bduss
            if tokens.stoken:
                cfg["stoken"] = tokens.stoken
            save_config(cfg)

            await self.app.session.start(tokens.bduss, tokens.stoken)
            await self.app.session.verify()
            name = (
                tokens.display_name
                or self.app.session.nick_name
                or self.app.session.user_name
            )
            self._set_msg(f"#{login_id} 登录成功 · {name}")
            self.app.notify(f"已登录：{name}")
            self.query_one("#logout", Button).disabled = False
            self._update_leave_button()
            self.app.switch_to_forum()
        except QRLoginCancelled:
            self._set_msg(f"#{login_id} 已取消")
        except QRLoginTimeout:
            self._set_msg(f"#{login_id} 超时 — 可再点「扫码登录」")
        except QRLoginError as e:
            self._set_msg(f"#{login_id} 失败: {e}")
        except Exception as e:
            self._set_msg(f"#{login_id} 失败: {e}")
        finally:
            self._active_logins = max(0, self._active_logins - 1)
