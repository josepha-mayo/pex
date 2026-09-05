import { useEffect, useRef } from "react";

import { startupRecoveryCopy } from "../startupRecovery";
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
  const copy = startupRecoveryCopy(status);

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
            <button
              type="button"
              className="solid"
              onClick={onRetry}
              disabled={!status.retryable || retrying}
            >
              {retrying ? "Retrying…" : "Retry bridge"}
            </button>
            <code>{status.code}</code>
          </div>
        ) : (
          <div className="startup-recovery-progress" aria-hidden="true"><span /></div>
        )}
      </section>
    </main>
  );
}
