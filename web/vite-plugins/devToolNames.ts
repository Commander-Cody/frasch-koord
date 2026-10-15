/**
 * The names that mark the dev tools: the bases of their dev-server endpoints
 * and the file the area review reads. The plugins serve under them, and
 * scripts/check-build.mjs refuses a build that contains them — Node runs this
 * file for it as it is, so it imports nothing and has no syntax but types to
 * strip.
 */

/** Where vite-plugins/curate.ts answers. */
export const CURATE_BASE = '/__curate/';

/** Where vite-plugins/areas.ts answers. */
export const AREAS_BASE = '/__areas/';

/** In names/, what `frasch build areas` writes for the area review alone. */
export const AREA_PARTS_FILE = 'dialect_areas_parts.geojson';
