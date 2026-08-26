import { CSSProperties, useEffect, useState } from "react";
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
  "running-right": [120, 120, 120, 120, 120, 120, 120, 220],
  "running-left": [120, 120, 120, 120, 120, 120, 120, 220],
  waving: [140, 140, 140, 280],
  jumping: [140, 140, 140, 140, 280],
  failed: [140, 140, 140, 140, 140, 140, 140, 240],
  waiting: [150, 150, 150, 150, 150, 260],
  running: [120, 120, 120, 120, 120, 220],
  review: [150, 150, 150, 150, 150, 280],
};

const LOOK_ELIGIBLE: CodexRow[] = ["idle", "running", "waving"];

export function lookIndex(dx: number, dy: number, deadzone = 28): number | null {
  if (Math.hypot(dx, dy) < deadzone) return null;
  const degrees = ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360;
  return Math.round(degrees / 22.5) % 16;
}

function atlasStyle(src: string, row: number, frame: number, display: number): CSSProperties {
  const scale = display / CELL_W;
  return {
    width: CELL_W,
    height: CELL_H,
    backgroundImage: `url(${src})`,
    backgroundRepeat: "no-repeat",
    backgroundPosition: `-${frame * CELL_W}px -${row * CELL_H}px`,
    imageRendering: "auto",
    transform: `scale(${scale})`,
    transformOrigin: "top left",
    flex: "none",
  };
}

export function CodexSprite({
  src,
  mood,
  hover = false,
  dragDir = 0,
  look = null,
  scale = 1,
  reducedMotion = false,
}: {
  src: string;
  mood: PetMood;
  hover?: boolean;
  dragDir?: -1 | 0 | 1;
  look?: number | null;
  scale?: number;
  reducedMotion?: boolean;
}) {
  const underlying: CodexRow = PEX_TO_CODEX_ROW[mood];
  let rowName: CodexRow = underlying;
  if (hover) rowName = "jumping";
  else if (dragDir > 0) rowName = "running-right";
  else if (dragDir < 0) rowName = "running-left";

  const looking =
    look != null && !hover && dragDir === 0 && LOOK_ELIGIBLE.includes(underlying);
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

  const display = Math.round(112 * scale);
  const shownFrame = looking ? lookFrame : reducedMotion ? 0 : frame;
  if (!src) {
    return <div className="sprite-clip" style={{ width: display, height: Math.round(display * (CELL_H / CELL_W)) }} />;
  }
  return (
    <div className="sprite-clip" style={{ width: display, height: Math.round(display * (CELL_H / CELL_W)) }}>
      <div aria-hidden="true" style={atlasStyle(src, row, shownFrame, display)} />
    </div>
  );
}
