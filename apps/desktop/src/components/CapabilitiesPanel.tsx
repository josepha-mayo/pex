import {
  CAPABILITY_STATUS_CLASS,
  CAPABILITY_STATUS_LABEL,
  capabilityRows,
} from "../capabilities";

export function CapabilitiesPanel(props: Parameters<typeof capabilityRows>[0]) {
  const rows = capabilityRows(props);
  return (
    <section className="settings-card capabilities-panel">
      <h3>What this build actually does</h3>
      <p className="settings-note">
        Every claim below is derived from the live bridge right now — probed adapters, the
        configured supervisor, the bench endpoint — not from marketing copy. Unproven
        capability stays labelled, not implied.
      </p>
      <ul className="capabilities-list">
        {rows.map((row) => (
          <li key={row.capability}>
            <div className="cap-row">
              <span className={`cap-status ${CAPABILITY_STATUS_CLASS[row.status]}`}>
                {CAPABILITY_STATUS_LABEL[row.status]}
              </span>
              <strong>{row.capability}</strong>
            </div>
            <p>{row.detail}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
