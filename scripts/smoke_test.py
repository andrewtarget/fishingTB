"""Smoke test: config round-trip and app construct (no network)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from fishingtb import config as cfg
from fishingtb.models import PostItem, ThreadItem
from fishingtb.ui.app import FishingApp


def test_config_roundtrip(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.yaml"
    monkeypatch.setattr(cfg, "CONFIG_PATH", path)
    data = {
        "bduss": "test_bduss",
        "stoken": "test_stoken",
        "terminal_title": "npm run test",
        "recent_forums": [],
    }
    cfg.save_config(data)
    loaded = cfg.load_config()
    assert loaded["bduss"] == "test_bduss"
    assert loaded["stoken"] == "test_stoken"
    assert loaded["terminal_title"] == "npm run test"

    cfg.add_recent_forum("python")
    cfg.add_recent_forum("游戏")
    cfg.add_recent_forum("python")
    recent = cfg.load_config()["recent_forums"]
    assert recent[0] == "python"
    assert recent[1] == "游戏"
    assert recent.count("python") == 1


def test_models() -> None:
    t = ThreadItem(
        tid=1,
        title="",
        text="hello world " * 5,
        reply_num=2,
        view_num=10,
        last_time=1700000000,
        author="u",
        fname="python",
    )
    assert t.display_title
    assert t.last_time_str
    p = PostItem(pid=1, floor=1, author="a", text="hi", img_count=2)
    assert "[图片 x2]" in p.body


def test_app_construct() -> None:
    app = FishingApp()
    assert app.session is not None
    assert app.TITLE


if __name__ == "__main__":
    # minimal run without pytest
    import fishingtb.config as c

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "config.yaml"
        with mock.patch.object(c, "CONFIG_PATH", p):
            c.save_config({"bduss": "x", "stoken": "", "terminal_title": "t", "recent_forums": []})
            c.add_recent_forum("python")
            assert c.load_config()["recent_forums"] == ["python"]
            assert c.has_bduss()
    test_models()
    test_app_construct()
    print("smoke ok")
