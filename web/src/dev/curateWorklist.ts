// The browser's side of the curation worklist (names/work/curate.json, which
// `frasch curate export` writes): its shape, loading it together with the
// patch, the list's filter, and the text helpers of the decision forms. The
// contract itself is names/curate-worklist.schema.json; curateWorklist.test.ts
// pins the types below to it.

import type { PatchEntry } from './curatePatch';

/** One candidate of a worklist row. */
export interface CurateCandidate {
  /** "node/123" | "way/123" | "relation/123". */
  ref: string;
  name: string;
  class: string;
  /** Distance from the centre of North Frisia in km, as `frasch match` computed it; null without a position. */
  km: number | null;
  /** null when candidates.jsonl had no position for the object. */
  lon: number | null;
  lat: number | null;
  /** Decisive tags as one string, e.g. "place=hamlet"; empty when candidates.jsonl no longer has the object. */
  tags: string;
  /** In the Schleswig-Holstein extract the tiles are built from. */
  in_sh: boolean;
  wikidata?: string;
}

/** One row of `names/work/curate.json`. */
export interface CurateRow {
  /** The places.csv row's `id`: what the decisions are keyed on. */
  id: string;
  /** Its line in places.csv at export time (header = 1); shown, never used to find the row. */
  line: number;
  kind: string;
  result: 'ambiguous' | 'not_found';
  /** The Frisian name `frasch match` worked with. */
  name: string;
  /** Every non-empty Frisian name column, raw cell text, keyed by column name. */
  names: Record<string, string>;
  /** The primary German name, '' when the row has none. */
  name_de: string;
  /** The primary Danish name, '' when the row has none. */
  name_da: string;
  /** The German and Danish cells, raw: every variant with its remarks. */
  de: string;
  da: string;
  hint: string;
  note: string;
  /** Why the matcher gave up (matches.csv `note`). */
  why: string;
  /** [lon, lat, radius_km] of the location hint, or null. */
  hint_point: [number, number, number] | null;
  candidates: CurateCandidate[];
}

/** lon_min, lat_min, lon_max, lat_max. */
export type Bbox = [number, number, number, number];

/** `names/work/curate.json` as a whole. */
export interface CurateWorklist {
  bbox: Bbox;
  /** The kinds in the order the list walks them. */
  kind_order: string[];
  /** The kinds whose local reference can carry an area instead of a bare point. */
  polygon_kinds: string[];
  /** The OSM tags that say what kind of thing an object is, the most telling first. */
  class_keys: string[];
  /** The `place` values of a settlement, as a candidate's `class` has them. */
  settlement_places: string[];
  /** The results a row can have, for the filter. */
  results: CurateRow['result'][];
  rows: CurateRow[];
}

/* ---------------------------------------------------------------- loading */

/**
 * The worklist and the decisions made so far, from the dev-server endpoints
 * in web/vite-plugins/curate.ts. Rejects with a message fit for the panel.
 */
export async function fetchWorklist(): Promise<{
  worklist: CurateWorklist;
  entries: PatchEntry[];
}> {
  const [wlRes, patchRes] = await Promise.all([
    fetch('/__curate/worklist'),
    fetch('/__curate/patch'),
  ]);
  if (!wlRes.ok) {
    const body = (await wlRes.json().catch(() => null)) as { error?: string } | null;
    throw new Error(body?.error ?? `worklist: HTTP ${wlRes.status}`);
  }
  if (!patchRes.ok) throw new Error(`patch: HTTP ${patchRes.status}`);
  const worklist = (await wlRes.json()) as CurateWorklist;
  const patch = (await patchRes.json()) as { entries: PatchEntry[] };
  return { worklist, entries: patch.entries ?? [] };
}

/* ----------------------------------------------------------------- filter */

export type ResultFilter = 'all' | CurateRow['result'];

/** What the list shows. */
export interface RowFilter {
  /** Matched against every name, the German and Danish names and the hint. */
  text: string;
  /** '' for all kinds. */
  kind: string;
  result: ResultFilter;
  hideDone: boolean;
}

export const NO_FILTER: RowFilter = { text: '', kind: '', result: 'all', hideDone: true };

export function filterRows(
  rows: CurateRow[],
  filter: RowFilter,
  isDone: (id: string) => boolean,
): CurateRow[] {
  const needle = filter.text.trim().toLowerCase();
  return rows.filter((row) => {
    if (filter.kind && row.kind !== filter.kind) return false;
    if (filter.result !== 'all' && row.result !== filter.result) return false;
    if (filter.hideDone && isDone(row.id)) return false;
    if (!needle) return true;
    const haystack = [row.name, ...Object.values(row.names), row.de, row.da, row.hint]
      .join(' ')
      .toLowerCase();
    return haystack.includes(needle);
  });
}

/**
 * The kinds of the rows, in the exporter's `kind_order`. Anything the
 * exporter emitted but kind_order does not know about still has to be
 * reachable, so the leftovers come after it.
 */
export function rowKinds(worklist: CurateWorklist): string[] {
  const order = worklist.kind_order;
  const present = new Set(worklist.rows.map((row) => row.kind));
  const known = order.filter((kind) => present.has(kind));
  const rest = [...present].filter((kind) => !order.includes(kind)).sort();
  return [...known, ...rest];
}

/* ------------------------------------------------------------------- text */

/** Non-ASCII letters this project actually meets, spelled out as the slug wants them. */
const SLUG_CHARS: Record<string, string> = {
  ä: 'ae',
  ö: 'oe',
  ü: 'ue',
  ß: 'ss',
  å: 'aa',
  ø: 'oe',
  æ: 'ae',
};

/** A slug for `text`, in the shape `isValidSlug` checks. */
export function slugify(text: string): string {
  let out = '';
  for (const ch of (text || '').toLowerCase()) out += SLUG_CHARS[ch] ?? ch;
  // Anything else accented (é, ô, …) loses its mark rather than a whole letter.
  out = out.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  return out.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

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
  const refs: string[] = [];
  for (const part of parts) {
    const url = part.match(/openstreetmap\.org\/(node|way|relation)\/(\d+)/i);
    const plain = part.match(/^(node|way|relation)\/(\d+)$/i);
    const hit = url ?? plain;
    if (!hit) return null;
    refs.push(`${hit[1].toLowerCase()}/${hit[2]}`);
  }
  return refs;
}
