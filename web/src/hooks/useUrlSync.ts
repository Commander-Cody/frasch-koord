import { useEffect } from 'react';

import { writeUrlState, type UrlState } from '../urlState';

/**
 * Keeps the address bar a shareable link to what is on screen: `view` and
 * `place` go into the query string (see urlState.ts), MapLibre adds the
 * viewport.
 */
export function useUrlSync({ view, place }: UrlState): void {
  useEffect(() => {
    writeUrlState({ view, place });
  }, [view, place]);
}
