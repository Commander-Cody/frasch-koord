import { useCallback, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

/**
 * How long the first render may take before the map counts as broken. A
 * worker that never starts raises no error event (MapLibre does not listen
 * for one); the map just never loads.
 */
const LOAD_TIMEOUT_MS = 30_000;

/** Something the map needs failed to load, or its first render is overdue. */
export type MapFailure = 'error' | 'timeout';

/** What the failure watch asks of the map. */
export type FailureMap = Pick<MapLibreMap, 'on'>;

export interface MapFailureState {
  failure: MapFailure | null;
  /** Hides the failure until the next one. */
  dismiss: () => void;
  /**
   * Starts watching `map`, and returns how to stop. Called in the task that
   * creates the map: a failure that comes back before the watch is lost (#192).
   * The same function on every render.
   */
  watch: (map: FailureMap) => () => void;
}

/**
 * Whether something the watched map needs (tiles, glyphs, sprites, the
 * worker) failed to load, or its first render is overdue. The details go to
 * the console.
 */
export function useMapFailure(): MapFailureState {
  const [failure, setFailure] = useState<MapFailure | null>(null);
  const watch = useCallback((map: FailureMap) => watchFailure(map, setFailure), []);
  return { failure, dismiss: () => setFailure(null), watch };
}

/** Reports failures of `map` to `setFailure` until the returned function is called. */
function watchFailure(
  map: FailureMap,
  setFailure: Dispatch<SetStateAction<MapFailure | null>>,
): () => void {
  // MapLibre logs errors itself only while nobody listens for them.
  const errors = map.on('error', (e) => {
    console.error('Map error', e.error);
    setFailure('error');
  });
  const timer = window.setTimeout(() => setFailure((f) => f ?? 'timeout'), LOAD_TIMEOUT_MS);
  const load = map.on('load', () => {
    window.clearTimeout(timer);
    // Only late after all (a tab opened in the background renders nothing
    // until it is shown).
    setFailure((f) => (f === 'timeout' ? null : f));
  });
  return () => {
    window.clearTimeout(timer);
    errors.unsubscribe();
    load.unsubscribe();
  };
}
