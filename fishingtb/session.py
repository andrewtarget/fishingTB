"""aiotieba Client lifecycle and login verification."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiotieba

from fishingtb.config import load_config

if TYPE_CHECKING:
    from aiotieba.typing import UserInfo


class TiebaSession:
    """Owns a single aiotieba.Client for the app lifetime."""

    def __init__(self) -> None:
        self._client: aiotieba.Client | None = None
        self.user_name: str = ""
        self.nick_name: str = ""

    @property
    def client(self) -> aiotieba.Client:
        if self._client is None:
            raise RuntimeError("Session not started. Call start() first.")
        return self._client

    @property
    def started(self) -> bool:
        return self._client is not None

    async def start(self, bduss: str | None = None, stoken: str | None = None) -> None:
        """Create client from args or config.yaml."""
        await self.close()
        cfg = load_config()
        bduss = (bduss if bduss is not None else cfg.get("bduss", "")).strip()
        stoken = (stoken if stoken is not None else cfg.get("stoken", "")).strip()
        if not bduss:
            raise ValueError("BDUSS is empty. Configure it in Setup.")
        self._client = aiotieba.Client(BDUSS=bduss, STOKEN=stoken or "")
        await self._client.__aenter__()

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None
            self.user_name = ""
            self.nick_name = ""

    async def verify(self) -> UserInfo:
        """Call get_self_info(); raise on failure / invalid cookie."""
        user = await self.client.get_self_info()
        # Empty / invalid cookie often returns empty-ish user
        name = getattr(user, "user_name", None) or getattr(user, "nick_name_new", None) or ""
        if not name and not getattr(user, "user_id", 0):
            raise RuntimeError("Login failed: invalid or expired BDUSS.")
        self.user_name = getattr(user, "user_name", "") or ""
        self.nick_name = (
            getattr(user, "nick_name_new", None)
            or getattr(user, "nick_name", None)
            or self.user_name
        )
        return user
