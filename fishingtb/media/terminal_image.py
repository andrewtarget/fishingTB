"""Render PIL images in the terminal — braille / half-block / Sixel."""

from __future__ import annotations

import logging
import os

from PIL import Image as PILImage

log = logging.getLogger(__name__)

# Avoid probing stdin after Textual starts (can stall ~2s). Warm in main.py first.
_DEFAULT_CELL = (10, 20)
from rich.console import Console, ConsoleOptions, RenderResult
from rich.segment import Segment
from rich.style import Style

_RESAMPLE = PILImage.Resampling.LANCZOS

# Braille dot layout (2 wide x 4 tall per character)
_BRAILLE_BASE = 0x2800
_BRAILLE_DOTS: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0x01),
    (0, 1, 0x02),
    (0, 2, 0x04),
    (0, 3, 0x40),
    (1, 0, 0x08),
    (1, 1, 0x10),
    (1, 2, 0x20),
    (1, 3, 0x80),
)


def is_windows_terminal() -> bool:
    return bool(os.environ.get("WT_SESSION"))


def warm_terminal_probe() -> None:
    """Call once before Textual App.run() so Sixel sizing does not block later."""
    try:
        from textual_image._terminal import probe_terminal

        probe_terminal()
    except Exception as exc:
        log.debug("terminal probe skipped: %s", exc)


def _cell_size_px() -> tuple[int, int]:
    try:
        from textual_image._terminal import get_cell_size

        cs = get_cell_size()
        return max(1, cs.width), max(1, cs.height)
    except Exception:
        return _DEFAULT_CELL


def resolve_image_renderer() -> str:
    """
    Resolve config to a concrete renderer.

    Config values: auto | sixel | braille | halfblock
    auto → sixel in Windows Terminal, else braille (e.g. Cursor embedded terminal).
    """
    try:
        from fishingtb.config import load_config

        raw = str(load_config().get("image_renderer") or "auto").strip().lower()
    except Exception:
        raw = "auto"

    if raw == "auto":
        return "sixel" if is_windows_terminal() else "braille"
    if raw in ("sixel", "braille", "halfblock"):
        return raw
    return "sixel" if is_windows_terminal() else "braille"


def display_bounds(
    terminal_size: tuple[int, int],
    *,
    mode: str = "inline",
) -> tuple[int, int]:
    """Fallback cell bounds when the preview host has not laid out yet."""
    tw, th = terminal_size
    if mode == "full":
        # title + hint + toolbar + status + tall border ≈ 6 rows
        return (max(20, tw - 8), max(6, th - 10))
    return (max(60, tw - 6), max(20, min(48, int(th * 0.5))))


def contain_cell_size(
    pixel_width: int,
    pixel_height: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    """Largest cell box that fits the image inside max_width × max_height."""
    from textual_image._geometry import ImageSize
    from textual_image._terminal import get_cell_size

    mw = max(1, max_width)
    mh = max(1, max_height)
    if pixel_width <= 0 or pixel_height <= 0:
        return mw, mh
    return ImageSize(pixel_width, pixel_height, "auto", "auto").get_cell_size(
        mw, mh, get_cell_size()
    )


def _pixel_rows(img: PILImage.Image) -> list[tuple[tuple[int, int, int], ...]]:
    rgb = img.convert("RGB")
    w, h = rgb.size
    if hasattr(rgb, "get_flattened_data"):
        flat = rgb.get_flattened_data()
    else:
        flat = tuple(rgb.getdata())
    rows: list[tuple[tuple[int, int, int], ...]] = []
    for y in range(h):
        row = flat[y * w : (y + 1) * w]
        rows.append(tuple(tuple(p) for p in row))
    return rows


def _lum(r: int, g: int, b: int) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def _fit_image_halfblock(
    image: PILImage.Image,
    *,
    max_width: int,
    max_height: int,
) -> PILImage.Image:
    w, h = image.size
    if w <= 0 or h <= 0:
        return image
    max_img_h = max_height * 2
    scale = min(max_width / w, max_img_h / h, 1.0)
    if scale >= 1.0:
        nh = h if h % 2 == 0 else h + 1
        if nh != h:
            return image.resize((w, nh), _RESAMPLE)
        return image
    nw = max(1, int(w * scale))
    nh = max(2, int(h * scale))
    nh = nh if nh % 2 == 0 else nh + 1
    return image.resize((nw, nh), _RESAMPLE)


def _fit_image_braille(
    image: PILImage.Image,
    *,
    max_width: int,
    max_height: int,
) -> PILImage.Image:
    w, h = image.size
    if w <= 0 or h <= 0:
        return image
    max_img_w = max_width * 2
    max_img_h = max_height * 4
    scale = min(max_img_w / w, max_img_h / h, 1.0)
    if scale >= 1.0:
        nw = w if w % 2 == 0 else w + 1
        nh = h if h % 4 == 0 else h + (4 - h % 4)
        if (nw, nh) != (w, h):
            return image.resize((nw, nh), _RESAMPLE)
        return image
    nw = max(2, int(w * scale))
    nh = max(4, int(h * scale))
    nw = nw if nw % 2 == 0 else nw + 1
    nh = nh if nh % 4 == 0 else nh + (4 - nh % 4)
    return image.resize((nw, nh), _RESAMPLE)


def build_halfblock_lines(
    image: PILImage.Image,
    *,
    max_width: int = 80,
    max_height: int = 24,
) -> list[list[Segment]]:
    fitted = _fit_image_halfblock(image, max_width=max_width, max_height=max_height)
    rows = _pixel_rows(fitted)
    lines: list[list[Segment]] = []
    for y in range(0, len(rows) - 1, 2):
        upper = rows[y]
        lower = rows[y + 1]
        line: list[Segment] = []
        for x in range(len(upper)):
            ur, ug, ub = upper[x]
            lr, lg, lb = lower[x]
            style = Style(color=f"rgb({ur},{ug},{ub})", bgcolor=f"rgb({lr},{lg},{lb})")
            line.append(Segment("▀", style))
        lines.append(line)
    return lines


def build_braille_lines(
    image: PILImage.Image,
    *,
    max_width: int = 80,
    max_height: int = 24,
) -> list[list[Segment]]:
    """Color braille: 2x4 pixels per terminal cell (~4x denser than half-block)."""
    fitted = _fit_image_braille(image, max_width=max_width, max_height=max_height)
    rows = _pixel_rows(fitted)
    if not rows:
        return []
    h = len(rows)
    w = len(rows[0])
    lines: list[list[Segment]] = []

    for cy in range(0, h, 4):
        line: list[Segment] = []
        for cx in range(0, w, 2):
            rs = gs = bs = 0
            cnt = 0
            samples: list[tuple[int, int, int]] = []
            for dx, dy, _bit in _BRAILLE_DOTS:
                px, py = cx + dx, cy + dy
                if px < w and py < h:
                    r, g, b = rows[py][px]
                    samples.append((r, g, b))
                    rs += r
                    gs += g
                    bs += b
                    cnt += 1
            if cnt == 0:
                line.append(Segment(" "))
                continue

            ar, ag, ab = rs // cnt, gs // cnt, bs // cnt
            avg_lum = _lum(ar, ag, ab)
            bits = 0
            for dx, dy, bit in _BRAILLE_DOTS:
                px, py = cx + dx, cy + dy
                if px < w and py < h:
                    r, g, b = rows[py][px]
                    if _lum(r, g, b) < avg_lum:
                        bits |= bit

            style = Style(color=f"rgb({ar},{ag},{ab})")
            if bits == 0:
                line.append(Segment(" ", style))
            else:
                line.append(Segment(chr(_BRAILLE_BASE + bits), style))
        lines.append(line)
    return lines


class _LineImage:
    """Shared Rich renderable for precomputed segment lines."""

    def __init__(self, lines: list[list[Segment]]) -> None:
        self._lines = lines

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        if not self._lines:
            yield Segment("(empty image)")
            return
        for line in self._lines:
            for seg in line:
                yield seg
            yield Segment("\n")


class HalfBlockImage(_LineImage):
    @classmethod
    def from_pil(
        cls,
        image: PILImage.Image,
        *,
        max_width: int = 80,
        max_height: int = 24,
    ) -> HalfBlockImage:
        return cls(build_halfblock_lines(image, max_width=max_width, max_height=max_height))


class BrailleImage(_LineImage):
    @classmethod
    def from_pil(
        cls,
        image: PILImage.Image,
        *,
        max_width: int = 80,
        max_height: int = 24,
    ) -> BrailleImage:
        return cls(build_braille_lines(image, max_width=max_width, max_height=max_height))


def build_terminal_visual(
    pil: PILImage.Image,
    *,
    max_width: int,
    max_height: int,
    renderer: str,
) -> _LineImage:
    if renderer == "halfblock":
        return HalfBlockImage.from_pil(pil, max_width=max_width, max_height=max_height)
    return BrailleImage.from_pil(pil, max_width=max_width, max_height=max_height)


async def create_image_widget(
    pil: PILImage.Image,
    *,
    max_width: int,
    max_height: int,
    renderer: str | None = None,
    mode: str = "inline",
):
    """
    Build a Textual image widget on the UI thread.
    Heavy work runs in a worker thread; widgets stay on the main thread.

    full + sixel: use textual_image SixelImage widget (correct cursor positioning).
    Preview uses contain downscale (full image fits in max_width × max_height).
    """
    import asyncio

    from textual.widgets import Static

    renderer = renderer or resolve_image_renderer()

    if renderer == "sixel" and mode == "full":
        try:
            small = await asyncio.wait_for(
                asyncio.to_thread(
                    _downscale_for_sixel,
                    pil,
                    max_width=max_width,
                    max_height=max_height,
                ),
                timeout=6.0,
            )
            from textual_image.widget import SixelImage

            widget = SixelImage(small)
            # Lock widget to contain size so Sixel cannot grow past the host and get clipped.
            cw, ch = contain_cell_size(
                small.width, small.height, max_width, max_height
            )
            widget.styles.width = cw
            widget.styles.height = ch
            return widget
        except Exception as exc:
            log.warning("Sixel widget failed, fallback to braille: %s", exc)
            renderer = "braille"

    visual = await asyncio.wait_for(
        asyncio.to_thread(
            build_terminal_visual,
            pil,
            max_width=max_width,
            max_height=max_height,
            renderer=renderer,
        ),
        timeout=8.0,
    )
    return Static(visual, markup=False, expand=True)


def _downscale_for_sixel(
    pil: PILImage.Image,
    *,
    max_width: int,
    max_height: int,
) -> PILImage.Image:
    """Shrink before Sixel encode — large PIL images make encoding very slow."""
    cw, ch = _cell_size_px()
    cap_w = max(1, max_width * cw)
    cap_h = max(1, max_height * ch)

    w, h = pil.size
    scale = min(cap_w / w, cap_h / h, 1.0)
    if scale >= 1.0:
        return pil
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    return pil.resize((nw, nh), PILImage.Resampling.BILINEAR)


class _FrozenSixel:
    """Sixel data pre-encoded in a worker thread to avoid UI stalls."""

    def __init__(self, sixel_data: str, cell_width: int, cell_height: int) -> None:
        self._sixel_data = sixel_data
        self._cell_width = cell_width
        self._cell_height = cell_height

    def cleanup(self) -> None:
        pass

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        from rich.control import Control
        from rich.segment import ControlType, Segment

        null_control = [(ControlType.CURSOR_FORWARD, 0)]
        for _ in range(self._cell_height):
            yield Segment(" " * self._cell_width + "\n")
        yield Segment("\x1b7", control=null_control)
        yield Control.move(0, -self._cell_height)
        yield Segment(self._sixel_data, control=null_control)
        yield Segment("\x1b8", control=null_control)

    def __rich_measure__(self, console: Console, options: ConsoleOptions):
        from rich.measure import Measurement

        return Measurement(self._cell_width, self._cell_width)


def _build_sixel_visual(
    pil: PILImage.Image,
    *,
    max_width: int,
    max_height: int,
):
    try:
        from textual_image._geometry import ImageSize
        from textual_image._pixeldata import PixelData
        from textual_image._sixel import image_to_sixels
        from textual_image._terminal import get_cell_size

        small = _downscale_for_sixel(pil, max_width=max_width, max_height=max_height)
        terminal_sizes = get_cell_size()
        render_size = ImageSize(small.width, small.height, max_width, max_height)
        cell_w, cell_h = render_size.get_cell_size(
            max_width, max_height, terminal_sizes
        )
        pixel_w, pixel_h = render_size.get_pixel_size(
            max_width, max_height, terminal_sizes
        )
        scaled = PixelData(small).scaled(pixel_w, pixel_h)
        sixel_data = image_to_sixels(scaled.pil_image)
        return _FrozenSixel(sixel_data, cell_w, cell_h)
    except Exception:
        return None


def _try_sixel_widget(
    pil: PILImage.Image,
    *,
    max_width: int,
    max_height: int,
):
    visual = _build_sixel_visual(pil, max_width=max_width, max_height=max_height)
    if visual is None:
        return None
    from textual.widgets import Static

    return Static(visual, markup=False, expand=True)


def build_image_widget(
    pil: PILImage.Image,
    *,
    max_width: int,
    max_height: int,
    renderer: str | None = None,
    mode: str = "inline",
):
    """Sync helper for tests."""
    from textual.widgets import Static

    renderer = renderer or resolve_image_renderer()
    if renderer == "sixel" and mode == "full":
        widget = _try_sixel_widget(pil, max_width=max_width, max_height=max_height)
        if widget is not None:
            return widget
        renderer = "braille"

    visual = build_terminal_visual(
        pil,
        max_width=max_width,
        max_height=max_height,
        renderer=renderer,
    )
    return Static(visual, markup=False, expand=True)


def mount_terminal_image(
    pil: PILImage.Image,
    *,
    max_width: int = 80,
    max_height: int = 24,
    renderer: str | None = None,
):
    return build_image_widget(
        pil,
        max_width=max_width,
        max_height=max_height,
        renderer=renderer,
    )
