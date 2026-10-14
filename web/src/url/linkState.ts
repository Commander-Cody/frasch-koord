// What a link carries besides the viewport: the selected label option and the
// place whose card is open, e.g.
//
//   /?view=frr-x-local&place=naibel#12/54.79/8.83
//
// The viewport is MapLibre's own `#zoom/lat/lon` hash (see Map.tsx). MapLibre
// rewrites the whole hash on every move, so nothing else can live there; these
// go in the query string, which it leaves alone.

import { DEFAULT_VIEW, viewOption } from '../dialects/views';
import { hasViewport, readQueryParam, replaceQueryParams } from './queryParams';

/** Label option tag (a dialect, or LOCAL_TAG). */
const VIEW_PARAM = 'view';
/**
 * Name-list row id of the place whose card is open, e.g. "naibel". Links from
 * before the row ids name an OSM reference ("node/240042766"), which
 * names/load.ts `entryLookup` still resolves.
 */
const PLACE_PARAM = 'place';

/**
 * The label option the page opens in: the link's `?view=` when it names one
 * of the selector's options, else the default — a stale tag from an old link
 * must not leave the map without labels or the UI without a language. A
 * function, read when a view mounts: the URL changes once the page runs.
 */
export function initialView(): string {
  return viewOption(readQueryParam(VIEW_PARAM) ?? DEFAULT_VIEW).tag;
}

/** Keeps `?view=` the selected label option. */
export function writeView(view: string): void {
  replaceQueryParams({ [VIEW_PARAM]: view });
}

/** The place a link names, and whether the link also says where to look. */
export interface LinkedPlace {
  ref: string;
  /** The link has a `#zoom/lat/lon` of its own: mark the place, do not fly to it. */
  keepViewport: boolean;
}

/**
 * The place the page's link opens, if it names one. To be read at mount,
 * before the map starts writing a hash of its own.
 */
export function linkedPlace(): LinkedPlace | undefined {
  const ref = readQueryParam(PLACE_PARAM);
  return ref === undefined ? undefined : { ref, keepViewport: hasViewport() };
}

/** Keeps `?place=` the place whose card is open; none removes it. */
export function writePlace(place: string | undefined): void {
  replaceQueryParams({ [PLACE_PARAM]: place });
}
