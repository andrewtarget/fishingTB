"""Download Tieba images for in-terminal preview."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from collections import OrderedDict
from pathlib import Path

import aiohttp
from PIL import Image as PILImage

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

from fishingtb.config import IMAGE_CACHE_DIR, ensure_data_layout

ensure_data_layout()
CACHE_DIR = IMAGE_CACHE_DIR

PREVIEW_MAX_SIDE = 720
TERMINAL_MAX_SIDE = PREVIEW_MAX_SIDE
FULL_MAX_SIDE = PREVIEW_MAX_SIDE
INLINE_MAX_SIDE = PREVIEW_MAX_SIDE

_FETCH_TIMEOUT = 12.0
_MEMORY_LIMIT = 48

_session: aiohttp.ClientSession | None = None
_download_sem = asyncio.Semaphore(3)
_user_fetch_sem = asyncio.Semaphore(2)
_memory: OrderedDict[str, PILImage.Image] = OrderedDict()
_bytes_warming: set[str] = set()


def clear_disk_cache() -> int:
    """Remove all cached image files on disk. Called once at program start."""
    if not CACHE_DIR.is_dir():
        return 0
    removed = 0
    for path in CACHE_DIR.glob("*.img"):
        if not path.is_file():
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    return removed


def _cache_path(url: str) -> Path:
    h = hashlib.sha1(url.encode("utf-8", errors="ignore")).hexdigest()
    return CACHE_DIR / f"{h}.img"


def _mem_get(url: str) -> PILImage.Image | None:
    img = _memory.get(url)
    if img is not None:
        _memory.move_to_end(url)
    return img


def _mem_put(url: str, img: PILImage.Image) -> None:
    _memory[url] = img
    _memory.move_to_end(url)
    while len(_memory) > _MEMORY_LIMIT:
        _memory.popitem(last=False)


def _decode_and_resize(data: bytes, max_side: int) -> PILImage.Image:
    buf = io.BytesIO(data)
    img = PILImage.open(buf)
    if max_side > 0 and img.format == "JPEG" and hasattr(img, "draft"):
        img.draft("RGB", (max_side, max_side))
    img = img.convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > max_side:
        scale = max_side / float(longest)
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            PILImage.Resampling.BILINEAR,
        )
    return img


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=12, connect=4)
        headers = {
            "User-Agent": UA,
            "Referer": "https://tieba.baidu.com/",
        }
        connector = aiohttp.TCPConnector(limit=6, ttl_dns_cache=300)
        _session = aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector,
        )
    return _session


async def close_image_client() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None
    _memory.clear()
    _bytes_warming.clear()


def _disk_cached(url: str) -> bool:
    path = _cache_path(url)
    return path.exists() and path.stat().st_size > 0


async def _read_bytes(url: str, *, priority: bool = False) -> bytes:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(url)
    if _disk_cached(url):
        return await asyncio.to_thread(path.read_bytes)

    sem = _user_fetch_sem if priority else _download_sem
    async with sem:
        if _disk_cached(url):
            return await asyncio.to_thread(path.read_bytes)
        session = await _get_session()
        async with session.get(url) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} downloading image")
            data = await resp.read()
        await asyncio.to_thread(path.write_bytes, data)
        return data


async def fetch_image(
    url: str,
    *,
    max_side: int = PREVIEW_MAX_SIDE,
    priority: bool = True,
) -> PILImage.Image:
    """Download/decode with disk + memory cache. Use priority=True when user is waiting."""
    cached = _mem_get(url)
    if cached is not None:
        return cached

    async def _do() -> PILImage.Image:
        data = await _read_bytes(url, priority=priority)
        side = min(max_side, PREVIEW_MAX_SIDE)
        img = await asyncio.to_thread(_decode_and_resize, data, side)
        _mem_put(url, img)
        return img

    return await asyncio.wait_for(_do(), timeout=_FETCH_TIMEOUT)


async def warm_image_bytes(urls: list[str], *, limit: int = 3) -> None:
    """Only fetch raw bytes to disk — cheap prefetch that helps preview open."""
    batch: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        if _disk_cached(url) or _mem_get(url) is not None:
            continue
        if url in _bytes_warming:
            continue
        batch.append(url)
        if len(batch) >= limit:
            break
    if not batch:
        return

    await asyncio.sleep(0.25)

    async def _one(u: str) -> None:
        if u in _bytes_warming:
            return
        _bytes_warming.add(u)
        try:
            await _read_bytes(u, priority=False)
        except Exception as exc:
            log.debug("warm bytes failed %s: %s", u[:48], exc)
        finally:
            _bytes_warming.discard(u)

    await asyncio.gather(*(_one(u) for u in batch))


async def prefetch_images(
    urls: list[str],
    *,
    max_side: int = PREVIEW_MAX_SIDE,
    limit: int = 2,
) -> None:
    """Decode prefetch for neighbor images (low priority)."""
    await warm_image_bytes(urls, limit=limit)
    seen: set[str] = set()
    for url in urls:
        if not url or url in seen or _mem_get(url) is not None:
            continue
        seen.add(url)
        try:
            await fetch_image(url, max_side=max_side, priority=False)
        except Exception:
            pass
        if len(seen) >= limit:
            break
