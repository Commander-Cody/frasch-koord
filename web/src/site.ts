// Where the site and its tiles are served from: the only module that reads
// the deployment's base path and tiles URL out of `import.meta.env`.

import { resolvedOnPage } from './url/queryParams';

/**
 * Absolute URL of `path` (no leading slash, e.g. "data/names.json") under the
 * site's base: `/` in dev and for a root deployment, `/frasch-koord/` for a
 * GitHub Pages project site (Vite's `base`, `import.meta.env.BASE_URL`).
 * Everything the site serves from web/public/ goes through here, so the build
 * works under any base path.
 *
 * Absolute because MapLibre wants absolute glyph and sprite URLs; built by
 * string concatenation rather than `new URL(path, base)`, which would
 * percent-encode the `{fontstack}`/`{range}` placeholders of the glyph URL.
 * Read at call time, so tests can stub BASE_URL.
 */
export function siteUrl(path: string): string {
  const base = import.meta.env.BASE_URL;
  // A relative base (`./`) is relative to the page.
  return `${resolvedOnPage(base)}${path}`;
}

/**
 * URL of the PMTiles archive (or any MapLibre-compatible vector source URL).
 * The ONLY place the frontend depends on how/where tiles are hosted.
 *
 * Defaults to the PMTiles archive web/tiles.lock pins, served from this
 * site's own tiles/ directory (see web/public/tiles/) under the name it was
 * published by, under the site's base path. Override via the VITE_TILES_URL
 * environment variable, e.g. to point at a CDN-hosted PMTiles archive.
 */
export const TILES_URL: string =
  import.meta.env.VITE_TILES_URL ||
  `pmtiles://${siteUrl(`tiles/${import.meta.env.TILES_ARCHIVE}`)}`;
