// The places the curation view creates (#113): their provisional key, the
// names their form may repeat, and how one is listed and opened like a row
// of the worklist until `frasch curate apply` makes it one.

import type { NewPlace, PatchEntry } from './patch';
import type { ListedPlace, ListRow } from './worklist';

/**
 * The names of a name cell, their remarks left out: its variants are
 * separated by `;`, a remark is in brackets (names/README.md).
 */
function namesOfCell(cell: string | undefined): string[] {
  return (cell ?? '')
    .split(';')
    .map((variant) => variant.replace(/\([^()]*\)/g, '').trim())
    .filter(Boolean);
}

/** The first name of a cell; '' for none. */
function primaryName(cell: string | undefined): string {
  return namesOfCell(cell)[0] ?? '';
}

/** Every name of the cells, in lower case: what a duplicate is found by. */
function namesOf(cells: Record<string, string>): Set<string> {
  return new Set(
    Object.values(cells).flatMap((cell) => namesOfCell(cell).map((name) => name.toLowerCase())),
  );
}

/**
 * The places that already have a name of `cells` (column -> cell, as typed)
 * in any of their name columns, whatever the case. Names do repeat, so this
 * only warns.
 */
export function duplicates(
  cells: Record<string, string>,
  places: readonly ListedPlace[],
): ListedPlace[] {
  const typed = namesOf(cells);
  return places.filter((place) => [...namesOf(place.names)].some((name) => typed.has(name)));
}

/**
 * A fresh provisional key, `new:` and 32 hex digits (names/curate-patch.schema.json's
 * `provisional_key`): unique across sessions, and never a row id.
 */
export function newPlaceKey(): string {
  return `new:${crypto.randomUUID().replaceAll('-', '')}`;
}

/** What the form of a new place holds: every name column, empty ones too. */
export interface PlaceDraft {
  kind: string;
  names: Record<string, string>;
  note: string;
}

/** The cells of `names` that are not empty, trimmed. */
export function filledNames(names: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(names)
      .map(([column, cell]) => [column, cell.trim()])
      .filter(([, cell]) => cell),
  );
}

/** Whether a draft can be saved: it has a kind and a name. */
export function isComplete(draft: PlaceDraft): boolean {
  return Boolean(draft.kind) && Object.keys(filledNames(draft.names)).length > 0;
}

/**
 * The name a place goes by in the view: its first Frisian name, else its
 * German or Danish one — never its Low Saxon or Synnejysk one, as no row of
 * places.csv is named by those.
 */
function nameOf(names: Record<string, string>, frisianColumns: readonly string[]): string {
  const frisian = frisianColumns.map((column) => primaryName(names[column])).find(Boolean);
  return frisian || primaryName(names.de) || primaryName(names.da);
}

/** The `create` entry of a draft, with the name and German name its messages give. */
export function createEntry(
  key: string,
  draft: PlaceDraft,
  frisianColumns: readonly string[],
): PatchEntry {
  const names = filledNames(draft.names);
  const note = draft.note.trim();
  return {
    id: key,
    action: 'create',
    kind: draft.kind,
    name: nameOf(names, frisianColumns),
    de: primaryName(names.de),
    names,
    ...(note ? { note } : {}),
  };
}

/** A created place as the list and the duplicate warning show a row: keyed by its key. */
export function listedPlace(place: NewPlace): ListedPlace {
  return { id: place.key, kind: place.kind, names: place.names };
}

/**
 * A created place as a row of the list and its detail: what the worklist
 * would say about it, were it a row the matcher found nothing for yet.
 */
export function placeRow(place: NewPlace, frisianColumns: readonly string[]): ListRow {
  const { names } = place;
  return {
    id: place.key,
    line: 0,
    kind: place.kind,
    result: 'new',
    name: nameOf(names, frisianColumns),
    names: Object.fromEntries(frisianColumns.filter((c) => names[c]).map((c) => [c, names[c]])),
    name_de: primaryName(names.de),
    name_da: primaryName(names.da),
    slug_suggestion: '',
    de: names.de ?? '',
    da: names.da ?? '',
    hint: '',
    note: place.note,
    why: '',
    hint_point: null,
    candidates: [],
  };
}
