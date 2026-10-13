import { useEffect } from 'react';

/** Escape calls `close` while `open`, like it closes any transient panel. */
export function useCloseOnEscape(open: boolean, close: (means: 'keyboard') => void): void {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close('keyboard');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, close]);
}
