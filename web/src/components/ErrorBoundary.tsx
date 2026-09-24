import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

export interface ErrorBoundaryProps {
  children: ReactNode;
  /** Rendered in place of `children` once one of them threw while rendering. */
  fallback: ReactNode;
  /**
   * Try `children` again when this changes. App passes the selection: one
   * malformed names.json entry must not take the panel away for good, only
   * until the user picks another place (or closes the card).
   */
  resetKey?: unknown;
}

interface ErrorBoundaryState {
  failed: boolean;
  /** The resetKey the failure happened under. */
  failedAt?: unknown;
}

/**
 * Catches a render error below it, so that it takes down only this part of
 * the page. React unmounts the whole root on an uncaught one — the map
 * included — which is why App wraps the side panel, never the map.
 * React has no hook for this; it has to be a class.
 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): Partial<ErrorBoundaryState> {
    return { failed: true };
  }

  static getDerivedStateFromProps(
    props: ErrorBoundaryProps,
    state: ErrorBoundaryState,
  ): Partial<ErrorBoundaryState> | null {
    if (!state.failed) return { failedAt: props.resetKey };
    return props.resetKey !== state.failedAt ? { failed: false, failedAt: props.resetKey } : null;
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error('Panel crashed', error, info.componentStack);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
