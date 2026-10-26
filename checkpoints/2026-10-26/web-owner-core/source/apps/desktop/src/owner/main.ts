import { createOwnerClient, type OwnerView } from "./client";
import "./owner.css";

const form = document.querySelector<HTMLFormElement>("#owner-form")!;
const input = document.querySelector<HTMLInputElement>("#owner-secret")!;
const status = document.querySelector<HTMLElement>("#status")!;
const workspace = document.querySelector<HTMLElement>("#workspace")!;
const login = document.querySelector<HTMLButtonElement>("#sign-in")!;
const logout = document.querySelector<HTMLButtonElement>("#sign-out")!;
const check = document.querySelector<HTMLButtonElement>("#check-session")!;
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
  if (!authenticated) input.value = "";
  if (expiryTimer) clearTimeout(expiryTimer);
  if (authenticated && view.expiresAt) expiryTimer = setTimeout(() => client.lock(), Math.max(0, view.expiresAt - Date.now()));
}
let client: ReturnType<typeof createOwnerClient>;
try {
  client = createOwnerClient({ origin: window.location.origin, changed: render });
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
