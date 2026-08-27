import { useEffect, useState } from "react";
import type { PetMood } from "./types";

export type { PetMood };

export const CODEX_ROWS = [
  "idle",
  "running-right",
  "running-left",
  "waving",
  "jumping",
  "failed",
  "waiting",
  "running",
  "review",
] as const;

export type CodexRow = (typeof CODEX_ROWS)[number];

export const PEX_TO_CODEX_ROW: Record<PetMood, CodexRow> = {
  idle: "idle",
  observing: "review",
  working: "running",
  handoff: "waving",
  drift: "running-right",
  approved: "review",
  warning: "failed",
  decision: "waiting",
  degraded: "failed",
};

const CELL_W = 192;
const CELL_H = 208;

const FRAME_MS: Record<CodexRow, number[]> = {
  idle: [1680, 660, 660, 840, 840, 1920],
  "running-right": [160, 160, 160, 160, 160, 160, 160, 280],
  "running-left": [160, 160, 160, 160, 160, 160, 160, 280],
  waving: [220, 220, 220, 420],
  jumping: [400, 420, 440, 420, 780],
  failed: [180, 180, 180, 180, 180, 180, 180, 320],
  waiting: [220, 220, 220, 220, 220, 380],
  running: [160, 160, 160, 160, 160, 280],
  review: [220, 220, 220, 220, 220, 400],
};

const LOOK_ELIGIBLE: CodexRow[] = ["idle", "running", "waving", "review", "waiting"];

export function lookIndex(dx: number, dy: number, deadzone = 42): number | null {
  if (Math.hypot(dx, dy) < deadzone) return null;
  const degrees = ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360;
  return Math.round(degrees / 22.5) % 16;
}

const SHEET_COLS = 8;
const SHEET_ROWS = 11;

export function CodexSprite({
  src,
  mood,
  hop = false,
  dragDir = 0,
  look = null,
  scale = 1,
  reducedMotion = false,
}: {
  src: string;
  mood: PetMood;
  hover?: boolean;
  hop?: boolean;
  dragDir?: -1 | 0 | 1;
  look?: number | null;
  scale?: number;
  reducedMotion?: boolean;
}) {
  const underlying: CodexRow = PEX_TO_CODEX_ROW[mood];
  let rowName: CodexRow = underlying;
  if (hop) rowName = "jumping";
  else if (dragDir > 0) rowName = "running-right";
  else if (dragDir < 0) rowName = "running-left";

  const looking =
    look != null && !hop && dragDir === 0 && LOOK_ELIGIBLE.includes(underlying);
  const row = looking ? (look < 8 ? 9 : 10) : CODEX_ROWS.indexOf(rowName);
  const lookFrame = looking ? look % 8 : 0;
  const durations = FRAME_MS[rowName];
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    setFrame(0);
  }, [rowName, looking]);

  useEffect(() => {
    if (looking || reducedMotion) return;
    const ms = durations[frame] ?? durations[durations.length - 1];
    const id = window.setTimeout(() => {
      setFrame((frame + 1) % durations.length);
    }, ms);
    return () => window.clearTimeout(id);
  }, [durations, frame, looking, reducedMotion, rowName]);

  const displayW = Math.round(112 * scale);
  const displayH = Math.round(displayW * (CELL_H / CELL_W));
  const shownFrame = looking ? lookFrame : reducedMotion ? 0 : frame;
  const sheetW = displayW * SHEET_COLS;
  const sheetH = displayH * SHEET_ROWS;
  return (
    <div className="sprite-3d" style={{ width: displayW, height: displayH }}>
      <div className="sprite-clip" style={{ width: displayW, height: displayH }}>
        {src ? (
          <img
            className="sprite-sheet"
            alt=""
            draggable={false}
            src={src}
            width={sheetW}
            height={sheetH}
            style={{
              width: sheetW,
              height: sheetH,
              transform: `translate(${-shownFrame * displayW}px, ${-row * displayH}px)`,
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
