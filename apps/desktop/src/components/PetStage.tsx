import { type MouseEvent, type PointerEvent, useEffect, useRef, useState } from "react";

import { CodexSprite, lookIndex, type PetMood } from "../pets/atlas";
import { startPetDrag } from "../releasePet";
import type { StatusCopy } from "../types";

const HOP_DWELL_MS = 800;
const HOP_PLAY_MS = 2460;

export function PetStage({
  name,
  sheet,
  mood,
  scale,
  reducedMotion,
  overlay = false,
  status,
  onActivate,
}: {
  name: string;
  sheet: string;
  mood: PetMood;
  scale: number;
  reducedMotion: boolean;
  overlay?: boolean;
  status?: StatusCopy;
  onActivate: () => void;
}) {
  const [hop, setHop] = useState(false);
  const [dragDir, setDragDir] = useState<-1 | 0 | 1>(0);
  const [look, setLook] = useState<number | null>(null);
  const actor = useRef<HTMLButtonElement>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);
  const hopDwell = useRef<number | null>(null);
  const hopPlay = useRef<number | null>(null);
  const lookDebounce = useRef<number | null>(null);

  function clearTimers() {
    if (hopDwell.current != null) window.clearTimeout(hopDwell.current);
    if (hopPlay.current != null) window.clearTimeout(hopPlay.current);
    if (lookDebounce.current != null) window.clearTimeout(lookDebounce.current);
    hopDwell.current = null;
    hopPlay.current = null;
    lookDebounce.current = null;
  }

  useEffect(() => clearTimers, []);

  function onPointerEnter() {
    clearTimers();
    hopDwell.current = window.setTimeout(() => {
      setHop(true);
      hopPlay.current = window.setTimeout(() => setHop(false), HOP_PLAY_MS);
    }, HOP_DWELL_MS);
  }

  function resetPointer() {
    clearTimers();
    setHop(false);
    setLook(null);
    setDragDir(0);
    dragStart.current = null;
  }

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    dragStart.current = { x: event.clientX, y: event.clientY };
    dragged.current = false;
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>) {
    const box = actor.current?.getBoundingClientRect();
    if (box) {
      const next = lookIndex(
        event.clientX - (box.left + box.width / 2),
        event.clientY - (box.top + box.height / 2),
      );
      if (lookDebounce.current != null) window.clearTimeout(lookDebounce.current);
      lookDebounce.current = window.setTimeout(() => setLook(next), 90);
    }
    const start = dragStart.current;
    if (!start || event.buttons !== 1) return;
    const dx = event.clientX - start.x;
    if (Math.abs(dx) <= 6) return;
    const startingDrag = !dragged.current;
    dragged.current = true;
    setDragDir(dx > 0 ? 1 : -1);
    if (overlay && startingDrag) void startPetDrag();
  }

  function onPointerUp() {
    const wasDrag = dragged.current;
    dragStart.current = null;
    dragged.current = false;
    setDragDir(0);
    if (!wasDrag) onActivate();
  }

  function onClick(event: MouseEvent<HTMLButtonElement>) {
    // Pointer activation is handled on pointer-up so a drag never opens PEX.
    // Keyboard-generated button clicks have detail=0 and still need to work.
    if (event.detail === 0) onActivate();
  }

  return (
    <div className={`pet-stage ${overlay ? "pet-stage-overlay" : ""}`}>
      <button
        ref={actor}
        type="button"
        className={`pet-actor mood-${mood}`}
        aria-label={`${name}. ${status ? `${status.label}. ${status.detail}` : ""} ${overlay ? "Open PEX inspector, then command deck" : "Inspect current work"}.`.replaceAll(/\s+/g, " ").trim()}
        onPointerEnter={onPointerEnter}
        onPointerLeave={resetPointer}
        onPointerCancel={resetPointer}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={onClick}
      >
        {sheet ? (
          <CodexSprite
            src={sheet}
            mood={mood}
            hop={hop}
            dragDir={dragDir}
            look={look}
            scale={overlay ? Math.max(scale, 1.04) : scale}
            reducedMotion={reducedMotion}
          />
        ) : (
          <span className="pet-fallback" aria-hidden="true">P</span>
        )}
        <span className="pet-name">{name}</span>
      </button>
      {status ? (
        <button type="button" className="activity-bubble" onClick={onActivate} aria-live="polite">
          <span className="status-dot" aria-hidden="true" />
          <span>
            <strong>{status.label}</strong>
            <small>{status.detail}</small>
          </span>
          <span className="bubble-action">Inspect</span>
        </button>
      ) : null}
    </div>
  );
}
