// The browser's side of the curation worklist (names/work/curate.json, which
// `frasch curate export` writes): its shape, loading it together with the
// patch, and the list's filter. The
// contract itself is names/curate-worklist.schema.json; worklist.test.ts
// pins the types below to it.

import { fetchJson } from '../shell/fetchJson';
import type { PatchEntry } from './patch';

/** One candidate of a worklist row. */
export interface CurateCandidate {
  /** "node/123" | "way/123" | "relation/123". */
  ref: string;
  name: string;
  class: string;
  /** Distance from the centre of North Frisia in km, as `frasch match` computed it; null without a position. */
  km: number | null;
  /** null when the candidate scan could not place the object. */
  lon: number | null;
  lat: number | null;
  /** Decisive tags as one string, e.g. "place=hamlet". */
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
  /** A slug for a `local/<slug>` reference of the row, folded like a row id; '' when the names give none. */
  slug_suggestion: string;
  /** The German and Danish cells, raw: every variant with its remarks. */
  de: string;
  da: string;
  hint: string;
  note: string;
  /** Why the matcher gave up (matches.jsonl `why`). */
  why: string;
  /** [lon, lat, radius_km] of the location hint, or null. */
  hint_point: [number, number, number] | null;
  candidates: CurateCandidate[];
}

/**
 * A row of the list: one of the worklist, or a place the view created
 * (newPlaces.ts `placeRow`), whose result is `new` and whose `line` is 0.
 */
export type ListRow = Omit<CurateRow, 'result'> & { result: CurateRow['result'] | 'new' };

/** A row of places.csv by its names, for a new place's duplicate warning. */
export interface ListedPlace {
  id: string;
  kind: string;
  /** Every non-empty cell of `all_name_columns`, raw, keyed by column name. */
  names: Record<string, string>;
}

/** lon_min, lat_min, lon_max, lat_max. */
export type Bbox = [number, number, number, number];

/** `names/work/curate.json` as a whole. */
export interface CurateWorklist {
  bbox: Bbox;
  /** Every kind, in the order the list walks them. */
  kind_order: string[];
  /** The Frisian name columns of places.csv in list order: a place goes by its first name among these. */
  frisian_columns: string[];
  /** Every name column of places.csv in list order (`frisian_columns`, `de`, `nds`, `jut`, `da`): a new place's form has a cell for each. */
  all_name_columns: string[];
  /** The kinds whose local reference can carry an area instead of a bare point. */
  polygon_kinds: string[];
  /** The OSM tags that say what kind of thing an object is, the most telling first. */
  class_keys: string[];
  /** The `place` values of a settlement, as a candidate's `class` has them. */
  settlement_places: string[];
  /** The results a row can have, for the filter. */
  results: CurateRow['result'][];
  rows: CurateRow[];
  /** Every row of places.csv, by its names. */
  places: ListedPlace[];
}

/* ---------------------------------------------------------------- loading */

/** The worklist together with the decisions made on it so far. */
export interface LoadedWorklist {
  worklist: CurateWorklist;
  /** The lines of the patch, oldest first. */
  entries: PatchEntry[];
}

/**
 * The worklist and the decisions made so far, from the dev-server endpoints
 * in web/vite-plugins/curate.ts. Rejects with a message fit for the panel.
 */
export async function loadWorklist(): Promise<LoadedWorklist> {
  const [worklist, patch] = await Promise.all([
    fetchJson<CurateWorklist>('/__curate/worklist'),
    fetchJson<{ entries?: PatchEntry[] }>('/__curate/patch'),
  ]);
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

export function filterRows<Row extends ListRow>(
  rows: Row[],
  filter: RowFilter,
  isDone: (id: string) => boolean,
): Row[] {
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
 * The kinds of `rows` — the worklist's and the created places' — in the
 * exporter's `kind_order` (`order`). Anything the exporter emitted but
 * kind_order does not know about still has to be reachable, so the
 * leftovers come after it.
 */
export function rowKinds(
  order: readonly string[],
  rows: readonly Pick<ListRow, 'kind'>[],
): string[] {
  const present = new Set(rows.map((row) => row.kind));
  const known = order.filter((kind) => present.has(kind));
  const rest = [...present].filter((kind) => !order.includes(kind)).sort();
  return [...known, ...rest];
}
