import { useEffect, useState, type ReactNode } from "react";
import type { SupervisorAuthMode, SupervisorProtocol, SupervisorCredentialAction } from "../supervisorDraft";
import type {
  Goal,
  HatchCap,
  HatchJobRow,
  ChannelHubStatus,
  SupervisorInfo,
} from "../types";
import {
  channelStatusCopy,
  HATCH_BASE_CANDIDATE_CONFIRMATION,
  HATCH_BASE_CANDIDATE_DISCLOSURE,
  HATCH_EXTERNAL_IMPORT_DISCLOSURE,
  supervisorHonestyCopy,
} from "../viewModel";

type HookHarness = "cursor" | "claude_code" | "qwen" | "hermes" | "opencode";
type SettingsSection = "companion" | "supervisor" | "connections" | "goals";

export function SettingsPage({
  goals,
  note,
  nickname,
  scale,
  clickThrough,
  petVisible,
  supervisor,
  supervisorProvider,
  supervisorModel,
  supervisorAuth,
  supervisorProtocol,
  supervisorBaseUrl,
  supervisorApiKey,
  supervisorCredentialAction,
  channels,
  settingsAvailable,
  settingsIssue,
  savingSupervisor,
  refreshingCatalog,
  hatchCap,
  hatchJobs,
  hatchName,
  hatchNotes,
  hatchStyle,
  hatchOneCallConfirmed,
  hatching,
  importDir,
  hookHarness,
  hookProject,
  hookEnvironment,
  hookCredential,
  hookCredentialExpiresAt,
  provisioningHook,
  companionRoster,
  workerConnection,
  onBack,
  onNickname,
  onScale,
  onClickThrough,
  onPetVisible,
  onSaveAppearance,
  onSupervisorProvider,
  onSupervisorModel,
  onSupervisorAuth,
  onSupervisorProtocol,
  onSupervisorBaseUrl,
  onSupervisorApiKey,
  onSupervisorCredentialAction,
  onSaveSupervisor,
  onReloadSettings,
  onRefreshCatalog,
  onHatchName,
  onHatchNotes,
  onHatchStyle,
  onHatchOneCallConfirmed,
  onHatch,
  onImportDir,
  onImport,
  onHookHarness,
  onHookProject,
  onProvisionHook,
  onCopyHook,
  onClearHook,
}: {
  goals: Goal[];
  note?: string | null;
  nickname: string;
  scale: number;
  clickThrough: boolean;
  petVisible: boolean;
  supervisor: SupervisorInfo | null;
  supervisorProvider: string;
  supervisorModel: string;
  supervisorAuth: SupervisorAuthMode;
  supervisorProtocol: SupervisorProtocol;
  supervisorBaseUrl: string;
  supervisorApiKey: string;
  supervisorCredentialAction: SupervisorCredentialAction;
  channels: ChannelHubStatus | null;
  settingsAvailable: boolean;
  settingsIssue?: string | null;
  savingSupervisor: boolean;
  refreshingCatalog: boolean;
  hatchCap: HatchCap | null;
  hatchJobs: HatchJobRow[];
  hatchName: string;
  hatchNotes: string;
  hatchStyle: string;
  hatchOneCallConfirmed: boolean;
  hatching: boolean;
  importDir: string;
  hookHarness: HookHarness;
  hookProject: string;
  hookEnvironment: string;
  hookCredential: string;
  hookCredentialExpiresAt: string;
  provisioningHook: boolean;
  companionRoster?: ReactNode;
  workerConnection?: ReactNode;
  onBack: () => void;
  onNickname: (value: string) => void;
  onScale: (value: number) => void;
  onClickThrough: (value: boolean) => void;
  onPetVisible: (value: boolean) => void;
  onSaveAppearance: () => void;
  onSupervisorProvider: (value: string) => void;
  onSupervisorModel: (value: string) => void;
  onSupervisorAuth: (value: SupervisorAuthMode) => void;
  onSupervisorProtocol: (value: SupervisorProtocol) => void;
  onSupervisorBaseUrl: (value: string) => void;
  onSupervisorApiKey: (value: string) => void;
  onSupervisorCredentialAction: (value: SupervisorCredentialAction) => void;
  onSaveSupervisor: () => void;
  onReloadSettings: () => void;
  onRefreshCatalog: () => void;
  onHatchName: (value: string) => void;
  onHatchNotes: (value: string) => void;
  onHatchStyle: (value: string) => void;
  onHatchOneCallConfirmed: (value: boolean) => void;
  onHatch: () => void;
  onImportDir: (value: string) => void;
  onImport: () => void;
  onHookHarness: (value: HookHarness) => void;
  onHookProject: (value: string) => void;
  onProvisionHook: () => void;
  onCopyHook: () => void;
  onClearHook: () => void;
}) {
  const sections: SettingsSection[] = ["companion", "supervisor", "connections", "goals"];
  const [section, setSection] = useState<SettingsSection>(
    settingsAvailable && !settingsIssue && supervisor?.model_loaded ? "companion" : "supervisor",
  );
  useEffect(() => {
    if (settingsIssue || !settingsAvailable) setSection("supervisor");
  }, [settingsAvailable, settingsIssue]);
  const providers = Array.from(
    new Set([
      ...(supervisor?.providers || []),
      ...(supervisor?.catalog || []).map((row) => row.provider),
    ]),
  );
  const visibleCatalog = (supervisor?.catalog || []).filter(
    (row) => !supervisorProvider || row.provider === supervisorProvider,
  );
  const inCatalog = visibleCatalog.some((row) => row.model_id === supervisorModel);
  const catalogIsLive = visibleCatalog.length > 0 && visibleCatalog.every(
    (row) => row.source === "live_provider_list",
  );
  const supervisorAuthOptions: SupervisorAuthMode[] = supervisorProvider === "custom"
    ? ["custom", "api_key"]
    : ["ollama", "lmstudio", "llamacpp", "vllm"].includes(supervisorProvider)
      ? ["local"]
      : supervisorProvider === "bedrock"
        ? ["bedrock", "agentcore"]
        : ["api_key", "login"];
  const supervisorUsesCredential = ["api_key", "custom"].includes(supervisorAuth);

  return (
    <main
      className="main-shell settings-shell surface-focus-target"
      data-settings-root="true"
      tabIndex={-1}
    >
      <header className="topbar">
        <button type="button" className="ghost" onClick={onBack}>← Back</button>
        <span className="wordmark">PEX</span>
        <span className="topbar-state">Settings</span>
      </header>
      <div className="settings-page">
        <header className="surface-heading">
          <div>
            <p className="eyebrow">Local companion</p>
            <h1>Settings</h1>
            <p>Appearance, supervisor inference, and pet sources. Credentials stay in the local environment or secret store.</p>
          </div>
        </header>

        <nav className="settings-sections" aria-label="Settings sections" role="tablist">
          {sections.map((item, index) => (
            <button
              type="button"
              id={`settings-tab-${item}`}
              role="tab"
              className={section === item ? "active" : ""}
              aria-selected={section === item}
              aria-controls="settings-panel"
              tabIndex={section === item ? 0 : -1}
              onClick={() => setSection(item)}
              onKeyDown={(event) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const nextIndex = event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? sections.length - 1
                    : (index + (event.key === "ArrowRight" ? 1 : -1) + sections.length) % sections.length;
                const next = sections[nextIndex];
                setSection(next);
                document.getElementById(`settings-tab-${next}`)?.focus();
              }}
              key={item}
            >
              {item === "goals" ? "Goals" : item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </nav>

        <div
          className="settings-grid"
          id="settings-panel"
          role="tabpanel"
          aria-labelledby={`settings-tab-${section}`}
        >
          {section === "connections" ? workerConnection : null}
          {section === "companion" ? (
          <section className="settings-card">
            <p className="eyebrow">Companion</p>
            <h2>Appearance</h2>
            <label>
              Nickname
              <input value={nickname} onChange={(event) => onNickname(event.target.value)} />
            </label>
            <label>
              Pet scale · {scale.toFixed(2)}
              <input
                type="range"
                min={0.8}
                max={1.4}
                step={0.05}
                value={scale}
                onChange={(event) => onScale(Number(event.target.value))}
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={petVisible}
                onChange={(event) => onPetVisible(event.target.checked)}
              />
              Show desktop pet
            </label>
            <label>
              <input
                type="checkbox"
                checked={clickThrough}
                onChange={(event) => onClickThrough(event.target.checked)}
              />
              Click through the pet overlay
            </label>
            <p className="settings-note">
              When on, the pet ignores mouse clicks so it cannot cover work. Turn this off here to
              interact with the pet again.
            </p>
            <button type="button" className="solid" onClick={onSaveAppearance}>Save appearance</button>
          </section>
          ) : null}
          {section === "companion" ? companionRoster : null}

          {section === "connections" ? (
          <section className="settings-card settings-wide">
            <p className="eyebrow">Worker integrations</p>
            <h2>Provision a scoped hook</h2>
            <p className="settings-note">
              Create this before starting a new hooked worker. It can call only the selected
              harness routes in this project; the first valid hook binds it permanently to that
              vendor session. The bridge operator bearer is never copied into the worker.
            </p>
            <div className="form-grid two-column">
              <label>
                Harness
                <select
                  value={hookHarness}
                  onChange={(event) => onHookHarness(event.target.value as HookHarness)}
                >
                  <option value="cursor">Cursor</option>
                  <option value="claude_code">Claude Code</option>
                  <option value="qwen">Qwen</option>
                  <option value="hermes">Hermes</option>
                  <option value="opencode">OpenCode</option>
                </select>
              </label>
              <label>
                Exact project folder
                <input
                  value={hookProject}
                  onChange={(event) => onHookProject(event.target.value)}
                  placeholder="C:\\work\\project"
                  autoComplete="off"
                />
              </label>
            </div>
            <p className="settings-note">
              Set <code>{hookEnvironment}</code> in the environment that launches the worker.
              Starting another session with the same credential will be rejected after first bind.
            </p>
            <button
              type="button"
              className="solid"
              disabled={!hookProject.trim() || provisioningHook}
              onClick={onProvisionHook}
            >
              {provisioningHook ? "Provisioning…" : "Create one-time credential"}
            </button>
            {hookCredential ? (
              <div role="status" aria-live="polite">
                <label>
                  {hookEnvironment} · expires {hookCredentialExpiresAt}
                  <input
                    type="password"
                    value={hookCredential}
                    readOnly
                    autoComplete="off"
                    aria-label={`One-time ${hookEnvironment} credential`}
                  />
                </label>
                <button type="button" className="ghost" onClick={onCopyHook}>Copy credential</button>
                <button type="button" className="ghost" onClick={onClearHook}>Clear from screen</button>
              </div>
            ) : null}
          </section>
          ) : null}

          {section === "supervisor" ? (
          <section className="settings-card settings-wide">
            <p className="eyebrow">Supervisor inference</p>
            <h2>PEX model</h2>
            <p className="settings-note">
              {supervisor
                ? supervisorHonestyCopy(supervisor)
                : "Supervisor configuration has not been observed from canonical local state."}
            </p>
            <p className="settings-note">
              {supervisor?.login_note || (supervisor
                ? "This is PEX’s supervisor model, not a worker harness. Use the displayed credential source."
                : "No provider or credential source is assumed while settings are unavailable.")}
            </p>
            {settingsIssue ? (
              <div className="canonical-state-warning" role="status" aria-live="polite">
                <p>
                  {settingsIssue}{" "}
                  {settingsAvailable
                    ? "Available settings remain editable; unavailable sections are not treated as defaults."
                    : "Supervisor configuration controls remain disabled until a current revision loads."}
                </p>
                <button type="button" className="ghost" disabled={savingSupervisor} onClick={onReloadSettings}>
                  Retry settings
                </button>
              </div>
            ) : null}
            <div className="form-grid two-column">
              <label>
                Provider
                <select
                  disabled={!settingsAvailable || savingSupervisor}
                  value={supervisorProvider}
                  onChange={(event) => {
                    const next = event.target.value;
                    onSupervisorProvider(next);
                    const first = (supervisor?.catalog || []).find((row) => row.provider === next);
                    if (first) onSupervisorModel(first.model_id);
                  }}
                >
                  <option value="">auto-detect</option>
                  {providers.map((provider) => <option value={provider} key={provider}>{provider}</option>)}
                </select>
              </label>
              <label>
                {catalogIsLive ? "Live provider models" : "Model suggestions (unverified)"}
                <select disabled={!settingsAvailable || savingSupervisor} value={inCatalog ? supervisorModel : ""} onChange={(event) => onSupervisorModel(event.target.value)}>
                  <option value="">paste any model id below</option>
                  {visibleCatalog.map((row) => (
                      <option value={row.model_id} key={`${row.provider}:${row.model_id}:${row.label}`}>
                        {row.label} · {row.model_id}
                      </option>
                    ))}
                </select>
              </label>
            </div>
            <label>
              Model id
              <input disabled={!settingsAvailable || savingSupervisor} value={supervisorModel} onChange={(event) => onSupervisorModel(event.target.value)} placeholder="Any supported vendor id" />
            </label>
            <div className="form-grid two-column">
              <label>
                Authentication
                <select
                  value={supervisorAuth}
                  disabled={!settingsAvailable || savingSupervisor}
                  onChange={(event) => onSupervisorAuth(event.target.value as SupervisorAuthMode)}
                >
                  {supervisorAuthOptions.map((mode) => (
                    <option value={mode} key={mode}>{mode.replace("_", " ")}</option>
                  ))}
                </select>
              </label>
              {supervisorProvider === "custom" ? (
                <label>
                  Endpoint protocol
                  <select
                    value={supervisorProtocol}
                    disabled={!settingsAvailable || savingSupervisor}
                    onChange={(event) => onSupervisorProtocol(event.target.value as SupervisorProtocol)}
                  >
                    <option value="openai">OpenAI-compatible</option>
                    <option value="anthropic">Anthropic-compatible</option>
                  </select>
                </label>
              ) : null}
            </div>
            {supervisorProvider === "custom" ? (
              <label>
                Custom base URL
                <input
                  value={supervisorBaseUrl}
                  disabled={!settingsAvailable || savingSupervisor}
                  onChange={(event) => onSupervisorBaseUrl(event.target.value)}
                  placeholder="https://models.example.com/v1"
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            ) : supervisorProvider ? (
              <label>
                Provider endpoint · credential destination
                <input
                  value={supervisorBaseUrl}
                  disabled={!settingsAvailable || savingSupervisor}
                  readOnly
                  placeholder="Built-in provider endpoint"
                  autoComplete="off"
                  spellCheck={false}
                />
                <span className="settings-note">
                  {supervisorBaseUrl
                    ? "This saved endpoint is included when you save. Choose custom to edit the destination."
                    : "Saving selects this provider’s built-in endpoint. Choose custom for a different destination."}
                </span>
              </label>
            ) : null}
            {supervisorUsesCredential ? (
              <>
                <label>
                  API key · write only
                  <input
                    type="password"
                    value={supervisorApiKey}
                    disabled={!settingsAvailable || savingSupervisor}
                    onChange={(event) => onSupervisorApiKey(event.target.value)}
                    placeholder={supervisor?.credential_configured ? "Stored locally · paste to replace" : "Paste to store in the OS credential vault"}
                    autoComplete="new-password"
                    spellCheck={false}
                  />
                </label>
                <label>
                  When the key box is empty
                  <select
                    value={supervisorCredentialAction}
                    disabled={!settingsAvailable || savingSupervisor}
                    onChange={(event) => onSupervisorCredentialAction(event.target.value as SupervisorCredentialAction)}
                  >
                    <option value="keep">Keep the current credential source</option>
                    <option value="environment">Use provider environment credentials</option>
                    <option value="clear">Clear the stored credential</option>
                  </select>
                </label>
                <p className="settings-note">
                  {supervisor?.credential_source === "secret_store"
                    ? "A credential is stored in the OS vault. Its value and reference are never returned."
                    : supervisor?.credential_source === "environment"
                      ? "PEX is configured to read the selected provider’s environment credential."
                      : "No credential is configured. Custom auth may still work for an intentionally keyless endpoint."}
                </p>
              </>
            ) : null}
            <button type="button" className="ghost" disabled={!settingsAvailable || savingSupervisor || refreshingCatalog} onClick={onRefreshCatalog}>
              {refreshingCatalog ? "Refreshing…" : "Refresh configured provider models"}
            </button>
            <button type="button" className="solid" disabled={!settingsAvailable || savingSupervisor} onClick={onSaveSupervisor}>
              {savingSupervisor ? "Saving…" : "Save supervisor"}
            </button>
          </section>
          ) : null}

          {section === "connections" ? (
          <section className="settings-card settings-wide">
            <p className="eyebrow">Attention</p>
            <h2>Remote channels</h2>
            <p className="settings-note">
              Remote messages use the same human-decision policy as the deck. Telegram, Discord,
              WhatsApp, and Slack stay disconnected until a real adapter exists.
            </p>
            <ul className="settings-note">
              {(channels?.channels || []).map((row) => (
                <li key={row.id}>{channelStatusCopy(row)}</li>
              ))}
            </ul>
          </section>
          ) : null}

          {section === "companion" ? (
          <section className="settings-card settings-wide">
            <p className="eyebrow">Custom pet input</p>
            <h2>Generate a base candidate</h2>
            <p className="settings-note">
              {hatchCap?.generation_ready
                ? `Uses ${hatchCap.provider || "your configured"} image endpoint.`
                : hatchCap?.reason || "A configured image endpoint is required. Text-only endpoints fail explicitly."}
            </p>
            <p className="settings-note">
              {HATCH_BASE_CANDIDATE_DISCLOSURE}
            </p>
            <div className="form-grid two-column">
              <label>
                Pet name
                <input value={hatchName} onChange={(event) => onHatchName(event.target.value)} placeholder="Nori" />
              </label>
              <label>
                Style
                <select value={hatchStyle} onChange={(event) => onHatchStyle(event.target.value)}>
                  {['plush', 'clay', 'sticker', 'flat-vector', '3d-toy', 'auto'].map((style) => (
                    <option value={style} key={style}>{style}</option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Look
              <input value={hatchNotes} onChange={(event) => onHatchNotes(event.target.value)} placeholder="Plush fox, ink-navy, cream belly, no laptop" />
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={hatchOneCallConfirmed}
                onChange={(event) => onHatchOneCallConfirmed(event.target.checked)}
              />
              {HATCH_BASE_CANDIDATE_CONFIRMATION}
            </label>
            <button
              type="button"
              className="solid"
              disabled={
                !hatchName.trim() ||
                !hatchOneCallConfirmed ||
                hatchCap?.generation_ready !== true ||
                hatching
              }
              onClick={onHatch}
            >
              {hatching ? "Starting one call…" : "Generate unverified base candidate"}
            </button>
            {hatchJobs.length ? (
              <ul className="settings-list">
                {hatchJobs.slice(0, 4).map((job) => (
                  <li key={job.id}>
                    <strong>{job.display_name}</strong>
                    <span>{job.status} · {job.jobs_complete}/{job.jobs_total} · {job.error || job.step}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
          ) : null}

          {section === "companion" ? (
          <section className="settings-card">
            <p className="eyebrow">Bring your own</p>
            <h2>Import pet</h2>
            <p className="settings-note">{HATCH_EXTERNAL_IMPORT_DISCLOSURE}</p>
            <label>
              Codex v2 pet folder
              <input value={importDir} onChange={(event) => onImportDir(event.target.value)} placeholder="Folder with pet.json and spritesheet.webp" />
            </label>
            <button type="button" className="ghost" disabled={!importDir.trim()} onClick={onImport}>Import hatch-pet</button>
          </section>
          ) : null}

          {section === "goals" ? (
          <section className="settings-card">
            <p className="eyebrow">Persistent state</p>
            <h2>Stored goals</h2>
            {goals.length ? (
              <ul className="settings-list">
                {goals.map((goal) => (
                  <li key={goal.id}>
                    <strong>{goal.title}</strong>
                    <span>{goal.objective}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="settings-note">No goals stored yet.</p>}
          </section>
          ) : null}
        </div>
        {note ? <p className="note settings-page-note" role="status" aria-live="polite">{note}</p> : null}
      </div>
    </main>
  );
}
