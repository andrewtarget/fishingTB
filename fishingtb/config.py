"""Local config: BDUSS / STOKEN and recent forums."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
EXAMPLE_PATH = ROOT / "config.example.yaml"

# Generated / bulky runtime data only (e.g. image cache, cleared on start).
DATA_DIR = ROOT / "data"
IMAGE_CACHE_DIR = DATA_DIR / "cache" / "images"

DEFAULTS: dict[str, Any] = {
    "bduss": "",
    "stoken": "",
    "terminal_title": "npm run dev",
    "recent_forums": [],
    # auto | sixel | braille | halfblock  (auto → Sixel in Windows Terminal)
    "image_renderer": "auto",
}

_legacy_migrated = False


def ensure_data_layout() -> None:
    """Ensure directories for generated cache exist."""
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def migrate_legacy_paths() -> None:
    """One-time path fixes from older layouts."""
    global _legacy_migrated
    if _legacy_migrated:
        return
    _legacy_migrated = True
    ensure_data_layout()

    nested_cfg = DATA_DIR / "config.yaml"
    if nested_cfg.exists() and not CONFIG_PATH.exists():
        shutil.move(str(nested_cfg), str(CONFIG_PATH))

    old_cache = ROOT / "cache" / "images"
    if old_cache.is_dir():
        for src in old_cache.glob("*"):
            if not src.is_file():
                continue
            dest = IMAGE_CACHE_DIR / src.name
            if not dest.exists():
                shutil.copy2(src, dest)


def load_config() -> dict[str, Any]:
    """Load config.yaml, merging with defaults. Missing file → defaults."""
    migrate_legacy_paths()
    data = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if isinstance(loaded, dict):
            data.update(loaded)
    data["bduss"] = str(data.get("bduss") or "").strip()
    data["stoken"] = str(data.get("stoken") or "").strip()
    data["terminal_title"] = str(data.get("terminal_title") or DEFAULTS["terminal_title"])
    recent = data.get("recent_forums") or []
    data["recent_forums"] = [str(x).strip() for x in recent if str(x).strip()]
    return data


def save_config(data: dict[str, Any]) -> None:
    """Write config.yaml at project root."""
    merged = dict(DEFAULTS)
    merged.update(data)
    merged["bduss"] = str(merged.get("bduss") or "").strip()
    merged["stoken"] = str(merged.get("stoken") or "").strip()
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=False)


def has_bduss() -> bool:
    return bool(load_config().get("bduss"))


def clear_login_credentials() -> None:
    """Remove BDUSS/STOKEN from config.yaml (logout)."""
    cfg = load_config()
    cfg["bduss"] = ""
    cfg["stoken"] = ""
    save_config(cfg)


def add_recent_forum(fname: str, *, limit: int = 10) -> None:
    """Push forum name to the front of recent_forums."""
    fname = fname.strip()
    if not fname:
        return
    cfg = load_config()
    recent = [f for f in cfg.get("recent_forums", []) if f != fname]
    recent.insert(0, fname)
    cfg["recent_forums"] = recent[:limit]
    save_config(cfg)
