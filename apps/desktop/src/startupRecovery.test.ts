import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createElement, type ComponentType } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

import {
  KNOWN_BRIDGE_FAILURE_CODES,
  advanceBridgeBootstrapStatus,
  bridgeBootstrapAvailable,
  initialBridgeBootstrapStatus,
  normalizeBridgeBootstrapStatus,
  shouldPollBridgeBootstrap,
  startupRecoveryCopy,
  startupDiagnosticText,
  unavailableBridgeBootstrapStatus,
} from "./startupRecovery.ts";

test("every known startup error renders an actionable safe non-retryable state", async () => {
  const vite = await createServer({ root: process.cwd(), server: { middlewareMode: true }, appType: "custom" });
  try {
    const loaded = await vite.ssrLoadModule("/src/components/StartupRecovery.tsx") as {
      StartupRecovery: ComponentType<{
        status: ReturnType<typeof normalizeBridgeBootstrapStatus>;
        retrying: boolean;
        onRetry: () => void;
      }>;
    };
    for (const code of KNOWN_BRIDGE_FAILURE_CODES) {
      const status = normalizeBridgeBootstrapStatus({
        phase: "failed",
        code,
        message: "private native message must not be copied",
        retryable: false,
        source: code === "port_occupied_untrusted" ? "unverified_port_owner" : "not_ready",
        attempt: 1,
      });
      const html = renderToStaticMarkup(createElement(loaded.StartupRecovery, {
        status,
        retrying: false,
        onRetry: () => undefined,
      }));
      assert.match(html, /Copy safe details/u, code);
      assert.doesNotMatch(html, /disabled/u, code);
      assert.doesNotMatch(html, /Retry bridge/u, code);
      assert.match(html, new RegExp(`<code>${code}</code>`, "u"), code);
      assert.match(html, /Safe technical details/u, code);
      assert.match(html, /Startup attempt/u, code);
      assert.match(html, /Bridge state/u, code);
      const diagnostic = startupDiagnosticText(status);
      assert.ok(diagnostic?.startsWith(`PEX startup error: ${code}.`), code);
      assert.doesNotMatch(diagnostic, /private native message/u, code);
      const copy = startupRecoveryCopy(status);
      assert.notEqual(copy.title, "PEX could not start its bridge", code);
      assert.ok(copy.detail.length > 20, code);
      assert.ok((copy.guidance || "").length > 20, code);
      assert.doesNotMatch(copy.guidance || "", /\bretry\b/iu, code);
      assert.doesNotMatch(diagnostic, /\bretry\b/iu, code);
    }
  } finally {
    await vite.close();
  }
});

test("startup actions match the exact native retryability matrix", async () => {
  const retryability: Record<(typeof KNOWN_BRIDGE_FAILURE_CODES)[number], boolean> = {
    bridge_address_invalid: false,
    bridge_identity_lost: true,
    bridge_process_stopped: true,
    desktop_control_unavailable: false,
    desktop_state_unavailable: false,
    identity_timeout: true,
    not_started: true,
    port_check_failed: true,
    port_occupied_untrusted: true,
    sidecar_exited_early: true,
    sidecar_missing: false,
    sidecar_spawn_failed: true,
    token_generation_failed: true,
  };
  assert.deepEqual(Object.keys(retryability).sort(), [...KNOWN_BRIDGE_FAILURE_CODES].sort());
  const vite = await createServer({ root: process.cwd(), server: { middlewareMode: true }, appType: "custom" });
  try {
    const loaded = await vite.ssrLoadModule("/src/components/StartupRecovery.tsx") as {
      StartupRecovery: ComponentType<{
        status: ReturnType<typeof normalizeBridgeBootstrapStatus>;
        retrying: boolean;
        onRetry: () => void;
      }>;
    };
    for (const code of KNOWN_BRIDGE_FAILURE_CODES) {
      const status = normalizeBridgeBootstrapStatus({
        phase: "failed",
        code,
        message: "private native message",
        retryable: retryability[code],
        source: code === "port_occupied_untrusted" ? "unverified_port_owner" : "not_ready",
        attempt: 999999,
      });
      const html = renderToStaticMarkup(createElement(loaded.StartupRecovery, {
        status,
        retrying: false,
        onRetry: () => undefined,
      }));
      assert.match(html, /Copy safe details/u, code);
      assert.doesNotMatch(html, /private native message/u, code);
      if (retryability[code]) assert.match(html, />Retry bridge<\/button>/u, code);
      else assert.doesNotMatch(html, /Retry bridge/u, code);

      const retryingHtml = renderToStaticMarkup(createElement(loaded.StartupRecovery, {
        status,
        retrying: true,
        onRetry: () => undefined,
      }));
      if (retryability[code]) {
        assert.match(retryingHtml, /<button[^>]+disabled=""[^>]*>Retrying…<\/button>/u, code);
        assert.doesNotMatch(retryingHtml, />Retry bridge<\/button>/u, code);
      } else {
        assert.doesNotMatch(retryingHtml, /Retrying…|Retry bridge/u, code);
      }
    }
  } finally {
    await vite.close();
  }
});

test("startup recovery CSS wraps actions and remains scrollable at high zoom", async () => {
  const { readFile } = await import("node:fs/promises");
  const css = await readFile(new URL("./styles.css", import.meta.url), "utf8");
  assert.match(css, /\.startup-recovery\s*\{[\s\S]*?overflow:\s*auto/u);
  assert.match(css, /\.startup-recovery-actions\s*\{[\s\S]*?flex-wrap:\s*wrap/u);
  assert.match(css, /@media \(max-width: 440px\), \(max-height: 360px\)/u);
  assert.match(css, /overflow-wrap:\s*anywhere/u);
});

test("initial startup is explicitly pending and matches the native bounded cold-start budget", async () => {
  assert.equal(initialBridgeBootstrapStatus.phase, "starting");
  const copy = startupRecoveryCopy(initialBridgeBootstrapStatus);
  assert.equal(copy.tone, "starting");
  const rust = await readFile(new URL("../src-tauri/src/main.rs", import.meta.url), "utf8");
  const seconds = rust.match(/BRIDGE_STARTUP_TIMEOUT: Duration = Duration::from_secs\((\d+)\)/u)?.[1];
  assert.equal(seconds, "60");
  assert.ok(copy.guidance?.includes(`${seconds}-second deadline`));
});

test("unverified port ownership remains explicit and never suggests automatic takeover", () => {
  const status = normalizeBridgeBootstrapStatus({
    phase: "failed",
    code: "port_occupied_untrusted",
    message: "safe Rust detail",
    retryable: true,
    source: "unverified_port_owner",
    attempt: 2,
  });
  const copy = startupRecoveryCopy(status);
  assert.equal(status.source, "unverified_port_owner");
  assert.match(copy.detail, /could not prove/u);
  assert.match(copy.guidance || "", /will not stop or reuse/u);
});

test("malformed or widened desktop state fails closed without retry", () => {
  for (const value of [
    null,
    {},
    {
      phase: "ready",
      code: null,
      message: "forged",
      retryable: false,
      source: "unverified_port_owner",
      attempt: 1,
    },
    {
      phase: "failed",
      code: "arbitrary_internal_error",
      message: "raw private diagnostic",
      retryable: true,
      source: "not_ready",
      attempt: 1,
    },
    {
      phase: "failed",
      code: "sidecar_spawn_failed",
      message: "x".repeat(241),
      retryable: true,
      source: "not_ready",
      attempt: 1,
    },
  ]) {
    const normalized = normalizeBridgeBootstrapStatus(value);
    assert.equal(normalized.phase, "failed");
    assert.equal(normalized.code, "desktop_control_unavailable");
    assert.equal(normalized.retryable, false);
  }
});

test("a verified ready state is bound to the desktop-owned sidecar", () => {
  const status = normalizeBridgeBootstrapStatus({
    phase: "ready",
    code: null,
    message: "ready",
    retryable: false,
    source: "owned_sidecar",
    attempt: 3,
  });
  assert.equal(status.phase, "ready");
  assert.equal(status.source, "owned_sidecar");
  assert.equal(status.attempt, 3);
});

test("startup orchestration rejects stale polling and same-attempt resurrection", () => {
  const ready = normalizeBridgeBootstrapStatus({
    phase: "ready",
    code: null,
    message: "ready",
    retryable: false,
    source: "owned_sidecar",
    attempt: 4,
  });
  const failed = normalizeBridgeBootstrapStatus({
    phase: "failed",
    code: "bridge_process_stopped",
    message: "stopped",
    retryable: true,
    source: "owned_sidecar",
    attempt: 4,
  });
  const retrying = normalizeBridgeBootstrapStatus({
    phase: "starting",
    code: null,
    message: "starting",
    retryable: false,
    source: "not_ready",
    attempt: 5,
  });

  assert.equal(advanceBridgeBootstrapStatus(ready, failed), failed);
  assert.equal(advanceBridgeBootstrapStatus(failed, ready), failed);
  assert.equal(advanceBridgeBootstrapStatus(retrying, failed), retrying);
  assert.equal(advanceBridgeBootstrapStatus(retrying, ready), retrying);
});

test("only main desktop surfaces poll or mutate bridge bootstrap state", () => {
  assert.equal(shouldPollBridgeBootstrap(true, "main"), true);
  assert.equal(shouldPollBridgeBootstrap(true, "settings"), true);
  assert.equal(shouldPollBridgeBootstrap(true, "pet"), false);
  assert.equal(shouldPollBridgeBootstrap(false, "main"), false);
});

test("control-read availability gates ready UI without corrupting native generation state", () => {
  const ready = normalizeBridgeBootstrapStatus({
    phase: "ready",
    code: null,
    message: "ready",
    retryable: false,
    source: "owned_sidecar",
    attempt: 7,
  });
  assert.equal(bridgeBootstrapAvailable(true, "main", true, ready), true);
  assert.equal(bridgeBootstrapAvailable(true, "main", false, ready), false);
  assert.equal(unavailableBridgeBootstrapStatus(ready.attempt).attempt, 7);
  assert.equal(advanceBridgeBootstrapStatus(ready, ready), ready);
  assert.equal(bridgeBootstrapAvailable(true, "main", true, ready), true);
});
