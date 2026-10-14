import { useCallback, useEffect, useState } from 'react';

import { errorMessage } from './fetchJson';

/** What a dev panel loads, as far as it got, and a way to load it again. */
export interface DevResource<T> {
  /** null until loaded. */
  data: T | null;
  /** Why loading failed; null while it has not. */
  error: string | null;
  reload: () => void;
  /** Changes what was loaded the way the panel's own write changed the file; a no-op before. */
  update: (change: (data: T) => T) => void;
}

/**
 * Loads what a dev panel shows, once `load` (stable) resolves, and again on
 * `reload`: the files behind both views are rebuilt by hand, so reloading is
 * the whole of "refresh". What was loaded stays until the new data is there.
 */
export function useDevResource<T>(load: () => Promise<T>): DevResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [round, setRound] = useState(0);
  const reload = useCallback(() => setRound((n) => n + 1), []);
  const update = useCallback(
    (change: (data: T) => T) => setData((prev) => (prev === null ? prev : change(prev))),
    [],
  );

  useEffect(() => {
    // Only the latest round may answer: an earlier one can arrive after it.
    let current = true;
    load().then(
      (loaded) => {
        if (!current) return;
        setData(loaded);
        setError(null);
      },
      (err: unknown) => {
        if (current) setError(errorMessage(err));
      },
    );
    return () => {
      current = false;
    };
  }, [load, round]);
  return { data, error, reload, update };
}
