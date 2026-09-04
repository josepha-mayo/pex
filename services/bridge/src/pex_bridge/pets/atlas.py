"""Original PEX Codex-v2 spritesheets.

Geometry matches hatch-pet / pet.json: 8x11 atlas, 192x208 cells,
spriteVersionNumber 2. Art is PEX-original procedural characters — we do
not copy Codex built-in sprites.
"""

from __future__ import annotations

import math
import os
import secrets
from colorsys import hls_to_rgb, rgb_to_hls
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, UnidentifiedImageError

from pex_bridge.pets import (
    CODEX_CELL_H,
    CODEX_CELL_W,
    CODEX_COLS,
    CODEX_REQUIRED_FRAMES,
    CODEX_ROWS,
    CODEX_ROWS_V2,
    PetDefinition,
    validate_codex_v2_atlas,
)

ATLAS_W = CODEX_CELL_W * CODEX_COLS
ATLAS_H = CODEX_CELL_H * CODEX_ROWS_V2
MAX_CACHE_ATLAS_BYTES = 16 * 1024 * 1024

LOOK_ROW9 = [0.0, 22.5, 45.0, 67.5, 90.0, 112.5, 135.0, 157.5]
LOOK_ROW10 = [180.0, 202.5, 225.0, 247.5, 270.0, 292.5, 315.0, 337.5]


def _hex(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _shift(color: str, hue_deg: int) -> tuple[int, int, int]:
    r, g, b = (c / 255 for c in _hex(color))
    h, lightness, s = rgb_to_hls(r, g, b)
    h = (h + hue_deg / 360.0) % 1.0
    rr, gg, bb = hls_to_rgb(h, lightness, s)
    return int(rr * 255), int(gg * 255), int(bb * 255)


def _rgba(color: str, hue_deg: int = 0, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = _shift(color, hue_deg)
    return r, g, b, alpha


def _draw_body(
    draw: ImageDraw.ImageDraw,
    shape: str,
    cx: int,
    cy: int,
    body: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
    scale: float,
) -> None:
    w, h = int(58 * scale), int(62 * scale)
    x0, y0, x1, y1 = cx - w, cy - h, cx + w, cy + h
    if shape in {"orb", "quiet", "pulse"}:
        draw.ellipse((x0, y0, x1, y1), fill=body, outline=accent, width=3)
        if shape == "pulse":
            draw.ellipse((x0 + 14, y0 + 16, x1 - 14, y1 - 18), outline=accent, width=2)
    elif shape == "kit":
        draw.rounded_rectangle((x0, y0 + 8, x1, y1), radius=22, fill=body, outline=accent, width=3)
        ear = int(22 * scale)
        draw.polygon(
            [(x0 + 6, y0 + 18), (x0 + ear, y0 - 10), (cx - 8, y0 + 18)], fill=body, outline=accent
        )
        draw.polygon(
            [(x1 - 6, y0 + 18), (x1 - ear, y0 - 10), (cx + 8, y0 + 18)], fill=body, outline=accent
        )
    elif shape == "bot":
        draw.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=body, outline=accent, width=3)
        draw.rectangle((cx - 3, y0 - 16, cx + 3, y0), fill=accent)
        draw.ellipse((cx - 7, y0 - 24, cx + 7, y0 - 10), fill=accent)
    elif shape == "ledger":
        draw.rounded_rectangle((x0, y0, x1, y1), radius=6, fill=body, outline=accent, width=3)
        for i in range(3):
            yy = y0 + 22 + i * 16
            draw.line((x0 + 16, yy, x1 - 16, yy), fill=accent, width=2)
    elif shape == "mesh":
        draw.ellipse((x0 - 6, y0, cx + 8, y1), fill=body, outline=accent, width=2)
        draw.ellipse((cx - 8, y0 + 8, x1 + 6, y1 - 4), fill=body, outline=accent, width=2)
    elif shape == "nudge":
        draw.polygon([(cx, y0), (x1, cy), (cx, y1), (x0, cy)], fill=body, outline=accent)
    elif shape == "ember":
        draw.polygon(
            [(cx, y0 - 8), (x1, y1 - 6), (cx, y1 + 8), (x0, y1 - 6)], fill=body, outline=accent
        )
    elif shape == "spark":
        pts = []
        for i in range(8):
            ang = math.radians(i * 45 - 90)
            rad = 52 * scale if i % 2 == 0 else 28 * scale
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        draw.polygon(pts, fill=body, outline=accent)
    else:
        draw.ellipse((x0, y0, x1, y1), fill=body, outline=accent, width=3)


def _row_motion(row_name: str, frame: int) -> tuple[int, int, float, float]:
    """Return (dx, dy, scale, eye_open)."""
    t = frame / 7.0
    if row_name == "idle":
        return 0, int(math.sin(t * math.pi * 2) * 3), 1.0 + 0.03 * math.sin(t * math.pi * 2), 1.0
    if row_name == "running-right":
        return (
            int(10 + 8 * math.sin(t * math.pi * 2)),
            int(abs(math.sin(t * math.pi * 4)) * -10),
            1.0,
            1.0,
        )
    if row_name == "running-left":
        return (
            int(-10 - 8 * math.sin(t * math.pi * 2)),
            int(abs(math.sin(t * math.pi * 4)) * -10),
            1.0,
            1.0,
        )
    if row_name == "waving":
        return int(math.sin(t * math.pi * 2) * 6), -6, 1.02, 1.0
    if row_name == "jumping":
        return 0, int(-28 * math.sin(min(1.0, t) * math.pi)), 1.05, 1.0
    if row_name == "failed":
        return int(math.sin(t * math.pi * 8) * 3), 10, 0.92, 0.35
    if row_name == "waiting":
        blink = 0.15 if frame in {3, 4} else 1.0
        return 0, 4, 0.98, blink
    if row_name == "running":
        return (
            int(math.sin(t * math.pi * 2) * 4),
            int(abs(math.sin(t * math.pi * 4)) * -8),
            1.0,
            1.0,
        )
    if row_name == "review":
        return int(math.sin(t * math.pi) * 3), 0, 1.0, 1.0
    return 0, 0, 1.0, 1.0


def _draw_cell(
    canvas: Image.Image,
    pet: PetDefinition,
    col: int,
    row: int,
    row_name: str,
    look_deg: float | None,
    hue_shift: int,
) -> None:
    cell = Image.new("RGBA", (CODEX_CELL_W, CODEX_CELL_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(cell)
    dx, dy, scale, eye_open = _row_motion(row_name, col)
    if look_deg is not None:
        rad = math.radians(look_deg)
        dx += int(math.sin(rad) * 10)
        dy += int(-math.cos(rad) * 10)
        scale = 1.0
        eye_open = 1.0
    cx, cy = CODEX_CELL_W // 2 + dx, CODEX_CELL_H // 2 + 8 + dy
    body = _rgba(pet.body, hue_shift)
    accent = _rgba(pet.accent, hue_shift)
    _draw_body(draw, pet.shape, cx, cy, body, accent, scale)
    eye = _hex(pet.eye)
    ew, eh = 9, max(2, int(9 * eye_open))
    look_x = look_y = 0
    if look_deg is not None:
        rad = math.radians(look_deg)
        look_x = int(math.sin(rad) * 4)
        look_y = int(-math.cos(rad) * 4)
    for side in (-18, 18):
        ex = cx + side + look_x
        ey = cy - 8 + look_y
        draw.ellipse((ex - ew, ey - eh, ex + ew, ey + eh), fill=(*eye, 255))
        draw.ellipse(
            (ex - 3 + look_x, ey - 3 + look_y, ex + 1 + look_x, ey + 1 + look_y),
            fill=(250, 250, 250, 220),
        )
    if row_name == "waving":
        arm_y = cy - 20 - col * 3
        draw.line((cx + 40, cy, cx + 62, arm_y), fill=accent, width=6)
    if row_name == "failed":
        draw.line((cx - 28, cy - 28, cx - 12, cy - 12), fill=(240, 80, 70, 255), width=3)
        draw.line((cx - 12, cy - 28, cx - 28, cy - 12), fill=(240, 80, 70, 255), width=3)
    soft = cell.filter(ImageFilter.SMOOTH)
    canvas.paste(soft, (col * CODEX_CELL_W, row * CODEX_CELL_H), soft)


def render_atlas(pet: PetDefinition, hue_shift: int = 0) -> Image.Image:
    if (
        isinstance(hue_shift, bool)
        or not isinstance(hue_shift, int)
        or not -360 <= hue_shift <= 360
    ):
        raise ValueError("hue_shift must be an integer between -360 and 360")
    atlas = Image.new("RGBA", (ATLAS_W, ATLAS_H), (0, 0, 0, 0))
    for row, name in enumerate(CODEX_ROWS):
        looks = None
        if name == "look-9":
            looks = LOOK_ROW9
        elif name == "look-10":
            looks = LOOK_ROW10
        for col in range(CODEX_REQUIRED_FRAMES[row]):
            look = looks[col] if looks else None
            _draw_cell(atlas, pet, col, row, name if looks is None else "idle", look, hue_shift)
    return atlas


def write_atlas(pet: PetDefinition, dest: Path, hue_shift: int = 0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    image = render_atlas(pet, hue_shift)
    temporary = dest.parent / f".{dest.name}.{secrets.token_hex(8)}.tmp"
    try:
        with temporary.open("xb") as handle:
            image.save(handle, "WEBP", lossless=True, quality=95)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, dest)
    finally:
        image.close()
        temporary.unlink(missing_ok=True)
    return dest


def _cache_atlas_valid(path: Path) -> bool:
    try:
        stat = path.stat()
        if not path.is_file() or not 1 <= stat.st_size <= MAX_CACHE_ATLAS_BYTES:
            return False
        with Image.open(path) as image:
            validate_codex_v2_atlas(image, subject="cached pet atlas")
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return False
    return True


@lru_cache(maxsize=32)
def cached_bytes(pet_id: str, hue_shift: int, cache_dir: str) -> bytes:
    from pex_bridge.pets import starters_by_id

    if (
        isinstance(hue_shift, bool)
        or not isinstance(hue_shift, int)
        or not -360 <= hue_shift <= 360
    ):
        raise ValueError("hue_shift must be an integer between -360 and 360")
    pet = starters_by_id().get(pet_id)
    if pet is None:
        raise ValueError("unknown starter pet")
    path = Path(cache_dir) / f"{pet_id}_{hue_shift}.webp"
    if not _cache_atlas_valid(path):
        write_atlas(pet, path, hue_shift)
    with path.open("rb") as handle:
        data = handle.read(MAX_CACHE_ATLAS_BYTES + 1)
    if not data or len(data) > MAX_CACHE_ATLAS_BYTES:
        raise ValueError("cached pet atlas exceeded the safety bound")
    return data
