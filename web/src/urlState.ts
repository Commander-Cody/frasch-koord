// What a link carries besides the viewport: the selected label option and the
// place whose card is open, e.g.
//
//   /?view=frr-x-local&place=node/240042766#12/54.79/8.83
//
// The viewport is MapLibre's own `#zoom/lat/lon` hash (see Map.tsx). MapLibre
// rewrites the whole hash on every move, so nothing else can live there; these
// go in the query string, which it leaves alone.

import { DEFAULT_LABELS, labelOption } from './config';

const VIEW_PARAM = 'view';
const PLACE_PARAM = 'place';

export interface UrlState {
  /** Label option tag (a dialect, or LOCAL_TAG). */
  view?: string;
  /** Name-list id of the place whose card is open, e.g. "node/240042766" or "local/<slug>". */
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
 * the viewport hash. `replaceState`, not `pushState`: picking a dialect or a
 * place is not a navigation the back button should step through.
 */
export function writeUrlState(state: UrlState): void {
  const params = new URLSearchParams(window.location.search);
  for (const [key, value] of [
    [VIEW_PARAM, state.view],
    [PLACE_PARAM, state.place],
  ] as const) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  // Ids are `node/123`; a slash is fine in a query and reads much better
  // than %2F in a link people paste into chats.
  const query = params.toString().replace(/%2F/gi, '/');
  const { pathname, hash } = window.location;
  const url = `${pathname}${query ? `?${query}` : ''}${hash}`;
  if (url !== `${pathname}${window.location.search}${hash}`) {
    window.history.replaceState(window.history.state, '', url);
  }
}

/**
 * The label option the page opens in: the link's `?view=` when it names one
 * of the selector's options, else the default — a stale tag from an old link
 * must not leave the map without labels or the UI without a language.
 */
export const INITIAL_LABELS = labelOption(readUrlState().view ?? DEFAULT_LABELS).tag;
