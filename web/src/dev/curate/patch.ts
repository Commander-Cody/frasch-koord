// The browser's side of the curation patch (names/work/curate-patch.jsonl):
// what one decision looks like, which rows are decided, and which places
// the view created. The contract itself is names/curate-patch.schema.json;
// patch.test.ts pins PatchEntry to it.

import patchSchema from '../../../../names/curate-patch.schema.json';
import { fetchJson } from '../shell/fetchJson';
import type { LoadedWorklist } from './worklist';

/** One line of `names/work/curate-patch.jsonl`. */
export interface PatchEntry {
  /**
   * The places.csv row's `id` — what frasch/curate.py's `apply` finds the row
   * by —, or the provisional key of a place the view created (`newPlaceKey`).
   */
  id: string;
  /** Its line in places.csv when the worklist was exported; for messages only. */
  line?: number;
  /** The row's kind; for messages only, but a `create`'s is the new row's. */
  kind?: string;
  name?: string;
  de?: string;
  action: 'osm' | 'local' | 'skip' | 'clear' | 'create' | 'discard';
  osm?: string;
  wikidata?: string;
  slug?: string;
  lat?: number;
  lon?: number;
  polygon_km2?: number;
  /** A `create`'s name cells by column, only those that are not empty. */
  names?: Record<string, string>;
  note?: string;
  at?: string;
}

/** What the panel decides about a row; the row's own fields come from the worklist. */
export type Decision = Omit<PatchEntry, 'id' | 'line' | 'kind' | 'name' | 'de' | 'names'> & {
  action: 'osm' | 'local' | 'skip' | 'clear';
};

/** The actions about a created place itself rather than its location. */
const PLACE_ACTIONS: readonly PatchEntry['action'][] = ['create', 'discard'];

function isAboutPlace(entry: PatchEntry): boolean {
  return PLACE_ACTIONS.includes(entry.action);
}

/** A place the view created, as its last `create` says, until `apply` makes it a row. */
export interface NewPlace {
  /** Its provisional key, `new:…`: what its decision is keyed on too. */
  key: string;
  kind: string;
  /** Its name cells by column, only those that are not empty. */
  names: Record<string, string>;
  note: string;
}

/**
 * Appends `entry` to the patch through the dev server (web/vite-plugins/curate.ts)
 * and resolves the entry as stored. Rejects with a message fit for the panel.
 */
export async function postPatchEntry(entry: PatchEntry): Promise<PatchEntry> {
  const body = await fetchJson<{ ok?: boolean; entry?: PatchEntry; error?: string }>(
    '/__curate/patch',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry),
    },
  );
  if (!body.ok) throw new Error(body.error ?? 'the dev server did not store it');
  return body.entry ?? entry;
}

/** Changes what the panel loaded, as useDevResource's `update` does. */
export type UpdateLoaded = (change: (data: LoadedWorklist) => LoadedWorklist) => void;

/** Stores `entry` and mirrors the appended line in what the panel loaded, so it shows at once. */
export async function storeEntry(update: UpdateLoaded, entry: PatchEntry): Promise<void> {
  const stored = await postPatchEntry(entry);
  update((loaded) => ({ ...loaded, entries: [...loaded.entries, stored] }));
}

/**
 * The decided rows and created places: the last decision per id, as
 * frasch/curate.py's `apply` reads the patch. A `clear` entry withdraws the
 * decision, and so does the `discard` of a created place.
 */
export function decidedRows(entries: PatchEntry[]): Map<string, PatchEntry> {
  const discarded = new Set(
    lastAboutPlaces(entries)
      .filter((entry) => entry.action === 'discard')
      .map((entry) => entry.id),
  );
  const last = new Map<string, PatchEntry>();
  for (const entry of entries) {
    if (!isAboutPlace(entry)) last.set(entry.id, entry);
  }
  for (const [id, entry] of last) {
    if (entry.action === 'clear' || discarded.has(id)) last.delete(id);
  }
  return last;
}

/** The last `create` or `discard` per created place, in the order the places were created. */
function lastAboutPlaces(entries: PatchEntry[]): PatchEntry[] {
  const last = new Map<string, PatchEntry>();
  for (const entry of entries) {
    if (isAboutPlace(entry)) last.set(entry.id, entry);
  }
  return [...last.values()];
}

/** The places the view created and did not discard, each as its last `create` says. */
export function createdPlaces(entries: PatchEntry[]): NewPlace[] {
  return lastAboutPlaces(entries)
    .filter((entry) => entry.action === 'create')
    .map((entry) => ({
      key: entry.id,
      kind: entry.kind ?? '',
      names: entry.names ?? {},
      note: entry.note ?? '',
    }));
}

/** What a decision chose, in a word: the reference it saves, or that it skipped the row. */
export function decisionLabel(entry: PatchEntry): string {
  if (entry.action === 'osm') return entry.osm ?? '';
  if (entry.action === 'local') return `local/${entry.slug ?? ''}`;
  if (entry.action === 'skip') return 'skipped';
  return '';
}

const WIKIDATA = new RegExp(patchSchema.$defs.wikidata.pattern);

/**
 * The Wikidata id an OSM object's `wikidata` tag names, if it names exactly
 * one. OSM sometimes lists several (`Q1;Q2`), which the patch contract — and
 * so `apply` — refuses; the panel then saves none.
 */
export function singleWikidataId(tag: string | undefined): string | undefined {
  const id = tag?.trim() ?? '';
  return WIKIDATA.test(id) ? id : undefined;
}

const SLUG = new RegExp(patchSchema.$defs.slug.pattern);

/** Whether `slug` has the shape of a row id and of a `local/<slug>` reference. */
export function isValidSlug(slug: string): boolean {
  return SLUG.test(slug);
}
