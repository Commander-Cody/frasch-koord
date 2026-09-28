import { useEffect } from 'react';

/** Escape calls `close` while `open`, like it closes any transient panel. */
export function useCloseOnEscape(open: boolean, close: () => void): void {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, close]);
}
