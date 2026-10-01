// The browser's side of the curation patch (names/work/curate-patch.jsonl):
// what one decision looks like, and which rows are decided. The contract
// itself is names/curate-patch.schema.json; curatePatch.test.ts pins
// PatchEntry to it.

import patchSchema from '../../../names/curate-patch.schema.json';

/** One line of `names/work/curate-patch.jsonl`. */
export interface PatchEntry {
  /** The places.csv row's `id` — what frasch/curate.py's `apply` finds the row by. */
  id: string;
  /** Its line in places.csv when the worklist was exported; for messages only. */
  line: number;
  kind: string;
  name: string;
  de: string;
  action: 'osm' | 'local' | 'skip' | 'clear';
  osm?: string;
  wikidata?: string;
  slug?: string;
  lat?: number;
  lon?: number;
  polygon_km2?: number;
  note?: string;
  at?: string;
}

/** What the panel decides about a row; the row's own fields come from the worklist. */
export type Decision = Omit<PatchEntry, 'id' | 'line' | 'kind' | 'name' | 'de'>;

/**
 * Appends `entry` to the patch through the dev server (web/vite-plugins/curate.ts)
 * and resolves the entry as stored. Rejects with a message fit for the panel.
 */
export async function postPatchEntry(entry: PatchEntry): Promise<PatchEntry> {
  const res = await fetch('/__curate/patch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  });
  const body = (await res.json().catch(() => null)) as {
    ok?: boolean;
    entry?: PatchEntry;
    error?: string;
  } | null;
  if (!res.ok || !body?.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
  return body.entry ?? entry;
}

/**
 * The decided rows: the last entry per row id, as frasch/curate.py's `apply` reads
 * the patch. A `clear` entry withdraws the row's decision.
 */
export function decidedRows(entries: PatchEntry[]): Map<string, PatchEntry> {
  const last = new Map<string, PatchEntry>();
  for (const entry of entries) last.set(entry.id, entry);
  for (const [id, entry] of last) {
    if (entry.action === 'clear') last.delete(id);
  }
  return last;
}

const WIKIDATA = new RegExp(patchSchema.properties.wikidata.pattern);

/**
 * The Wikidata id an OSM object's `wikidata` tag names, if it names exactly
 * one. OSM sometimes lists several (`Q1;Q2`), which the patch contract — and
 * so `apply` — refuses; the panel then saves none.
 */
export function singleWikidataId(tag: string | undefined): string | undefined {
  const id = tag?.trim();
  return id && WIKIDATA.test(id) ? id : undefined;
}

const SLUG = new RegExp(patchSchema.$defs.slug.pattern);

/** Whether `slug` has the shape of a row id and of a `local/<slug>` reference. */
export function isValidSlug(slug: string): boolean {
  return SLUG.test(slug);
}
