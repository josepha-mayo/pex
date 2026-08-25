export type AdapterSupportLabel =
  | "deep"
  | "strong"
  | "basic"
  | "observe_only"
  | "experimental"
  | "unavailable";

export type PetSnapshot = {
  headline: string;
  working: number;
  drifting: number;
  needs_you: number;
  sessions: Array<{
    id: string;
    harness_type: string;
    status: string;
    goal_id?: string | null;
  }>;
  ts: string;
};
