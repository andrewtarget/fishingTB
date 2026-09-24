"""CLI entry: TUI by default, `login` for headless QR login."""

from __future__ import annotations

import argparse
import asyncio
import sys


def _cmd_tui() -> None:
    from fishingtb.media.images import clear_disk_cache
    from fishingtb.media.terminal_image import warm_terminal_probe
    from fishingtb.ui.app import FishingApp

    clear_disk_cache()
    warm_terminal_probe()
    FishingApp().run()


async def _cmd_login() -> int:
    from fishingtb.auth.qr_login import QRLoginError, qr_login
    from fishingtb.config import CONFIG_PATH, load_config, save_config
    from fishingtb.media.images import clear_disk_cache
    from fishingtb.session import TiebaSession

    clear_disk_cache()

    async def progress(msg: str) -> None:
        print(msg, flush=True)

    try:
        tokens = await qr_login(progress=progress)
    except QRLoginError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled", file=sys.stderr)
        return 130

    cfg = load_config()
    cfg["bduss"] = tokens.bduss
    if tokens.stoken:
        cfg["stoken"] = tokens.stoken
    save_config(cfg)
    print(f"Saved credentials to {CONFIG_PATH}", flush=True)

    session = TiebaSession()
    try:
        await session.start(tokens.bduss, tokens.stoken)
        await session.verify()
        name = tokens.display_name or session.nick_name or session.user_name
        print(f"Verified · logged in as {name}", flush=True)
    except Exception as e:
        print(f"Saved but verify failed: {e}", file=sys.stderr)
        return 1
    finally:
        await session.close()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="fishingTB — discreet Tieba TUI")
    parser.add_argument(
        "command",
        nargs="?",
        default="tui",
        choices=("tui", "login"),
        help="tui (default) | login (QR login in terminal)",
    )
    args = parser.parse_args(argv)

    if args.command == "login":
        raise SystemExit(asyncio.run(_cmd_login()))
    _cmd_tui()


if __name__ == "__main__":
    main()
