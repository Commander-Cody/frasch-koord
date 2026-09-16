// Central place for tile hosting and dialect configuration.
// The tiles URL is the ONLY place the frontend depends on how/where tiles are hosted.

/**
 * URL of the PMTiles archive (or any MapLibre-compatible vector source URL).
 *
 * Defaults to a PMTiles file served from this site's own /tiles/ directory
 * (see web/public/tiles/), resolved relative to the site origin. Override via
 * the VITE_TILES_URL environment variable, e.g. to point at a CDN-hosted
 * PMTiles archive.
 */
export const TILES_URL: string =
  import.meta.env.VITE_TILES_URL || 'pmtiles:///tiles/schleswig-holstein.pmtiles';

/** Default North Frisian dialect (BCP 47 private-use subtag). */
export const DEFAULT_DIALECT = 'frr-x-mooring';

/** A dialect selectable in the UI. */
export interface Dialect {
  /** BCP 47 language tag, e.g. "frr-x-mooring". Matches the tile property "name:<tag>". */
  tag: string;
  /** Human-readable label shown in the dialect selector. */
  label: string;
}

/** Dialects available in the UI. More will be added as name coverage grows. */
export const DIALECTS: Dialect[] = [{ tag: 'frr-x-mooring', label: 'Mooring' }];
