// What a link carries besides the viewport: the selected label option and the
// place whose card is open, e.g.
//
//   /?view=frr-x-local&place=naibel#12/54.79/8.83
//
// The viewport is MapLibre's own `#zoom/lat/lon` hash (see Map.tsx). MapLibre
// rewrites the whole hash on every move, so nothing else can live there; these
// go in the query string, which it leaves alone.

import { DEFAULT_VIEW, labelOption } from './config';
import { replaceQueryParams } from './queryParams';

const VIEW_PARAM = 'view';
const PLACE_PARAM = 'place';

export interface UrlState {
  /** Label option tag (a dialect, or LOCAL_TAG). */
  view?: string;
  /**
   * Name-list row id of the place whose card is open, e.g. "naibel". Links
   * from before the row ids name an OSM reference ("node/240042766"), which
   * names.ts `entryLookup` still resolves.
   */
  place?: string;
}

export function readUrlState(): UrlState {
  const params = new URLSearchParams(window.location.search);
  return {
    view: params.get(VIEW_PARAM) || undefined,
    place: params.get(PLACE_PARAM) || undefined,
  };
}

/**
 * Mirrors `state` into the address bar, keeping any other query parameter and
 * the viewport hash (see queryParams.ts).
 */
export function writeUrlState(state: UrlState): void {
  replaceQueryParams({ [VIEW_PARAM]: state.view, [PLACE_PARAM]: state.place });
}

/**
 * The label option the page opens in: the link's `?view=` when it names one
 * of the selector's options, else the default — a stale tag from an old link
 * must not leave the map without labels or the UI without a language. A
 * function, read when a view mounts: the URL changes once the page runs.
 */
export function initialView(): string {
  return labelOption(readUrlState().view ?? DEFAULT_VIEW).tag;
}
