"""Baidu Tieba QR-code login → BDUSS (+ tieba STOKEN)."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote

import aiohttp

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
TPL = "tb"  # Tieba passport template


class QRLoginError(RuntimeError):
    pass


class QRLoginCancelled(QRLoginError):
    pass


class QRLoginTimeout(QRLoginError):
    pass


@dataclass
class LoginTokens:
    bduss: str
    stoken: str = ""
    display_name: str = ""


ProgressCb = Callable[[str], object]
QrReadyCb = Callable[[str], object]


def _gid() -> str:
    return str(uuid.uuid4()).upper()


def _tt() -> str:
    return str(int(time.time() * 1000))


def _strip_jsonp(text: str) -> str:
    text = text.strip()
    m = re.match(r"^[^(]*\((.*)\)\s*;?\s*$", text, re.S)
    if m:
        return m.group(1)
    return text


async def _maybe_progress(cb: ProgressCb | None, msg: str) -> None:
    if cb is None:
        return
    result = cb(msg)
    if asyncio.iscoroutine(result):
        await result



async def fetch_qr(session: aiohttp.ClientSession, gid: str) -> tuple[str, str]:
    """Return (qr_image_url, sign)."""
    callback = f"tangram_guid_{_tt()}"
    params = {
        "lp": "pc",
        "qrloginfrom": "pc",
        "gid": gid,
        "callback": callback,
        "apiver": "v3",
        "tt": _tt(),
        "tpl": TPL,
        "_": _tt(),
    }
    async with session.get(
        "https://passport.baidu.com/v2/api/getqrcode",
        params=params,
    ) as resp:
        text = await resp.text()
    data = json.loads(_strip_jsonp(text))
    if int(data.get("errno", -1)) != 0 or not data.get("sign"):
        raise QRLoginError(f"Failed to get QR code: {data}")
    img = data.get("imgurl") or ""
    if img.startswith("//"):
        img = "https:" + img
    elif img.startswith("passport."):
        img = "https://" + img
    elif not img.startswith("http"):
        img = "https://passport.baidu.com/v2/api/qrcode?sign=" + data["sign"] + "&lp=pc"
    return img, data["sign"]


async def poll_scan(
    session: aiohttp.ClientSession,
    sign: str,
    gid: str,
    *,
    timeout: float = 180.0,
    interval: float = 1.5,
    progress: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    """Poll until user confirms scan; return channel_v.v (login ticket)."""
    deadline = time.monotonic() + timeout
    last_status: int | None = None
    while time.monotonic() < deadline:
        if should_cancel and should_cancel():
            raise QRLoginCancelled("Login cancelled")
        params = {
            "channel_id": sign,
            "tpl": TPL,
            "gid": gid,
            "callback": "",
            "apiver": "v3",
            "tt": _tt(),
            "_": _tt(),
        }
        async with session.get(
            "https://passport.baidu.com/channel/unicast",
            params=params,
        ) as resp:
            text = await resp.text()
        try:
            data = json.loads(_strip_jsonp(text))
        except json.JSONDecodeError:
            await asyncio.sleep(interval)
            continue

        errno = int(data.get("errno", 1))
        if errno == 1:
            # waiting for scan
            if last_status != -1:
                await _maybe_progress(progress, "Waiting for phone scan…")
                last_status = -1
            await asyncio.sleep(interval)
            continue

        channel_v = data.get("channel_v")
        if not channel_v:
            await asyncio.sleep(interval)
            continue
        if isinstance(channel_v, str):
            channel_v = json.loads(channel_v)
        status = int(channel_v.get("status", -1))
        if status == 1:
            if last_status != 1:
                await _maybe_progress(progress, "Scanned — confirm login on phone…")
                last_status = 1
            await asyncio.sleep(interval)
            continue
        if status == 0:
            v = channel_v.get("v")
            if not v:
                raise QRLoginError("Scan succeeded but ticket missing")
            await _maybe_progress(progress, "Confirmed — fetching tokens…")
            return str(v)
        # expired / cancelled
        if status in (2, 3):
            raise QRLoginError("QR code expired or cancelled — try again")
        await asyncio.sleep(interval)

    raise QRLoginTimeout("QR login timed out")


def _parse_stoken_list(raw: str) -> str:
    """Extract tieba (tb#) stoken from passport stokenList JSON string."""
    if not raw:
        return ""
    text = unquote(raw)
    # stokenList looks like: ["tb#XXXX","pp#YYYY",...]
    m = re.search(r"tb#([A-Za-z0-9]+)", text)
    if m:
        return m.group(1)
    return ""


async def exchange_ticket(
    session: aiohttp.ClientSession,
    ticket: str,
) -> LoginTokens:
    """Exchange scan ticket for BDUSS / STOKEN cookies."""
    from yarl import URL

    params = {
        "v": _tt(),
        "bduss": ticket,
        "u": "https://tieba.baidu.com/",
        "loginVersion": "v4",
        "qrcode": "1",
        "tpl": TPL,
        "apiver": "v3",
        "tt": _tt(),
        "time": str(int(time.time())),
        "alg": "v3",
        "callback": "bd__cbs__qrlogin",
    }
    async with session.get(
        "https://passport.baidu.com/v3/login/main/qrbdusslogin",
        params=params,
    ) as resp:
        text = await resp.text()

    def _cookies_for(url: str) -> dict[str, str]:
        jar = session.cookie_jar.filter_cookies(URL(url))
        return {k: morsel.value for k, morsel in jar.items()}

    cookies = _cookies_for("https://passport.baidu.com/")
    cookies.update(_cookies_for("https://www.baidu.com/"))
    cookies.update(_cookies_for("https://tieba.baidu.com/"))

    bduss = cookies.get("BDUSS", "")
    display = ""
    stoken = cookies.get("STOKEN", "")

    try:
        payload = json.loads(_strip_jsonp(text))
        data = payload.get("data") or {}
        session_info = data.get("session") or {}
        user = data.get("user") or {}
        if not bduss:
            bduss = str(session_info.get("bduss") or "")
        display = str(
            user.get("displayName")
            or user.get("username")
            or data.get("userName")
            or ""
        )
        tb_token = _parse_stoken_list(str(session_info.get("stokenList") or ""))
        if tb_token:
            stoken = tb_token
        elif session_info.get("stoken") and not stoken:
            stoken = str(session_info["stoken"])
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

    if not bduss:
        raise QRLoginError("Login response missing BDUSS")

    if not stoken:
        async with session.get("https://tieba.baidu.com/") as resp:
            await resp.text()
        tieba_cookies = _cookies_for("https://tieba.baidu.com/")
        stoken = tieba_cookies.get("STOKEN", "") or stoken

    return LoginTokens(bduss=bduss, stoken=stoken or "", display_name=display)


async def qr_login(
    *,
    timeout: float = 180.0,
    progress: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_qr_ready: QrReadyCb | None = None,
) -> LoginTokens:
    """
    Full QR login flow:
    1. Fetch QR → optionally open in system browser
    2. Poll until phone confirms
    3. Return BDUSS + STOKEN
    """
    timeout_total = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": UA, "Referer": "https://tieba.baidu.com/"}
    async with aiohttp.ClientSession(headers=headers, timeout=timeout_total) as session:
        gid = _gid()
        await _maybe_progress(progress, "正在获取二维码…")
        img_url, sign = await fetch_qr(session, gid)
        if on_qr_ready is not None:
            result = on_qr_ready(img_url)
            if asyncio.iscoroutine(result):
                await result
        await _maybe_progress(
            progress,
            "二维码已在终端弹窗显示，请用百度 App 扫码\n"
            "关闭弹窗不影响等待扫码",
        )

        ticket = await poll_scan(
            session,
            sign,
            gid,
            timeout=timeout,
            progress=progress,
            should_cancel=should_cancel,
        )
        tokens = await exchange_ticket(session, ticket)
        await _maybe_progress(
            progress,
            f"Login OK · {tokens.display_name or 'user'}",
        )
        return tokens
