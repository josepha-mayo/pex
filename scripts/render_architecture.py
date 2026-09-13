"""Render the judge-facing PEX architecture diagram deterministically."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1600
HEIGHT = 900
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture" / "pex-architecture.png"

BG = "#071116"
PANEL = "#0b171c"
CARD = "#122229"
CORE = "#11372f"
TEXT = "#f4faf7"
MUTED = "#a9bdc1"
LINE = "#76939b"
TEAL = "#4ee0ad"
GOLD = "#d5b253"
OPTIONAL = "#28261d"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    windows = Path("C:/Windows/Fonts")
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    try:
        return ImageFont.truetype(str(windows / name), size=size)
    except OSError:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)


F_TITLE = font(42, bold=True)
F_SUBTITLE = font(20)
F_HEADING = font(22, bold=True)
F_BODY = font(17)
F_SMALL = font(15, bold=True)


def centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, face, fill: str) -> None:
    draw.text(xy, text, font=face, fill=fill, anchor="mm")


def card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    lines: list[str],
    *,
    core: bool = False,
    optional: bool = False,
) -> None:
    fill = OPTIONAL if optional else CORE if core else CARD
    outline = GOLD if optional else TEAL if core else "#55727a"
    draw.rounded_rectangle(
        box,
        radius=18,
        fill=fill,
        outline=outline,
        width=3 if core or optional else 2,
    )
    cx = (box[0] + box[2]) // 2
    content_height = 30 + len(lines) * 27
    y = (box[1] + box[3] - content_height) // 2 + 14
    centered(draw, (cx, y), title, F_HEADING, TEXT)
    for line in lines:
        y += 30
        line_color = GOLD if optional and "NOT DEPLOYED" in line else MUTED
        centered(draw, (cx, y), line, F_BODY, line_color)


def arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    *,
    color: str = LINE,
    width: int = 3,
    dashed: bool = False,
) -> None:
    if dashed:
        for start, end in zip(points, points[1:], strict=False):
            dx, dy = end[0] - start[0], end[1] - start[1]
            distance = math.hypot(dx, dy)
            if not distance:
                continue
            ux, uy = dx / distance, dy / distance
            offset = 0.0
            while offset < distance - 10:
                segment_end = min(offset + 10, distance - 10)
                draw.line(
                    (
                        start[0] + ux * offset,
                        start[1] + uy * offset,
                        start[0] + ux * segment_end,
                        start[1] + uy * segment_end,
                    ),
                    fill=color,
                    width=width,
                )
                offset += 18
    else:
        draw.line(points, fill=color, width=width, joint="curve")
    start, end = points[-2], points[-1]
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 13
    spread = 0.55
    tip = end
    left = (
        end[0] - length * math.cos(angle - spread),
        end[1] - length * math.sin(angle - spread),
    )
    right = (
        end[0] - length * math.cos(angle + spread),
        end[1] - length * math.sin(angle + spread),
    )
    draw.polygon((tip, left, right), fill=color)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, color: str = MUTED) -> None:
    bounds = draw.textbbox(xy, text, font=F_SMALL, anchor="mm")
    draw.rounded_rectangle(
        (bounds[0] - 8, bounds[1] - 4, bounds[2] + 8, bounds[3] + 4),
        radius=5,
        fill=BG,
    )
    centered(draw, xy, text, F_SMALL, color)


def render() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    draw.ellipse((48, 48, 74, 74), fill="#35ddb0")
    draw.text((88, 72), "PEX", font=F_TITLE, fill=TEXT, anchor="lm")
    draw.text(
        (190, 69),
        "the independent supervisor above your coding agents",
        font=F_SUBTITLE,
        fill=MUTED,
        anchor="lm",
    )

    card(draw, (48, 152, 348, 272), "Human", ["sets goals", "makes consequential decisions"])
    card(
        draw,
        (48, 332, 348, 466),
        "PEX desktop + pets",
        ["attach · inspect · pause", "quiet unless you are needed"],
    )
    card(
        draw,
        (48, 618, 348, 750),
        "Zen BYOK model",
        ["Muse through Strands", "credential stays in OS vault"],
    )

    draw.rounded_rectangle((398, 124, 1188, 820), radius=26, fill=PANEL, outline="#36545d", width=2)
    draw.text((438, 170), "LOCAL PEX · IMPLEMENTED", font=F_SMALL, fill=MUTED, anchor="lm")
    card(
        draw,
        (456, 206, 756, 314),
        "Bridge + adapters",
        ["authenticated worker events"],
        core=True,
    )
    card(
        draw,
        (830, 206, 1130, 314),
        "Goal-bound evidence",
        ["files · tests · progress"],
        core=True,
    )
    card(draw, (456, 405, 756, 513), "Strands supervisor", ["bounded typed proposal"], core=True)
    card(
        draw,
        (830, 405, 1130, 513),
        "Independent verifier",
        ["checks consequential corrections"],
        core=True,
    )
    card(draw, (642, 594, 942, 702), "Local policy guard", ["allow · deny · ask human"], core=True)
    card(draw, (932, 714, 1140, 796), "Audit ledger", ["goal · action · outcome"])

    card(
        draw,
        (1252, 222, 1552, 368),
        "Existing coding worker",
        ["OpenCode HTTP", "Codex App Server"],
        core=True,
    )
    card(
        draw,
        (1252, 610, 1552, 762),
        "AgentCore Runtime (optional)",
        ["implemented + locally tested", "NOT DEPLOYED"],
        optional=True,
    )

    arrow(draw, [(198, 272), (198, 332)])
    arrow(draw, [(348, 399), (432, 399), (432, 260), (456, 260)])
    label(draw, (405, 373), "goal + controls")

    arrow(draw, [(756, 260), (830, 260)], color=TEAL)
    arrow(draw, [(980, 314), (980, 362), (606, 362), (606, 405)], color=TEAL)
    arrow(draw, [(756, 459), (830, 459)], color=TEAL)
    arrow(draw, [(980, 513), (980, 565), (792, 565), (792, 594)], color=TEAL)

    arrow(
        draw,
        [(1252, 282), (1210, 282), (1210, 190), (606, 190), (606, 206)],
    )
    label(draw, (1010, 190), "observed events")
    arrow(draw, [(942, 648), (1192, 648), (1192, 332), (1252, 332)], color=TEAL)
    label(draw, (1135, 646), "authorized correction", color=TEAL)

    arrow(draw, [(642, 648), (370, 648), (370, 421), (348, 421)])
    label(draw, (454, 648), "decision needed")
    arrow(draw, [(348, 684), (432, 684), (432, 459), (456, 459)])
    label(draw, (398, 684), "inference")

    arrow(draw, [(606, 513), (606, 758), (932, 758)])
    label(draw, (722, 756), "correct → NOOP", color=TEAL)
    arrow(draw, [(942, 684), (970, 714)])

    arrow(draw, [(756, 286), (1180, 286), (1180, 686), (1252, 686)], color=GOLD, dashed=True)
    label(draw, (1205, 550), "optional remote path", color=GOLD)
    arrow(
        draw,
        [(1252, 668), (1208, 668), (1208, 540), (606, 540), (606, 513)],
        color=GOLD,
        dashed=True,
    )

    draw.text(
        (48, 850),
        "Observe → reason → verify → act → observe again",
        font=F_SUBTITLE,
        fill=MUTED,
        anchor="lm",
    )
    draw.text(
        (1552, 850),
        "Typed actions. Local policy stays authoritative.",
        font=F_SUBTITLE,
        fill=MUTED,
        anchor="rm",
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, format="PNG", optimize=True)


if __name__ == "__main__":
    render()
