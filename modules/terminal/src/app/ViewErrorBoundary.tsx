import { Component, Fragment, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
  resetCount: number;
}

/**
 * Catches a render error from one view and keeps the rest of the terminal
 * alive — terminal-shell spec, "Awaria pojedynczego widoku". "Retry" remounts
 * the subtree fresh via the `key` rather than merely clearing the error flag,
 * so state that caused the crash doesn't survive the retry.
 */
export class ViewErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetCount: 0 };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    console.error("View crashed:", error, info.componentStack);
  }

  private retry = () => {
    this.setState((s) => ({ error: null, resetCount: s.resetCount + 1 }));
  };

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full items-center justify-center p-8">
          <div className="max-w-md text-center">
            <p className="text-lg text-critical">This view hit an error.</p>
            <p className="mt-1 text-sm text-ink-muted">{this.state.error.message}</p>
            <button
              type="button"
              onClick={this.retry}
              className="mt-4 rounded border border-border px-3 py-1.5 text-sm text-ink hover:bg-panel-strong"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }
    return <Fragment key={this.state.resetCount}>{this.props.children}</Fragment>;
  }
}
