import { useEffect, useRef, useState } from "react";

import { startupDiagnosticText, startupRecoveryCopy } from "../startupRecovery";
import type { BridgeBootstrapStatus } from "../types";

export function StartupRecovery({
  status,
  retrying,
  onRetry,
}: {
  status: BridgeBootstrapStatus;
  retrying: boolean;
  onRetry: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [copyFeedback, setCopyFeedback] = useState("");
  const copy = startupRecoveryCopy(status);

  async function copyDiagnostic() {
    const diagnostic = startupDiagnosticText(status);
    if (!diagnostic) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(diagnostic);
      setCopyFeedback("Safe startup details copied.");
    } catch {
      setCopyFeedback(`Copy unavailable. Error code: ${status.code}.`);
    }
  }

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [status.phase, status.attempt]);

  return (
    <main className={`startup-recovery startup-recovery-${copy.tone}`}>
      <section
        className="startup-recovery-card"
        role={status.phase === "failed" ? "alert" : "status"}
        aria-live={status.phase === "failed" ? "assertive" : "polite"}
        aria-busy={status.phase === "starting" || retrying}
      >
        <span className="startup-recovery-mark" aria-hidden="true">PEX</span>
        <p className="eyebrow">{copy.eyebrow}</p>
        <h1 ref={heading} tabIndex={-1}>{copy.title}</h1>
        <p>{copy.detail}</p>
        {copy.guidance ? <p className="startup-recovery-guidance">{copy.guidance}</p> : null}
        {status.phase === "failed" ? (
          <div className="startup-recovery-actions">
            {status.retryable ? (
              <button type="button" className="solid" onClick={onRetry} disabled={retrying}>
                {retrying ? "Retrying…" : "Retry bridge"}
              </button>
            ) : (
              <button type="button" className="solid" onClick={() => void copyDiagnostic()}>
                Copy safe error details
              </button>
            )}
            <code>{status.code}</code>
            {copyFeedback ? <span role="status" aria-live="polite">{copyFeedback}</span> : null}
          </div>
        ) : (
          <div className="startup-recovery-progress" aria-hidden="true"><span /></div>
        )}
      </section>
    </main>
  );
}
