"""First-run / re-login: QR login or paste BDUSS."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from fishingtb.config import load_config, save_config
from fishingtb.ui.widgets import CamouflageInput, StatusBar


class SetupScreen(Screen):
    BINDINGS = [
        Binding("escape", "maybe_back", "Back"),
        Binding("grave_accent", "app.boss", "Boss", priority=True, show=False),
    ]

    CSS = """
    SetupScreen {
        align: center middle;
    }
    #setup-box {
        width: 72;
        height: auto;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #setup-box Label {
        margin-bottom: 0;
    }
    #setup-box Input {
        margin-bottom: 1;
    }
    #setup-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    #setup-actions {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    #setup-actions Button {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        cfg = load_config()
        with Vertical(id="setup-box"):
            yield Label("Login")
            yield Static(
                "Recommended: QR Login — opens browser, scan with 百度 App.\n"
                "Or paste BDUSS / STOKEN from browser cookies (manual).",
                id="setup-hint",
            )
            with Vertical(id="setup-actions"):
                yield Button("QR Login (/login)", variant="primary", id="qr")
                yield Button("Save pasted tokens", id="save")
            yield Label("BDUSS (manual fallback)")
            yield CamouflageInput(
                value=cfg.get("bduss", ""),
                placeholder="paste BDUSS here",
                password=True,
                id="bduss",
            )
            yield Label("STOKEN (optional)")
            yield CamouflageInput(
                value=cfg.get("stoken", ""),
                placeholder="paste STOKEN here",
                password=True,
                id="stoken",
            )
        yield StatusBar(id="status")

    def on_mount(self) -> None:
        self.query_one("#status", StatusBar).set_status(
            "QR Login recommended · Esc cancel"
        )

    def action_maybe_back(self) -> None:
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.exit()

    @on(Button.Pressed, "#qr")
    def on_qr(self) -> None:
        self.app.push_login()

    @on(Button.Pressed, "#save")
    def on_save(self) -> None:
        bduss = self.query_one("#bduss", CamouflageInput).value.strip()
        stoken = self.query_one("#stoken", CamouflageInput).value.strip()
        if not bduss:
            self.query_one("#status", StatusBar).set_status("BDUSS is required")
            return
        self.query_one("#status", StatusBar).set_status("Verifying…")
        self.query_one("#save", Button).disabled = True
        self._verify(bduss, stoken)

    @work(exclusive=True)
    async def _verify(self, bduss: str, stoken: str) -> None:
        status = self.query_one("#status", StatusBar)
        btn = self.query_one("#save", Button)
        try:
            cfg = load_config()
            cfg["bduss"] = bduss
            cfg["stoken"] = stoken
            save_config(cfg)
            await self.app.session.start(bduss, stoken)
            user = await self.app.session.verify()
            name = self.app.session.nick_name or self.app.session.user_name or str(user)
            status.set_status(f"OK · logged in as {name}")
            self.app.notify(f"Logged in as {name}")
            self.app.switch_to_forum()
        except Exception as e:
            status.set_status(f"Failed: {e}")
            self.app.notify(str(e), severity="error")
        finally:
            btn.disabled = False
