// What the decision forms make of an OSM reference typed or pasted in.

import { parseOsmRef } from '../../names/osmRef';

/**
 * Accepts `way/123`, several joined by ';', and pasted openstreetmap.org URLs
 * (`https://www.openstreetmap.org/way/177387348`) — the two things one ends up
 * with after looking something up in a browser tab.
 */
export function parseRefs(text: string): string[] | null {
  const parts = (text || '')
    .split(/[;\n,]+/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length === 0) return null;
  const refs = parts.map(parseOsmRef);
  return refs.every((ref) => ref !== null) ? refs : null;
}
