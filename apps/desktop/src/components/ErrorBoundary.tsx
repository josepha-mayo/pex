import { Component, type ReactNode } from "react";
import { BrandMark } from "./BrandMark";

type BoundaryState = { error: Error | null };

// One bad render must not blank the whole shell — a judge mid-demo hits a
// readable, honest failure surface with a reload instead of a white screen.
export class AppErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("PEX surface render failed", error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="main-shell error-shell">
        <header className="topbar">
          <BrandMark label />
        </header>
        <section className="error-surface" role="alert">
          <p className="eyebrow">Render error</p>
          <h1>This surface hit an unexpected state.</h1>
          <p>
            The supervisor is unaffected — this is a UI failure, and the bridge's
            canonical state is intact. Reload to resume.
          </p>
          <code>{this.state.error.message || "unknown render error"}</code>
          <div className="button-row">
            <button type="button" className="solid" onClick={() => window.location.reload()}>
              Reload
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                window.location.hash = "";
                window.location.reload();
              }}
            >
              Reload to Home
            </button>
          </div>
        </section>
      </main>
    );
  }
}
