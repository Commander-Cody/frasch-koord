// The references of an `osm` cell as the browser handles them: the one place
// that splits a cell, tells an OSM object from a `local/<slug>` place of our
// own and builds a link to openstreetmap.org. frasch/refs.py is the Python
// side of the same spelling.

/** A reference to an OSM object, as a cell spells it. */
const OSM_REF = /^(node|way|relation)\/(\d+)$/i;
/** The object a page of openstreetmap.org shows, anywhere in its URL. */
const OSM_PAGE = /openstreetmap\.org\/(node|way|relation)\/(\d+)/i;

/**
 * The references of a cell: "relation/1420394; way/123" ->
 * ["relation/1420394", "way/123"], and the one "local/<slug>" of a place OSM
 * does not have. None for an empty cell.
 */
export function osmRefs(cell: string | undefined): string[] {
  return (cell ?? '')
    .split(';')
    .map((ref) => ref.trim())
    .filter(Boolean);
}

/**
 * The reference typed or pasted as `text` names: `way/123`, or the object of
 * an openstreetmap.org URL (`https://www.openstreetmap.org/way/177387348`).
 * null for anything that names no OSM object, a `local/<slug>` among them.
 */
export function parseOsmRef(text: string): string | null {
  const hit = OSM_PAGE.exec(text) ?? OSM_REF.exec(text.trim());
  return hit && `${hit[1].toLowerCase()}/${hit[2]}`;
}

/**
 * The page of the OSM object one reference names (`node/240042766`), or null
 * for one that is not an OSM object: our own `local/<slug>` places.
 */
export function osmUrl(ref: string | undefined): string | null {
  return ref && parseOsmRef(ref) === ref ? `https://www.openstreetmap.org/${ref}` : null;
}
