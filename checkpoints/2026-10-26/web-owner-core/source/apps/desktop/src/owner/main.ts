import { createOwnerClient, type OwnerView } from "./client";
import "./owner.css";
import { createWorkspaceClient, type WorkspaceView } from "./workspace";

const form = document.querySelector<HTMLFormElement>("#owner-form")!;
const input = document.querySelector<HTMLInputElement>("#owner-secret")!;
const status = document.querySelector<HTMLElement>("#status")!;
const workspace = document.querySelector<HTMLElement>("#workspace")!;
const login = document.querySelector<HTMLButtonElement>("#sign-in")!;
const logout = document.querySelector<HTMLButtonElement>("#sign-out")!;
const check = document.querySelector<HTMLButtonElement>("#check-session")!;
const refresh = document.querySelector<HTMLButtonElement>("#refresh-workspace")!;
const workspaceStatus = document.querySelector<HTMLElement>("#workspace-status")!;
const records = document.querySelector<HTMLElement>("#workspace-records")!;
let reader: ReturnType<typeof createWorkspaceClient> | undefined;
function renderWorkspace(view: WorkspaceView) {
  workspaceStatus.textContent = view.message;
  refresh.disabled = view.phase === "loading";
  records.replaceChildren();
  if (!view.data) return;
  const add = (tag: string, text: string, parent: HTMLElement = records) => {
    const element = document.createElement(tag); element.textContent = text; parent.append(element); return element;
  };
  add("small", `Observed ${view.data.observed_at}. Separate recorded reads; not an atomic live snapshot.`);
  add("h3", "Goals");
  if (!view.data.goals.length) add("p", "No recorded goals in this workspace.");
  for (const goal of view.data.goals) {
    const card = add("article", ""); card.className = "record";
    add("h4", goal.title, card);
    add("p", `${goal.paused ? "Paused · " : ""}${goal.completion.status.replaceAll("_", " ")}`, card);
    add("small", `${goal.id} · ${goal.completion.reason.replaceAll("_", " ")} · ${goal.completion.as_of}`, card);
  }
  add("h3", "Sessions");
  if (!view.data.sessions.length) add("p", "No recorded sessions in this workspace.");
  for (const session of view.data.sessions) {
    const card = add("article", ""); card.className = "record";
    add("h4", `${session.harness_type.replaceAll("_", " ")} · ${session.status.replaceAll("_", " ")}`, card);
    add("small", `${session.id} · Goal: ${session.goal_id ?? "not attached"} · Last activity: ${session.last_activity ?? "unknown"}`, card);
  }
  if (view.data.truncated.goals || view.data.truncated.sessions) add("p", "Showing the newest 20 records per section. Additional records are not displayed.");
}
let expiryTimer: ReturnType<typeof setTimeout> | null = null;
function render(view: OwnerView) {
  status.textContent = view.message;
  status.dataset.phase = view.phase;
  const authenticated = view.phase === "signed-in";
  workspace.hidden = !authenticated;
  form.hidden = authenticated || view.phase === "locked";
  login.disabled = view.phase === "checking" || view.phase === "signing-in" || view.phase === "unavailable";
  input.disabled = login.disabled;
  check.hidden = authenticated || view.phase === "signing-in" || view.phase === "checking";
  logout.hidden = !authenticated;
  if (!authenticated) { input.value = ""; reader?.lock(); }
  if (expiryTimer) clearTimeout(expiryTimer);
  if (authenticated && view.expiresAt) expiryTimer = setTimeout(() => client.lock(), Math.max(0, view.expiresAt - Date.now()));
}
let client: ReturnType<typeof createOwnerClient>;
try {
  client = createOwnerClient({ origin: window.location.origin, changed: render });
  reader = createWorkspaceClient({ origin: window.location.origin,
    authorized: () => client.state().phase === "signed-in" && (client.state().expiresAt ?? 0) > Date.now(),
    changed: renderWorkspace, denied: () => client.lock() });
  reader.lock();
  refresh.addEventListener("click", () => { void reader?.load(); });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const secret = input.value;
    input.value = "";
    void client.login(secret);
  });
  logout.addEventListener("click", () => { input.value = ""; void client.logout(); });
  check.addEventListener("click", () => { void client.check(); });
  window.addEventListener("pagehide", () => { input.value = ""; client.lock(); });
  window.addEventListener("pageshow", (event) => { if (event.persisted) void client.check(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { input.value = ""; client.lock(); }
    else void client.check();
  });
  void client.check();
} catch {
  render({ phase: "unavailable", message: "Secure HTTPS owner access is required. This page does not connect to the desktop bridge or enable providers." });
  check.hidden = true;
}
