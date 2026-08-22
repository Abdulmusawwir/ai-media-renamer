import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Optional label shown in the fallback (e.g. the page name). */
  label?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false, message: "" };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return { hasError: true, message };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // Surface in the console for debugging; the UI stays alive otherwise.
    console.error("ErrorBoundary caught an error:", error, info.componentStack);
  }

  private handleReload = () => {
    this.setState({ hasError: false, message: "" });
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-[40vh] items-center justify-center p-6">
        <div className="w-full max-w-md rounded-xl border border-danger/40 bg-danger/10 p-6 text-center shadow-lg">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-danger/15">
            <AlertTriangle size={24} className="text-danger" />
          </div>
          <h3 className="text-base font-semibold text-text">
            {this.props.label
              ? `Something went wrong in ${this.props.label}`
              : "Something went wrong"}
          </h3>
          <p className="mt-1 break-words text-sm text-text-dim">
            {this.state.message || "An unexpected error occurred."}
          </p>
          <button
            className="mx-auto mt-4 flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-2"
            onClick={this.handleReload}
          >
            <RotateCcw size={15} /> Reload
          </button>
        </div>
      </div>
    );
  }
}
