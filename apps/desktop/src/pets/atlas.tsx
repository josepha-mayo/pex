import { CSSProperties, useEffect, useState } from "react";

export type PetShape =
  | "orb"
  | "kit"
  | "bot"
  | "spark"
  | "ledger"
  | "mesh"
  | "quiet"
  | "ember"
  | "nudge"
  | "pulse";

export type PetMood =
  | "idle"
  | "observing"
  | "working"
  | "handoff"
  | "drift"
  | "approved"
  | "warning"
  | "decision"
  | "degraded";

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

export const PEX_TO_CODEX_ROW: Record<PetMood, (typeof CODEX_ROWS)[number]> = {
  idle: "idle",
  observing: "review",
  working: "running",
  handoff: "waving",
  drift: "running-right",
  approved: "jumping",
  warning: "failed",
  decision: "waiting",
  degraded: "failed",
};

const CELL_W = 192;
const CELL_H = 208;

export function atlasStyle(src: string, mood: PetMood, frame = 0, scale = 1): CSSProperties {
  const row = CODEX_ROWS.indexOf(PEX_TO_CODEX_ROW[mood]);
  const display = 54 * scale;
  return {
    width: CELL_W,
    height: CELL_H,
    backgroundImage: `url(${src})`,
    backgroundRepeat: "no-repeat",
    backgroundPosition: `-${frame * CELL_W}px -${row * CELL_H}px`,
    imageRendering: "auto",
    transform: `scale(${display / CELL_W})`,
    transformOrigin: "top left",
    flex: "none",
  };
}

export function CodexSprite({
  src,
  mood,
  scale = 1,
}: {
  src: string;
  mood: PetMood;
  scale?: number;
}) {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const ms = mood === "idle" || mood === "observing" ? 140 : 90;
    const id = window.setInterval(() => setFrame((n) => (n + 1) % 8), ms);
    return () => window.clearInterval(id);
  }, [mood]);
  const displayWidth = 54 * scale;
  const displayHeight = (CELL_H / CELL_W) * displayWidth;
  return (
    <div className="sprite-clip" style={{ width: displayWidth, height: displayHeight }}>
      <div aria-hidden="true" style={atlasStyle(src, mood, frame, scale)} />
    </div>
  );
}

export function PetFigure({
  shape,
  body,
  accent,
  mood,
}: {
  shape: PetShape;
  body: string;
  accent: string;
  mood: PetMood;
}) {
  const bounce =
    mood === "working" || mood === "drift" || mood === "handoff" ? "pet-bounce" : "pet-breathe";
  return (
    <div
      className={`figure ${shape} ${bounce}`}
      style={{ ["--body" as string]: body, ["--accent" as string]: accent }}
    >
      <span className="eye left" />
      <span className="eye right" />
    </div>
  );
}
