"""Boss key camouflage screen — looks like a build log."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import RichLog

FAKE_LOG = """\
> npm run build

> project@1.2.3 build
> webpack --config webpack.prod.js

asset main.js 412 KiB [emitted] [minimized] (name: main)
asset vendor.js 1.08 MiB [emitted] [minimized] (name: vendor)
asset index.html 1.24 KiB [emitted]
orphan modules 48.2 KiB [orphan] 12 modules
runtime modules 3.1 KiB 8 modules
cacheable modules 1.42 MiB
  modules by path ./src/ 318 KiB 64 modules
  modules by path ./node_modules/ 1.1 MiB 89 modules

WARNING in asset size limit: The following asset(s) exceed the recommended size limit (244 KiB).
  asset vendor.js (1.08 MiB)

webpack compiled with 1 warning in 3842 ms

> eslint src --ext .ts,.tsx

✔ No ESLint warnings or errors

> tsc --noEmit

Done in 2.1s.
"""


class BossScreen(ModalScreen[None]):
    """Fake webpack / npm output. Press ` again or Esc to return."""

    BINDINGS = [
        ("escape", "dismiss_boss", "Back"),
        ("grave_accent", "dismiss_boss", "Back"),
        ("q", "quit_app", "Quit"),
    ]

    CSS = """
    BossScreen {
        background: #0c0c0c;
    }
    #boss-log {
        height: 1fr;
        width: 1fr;
        background: #0c0c0c;
        color: #cccccc;
        border: none;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        log = RichLog(id="boss-log", highlight=False, markup=False)
        yield log

    def on_mount(self) -> None:
        self.app.title = "npm run build"
        log = self.query_one("#boss-log", RichLog)
        for line in FAKE_LOG.splitlines():
            log.write(line)
        log.focus()

    def action_dismiss_boss(self) -> None:
        from fishingtb.config import load_config

        self.app.title = load_config().get("terminal_title", "npm run dev")
        self.dismiss()

    def action_quit_app(self) -> None:
        self.app.exit()
