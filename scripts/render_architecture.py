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
        line_color = GOLD if optional and ("NOT DEPLOYED" in line or "KEY-GATED" in line) else MUTED
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

    card(draw, (48, 152, 348, 272), "Human", ["seals goals", "rules on escalations"])
    card(
        draw,
        (48, 332, 348, 466),
        "PEX desktop",
        ["Command Deck · Inspector · Pet", "replay · rulings · evidence packs"],
    )
    card(
        draw,
        (48, 618, 348, 750),
        "Nebius Token Factory",
        ["NVIDIA Nemotron model", "supervisor inference · key-gated"],
    )

    draw.rounded_rectangle((398, 124, 1188, 820), radius=26, fill=PANEL, outline="#36545d", width=2)
    draw.text((438, 170), "LOCAL PEX · IMPLEMENTED", font=F_SMALL, fill=MUTED, anchor="lm")
    card(
        draw,
        (448, 196, 672, 296),
        "Bridge + adapters",
        ["authenticated worker events"],
        core=True,
    )
    card(
        draw,
        (692, 196, 916, 296),
        "Sealed acceptance",
        ["baseline snapshot at attach"],
        core=True,
    )
    card(
        draw,
        (936, 196, 1160, 296),
        "Claim ledger",
        ["narration is signal", "never proof"],
        core=True,
    )
    card(
        draw,
        (448, 380, 672, 480),
        "Strands supervisor",
        ["semantic proposal on", "redacted evidence"],
        core=True,
    )
    card(
        draw,
        (692, 380, 916, 480),
        "Independent verifier",
        ["files · diffs · test exits", "staleness · tamper"],
        core=True,
    )
    card(
        draw,
        (936, 380, 1160, 480),
        "MCP server /mcp/",
        ["8 tools · 5 scopes", "session-bound credentials"],
        core=True,
    )
    card(draw, (448, 564, 672, 664), "Local policy guard", ["nudge · ask human · noop"], core=True)
    card(draw, (692, 564, 916, 664), "Audit ledger", ["claims · interventions", "rulings"])
    card(
        draw,
        (936, 564, 1160, 664),
        "Replay pipeline",
        ["deterministic trajectories", "not live control"],
        core=True,
    )

    card(
        draw,
        (1252, 190, 1552, 336),
        "Existing coding worker",
        ["OpenCode serve", "Codex App Server"],
        core=True,
    )
    card(
        draw,
        (1252, 480, 1552, 580),
        "AgentCore Runtime",
        ["implemented + locally tested", "NOT DEPLOYED"],
        optional=True,
    )
    card(
        draw,
        (1252, 620, 1552, 700),
        "Nebius ConTree",
        ["isolated pytest VMs", "KEY-GATED (beta)"],
        optional=True,
    )
    card(
        draw,
        (1252, 740, 1552, 830),
        "Tavily web evidence",
        ["public-claim checks", "KEY-GATED"],
        optional=True,
    )

    arrow(draw, [(198, 272), (198, 332)])
    arrow(draw, [(348, 399), (430, 399), (430, 246), (448, 246)])
    label(draw, (400, 385), "sealed goal + rulings")

    arrow(draw, [(672, 246), (692, 246)], color=TEAL)
    arrow(draw, [(916, 246), (936, 246)], color=TEAL)
    arrow(draw, [(990, 296), (990, 345), (804, 345), (804, 380)], color=TEAL)
    label(draw, (895, 339), "claims extracted")
    arrow(draw, [(692, 430), (672, 430)], color=TEAL)
    arrow(draw, [(580, 480), (580, 564)], color=TEAL)
    label(draw, (648, 522), "typed action")
    arrow(draw, [(672, 614), (692, 614)])
    arrow(draw, [(1048, 564), (1048, 540), (804, 540), (804, 480)], color=TEAL)
    label(draw, (925, 532), "recorded trajectories")
    arrow(draw, [(1048, 380), (1048, 296)])
    label(draw, (1048, 318), "scoped writes")

    arrow(draw, [(1252, 232), (1210, 232), (1210, 150), (560, 150), (560, 196)])
    label(draw, (880, 144), "observed events")
    arrow(draw, [(1402, 336), (1402, 430), (1160, 430)], color=TEAL)
    label(draw, (1285, 422), "8 tools · session-bound", color=TEAL)
    arrow(draw, [(560, 664), (560, 722), (1210, 722), (1210, 290), (1252, 290)], color=TEAL)
    label(draw, (880, 714), "authorized correction", color=TEAL)

    arrow(draw, [(448, 614), (382, 614), (382, 421), (348, 421)])
    label(draw, (414, 606), "decision needed")
    arrow(draw, [(500, 480), (500, 502), (370, 502), (370, 684), (348, 684)])
    label(draw, (435, 496), "model inference")

    arrow(draw, [(560, 196), (560, 132), (1430, 132), (1430, 480)], color=GOLD, dashed=True)
    label(draw, (990, 126), "optional remote path", color=GOLD)
    arrow(
        draw,
        [(1252, 530), (1245, 530), (1245, 556), (620, 556), (620, 480)],
        color=GOLD,
        dashed=True,
    )
    arrow(
        draw,
        [(916, 400), (928, 400), (928, 355), (1240, 355), (1240, 660), (1252, 660)],
        color=GOLD,
        dashed=True,
    )
    label(draw, (1085, 349), "isolated pytest", color=GOLD)
    arrow(
        draw,
        [(672, 462), (685, 462), (685, 505), (1230, 505), (1230, 785), (1252, 785)],
        color=GOLD,
        dashed=True,
    )
    label(draw, (950, 499), "bounded web evidence", color=GOLD)

    draw.text(
        (48, 850),
        "Worker claims → sealed surface → evidence → verdict → durable ruling",
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
