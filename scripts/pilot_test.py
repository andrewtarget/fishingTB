"""Headless Textual pilot for home + boss."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fishingtb import config as cfg
from fishingtb.ui.app import FishingApp
from fishingtb.ui.screens.boss import BossScreen
from fishingtb.ui.screens.forum import ForumScreen
from fishingtb.ui.screens.login import LoginScreen


async def run_pilot() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "config.yaml"
        with patch.object(cfg, "CONFIG_PATH", path):

            async def fake_qr(*_a, **_k):
                await asyncio.sleep(60)
                raise RuntimeError("should not finish")

            with patch("fishingtb.ui.screens.login.qr_login", side_effect=fake_qr):
                app = FishingApp()
                async with app.run_test() as pilot:
                    await pilot.pause()
                    assert isinstance(app.screen, LoginScreen), type(app.screen)
                    app.screen._cancelled = True  # type: ignore[attr-defined]

            cfg.save_config(
                {
                    "bduss": "fake",
                    "stoken": "",
                    "terminal_title": "npm run test",
                    "recent_forums": ["python"],
                }
            )
            app2 = FishingApp()

            async def fake_start(*_a, **_k):
                app2.session._client = object()

            async def fake_verify():
                app2.session.user_name = "tester"
                app2.session.nick_name = "tester"
                return object()

            app2.session.start = AsyncMock(side_effect=fake_start)  # type: ignore
            app2.session.verify = AsyncMock(side_effect=fake_verify)  # type: ignore
            app2.session.close = AsyncMock()  # type: ignore

            # Avoid network on home feed load
            with (
                patch(
                    "fishingtb.ui.screens.forum.get_followed_forums",
                    AsyncMock(return_value=[]),
                ),
                patch(
                    "fishingtb.ui.screens.forum.get_follow_feed",
                    AsyncMock(return_value=[]),
                ),
            ):
                async with app2.run_test() as pilot:
                    await pilot.pause()
                    assert isinstance(app2.screen, ForumScreen), type(app2.screen)
                    # mouse-ish: press tab button via action
                    await pilot.click("#tab-forums")
                    await pilot.pause()
                    await pilot.press("grave_accent")
                    await pilot.pause()
                    assert isinstance(app2.screen, BossScreen)
                    await pilot.press("escape")
                    await pilot.pause()
                    assert isinstance(app2.screen, ForumScreen)

    print("pilot ok")


if __name__ == "__main__":
    asyncio.run(run_pilot())
