// Recorded supervision replays: the demo bridge can inject a bounded fixture
// trajectory through the real pipeline so the supervision loop is visible
// without a worker install. Every surface labels the result as a replay —
// never a live worker and never a benchmark result.

import type { SessionRow } from "./types.ts";

export type DemoFixture = {
  id: string;
  title: string;
};

// A fixture id is bridge-minted and bounded; arbitrary strings are refused
// before any request so a poisoned listing cannot reach the replay route.
const FIXTURE_ID = /^[a-z0-9][a-z0-9_-]{0,62}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseFixture(raw: unknown): DemoFixture | null {
  if (!isRecord(raw)) return null;
  const { id, title } = raw;
  if (typeof id !== "string" || !FIXTURE_ID.test(id)) return null;
  if (typeof title !== "string" || !title.trim()) return null;
  return { id, title: title.trim() };
}

// The replay surface exists only while the bridge honestly advertises it: a
// missing route, an unlabeled payload, or a single malformed fixture removes
// the control entirely rather than offering a partial demo.
export function parseTrajectoriesResponse(payload: unknown): DemoFixture[] | null {
  if (!isRecord(payload)) return null;
  if (payload.replay !== true || payload.not_live_control !== true) return null;
  if (!Array.isArray(payload.fixtures)) return null;
  const fixtures: DemoFixture[] = [];
  for (const raw of payload.fixtures) {
    const fixture = parseFixture(raw);
    if (!fixture) return null;
    fixtures.push(fixture);
  }
  return fixtures.length ? fixtures : null;
}

export function parseReplaySessionId(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  if (payload.replay !== true || payload.not_live_control !== true) return null;
  const { session_id: sessionId } = payload;
  return typeof sessionId === "string" && sessionId.trim() ? sessionId.trim() : null;
}

export function isReplaySession(session: SessionRow | null | undefined): boolean {
  return session?.metadata?.replay === true && session?.metadata?.not_live_control === true;
}
