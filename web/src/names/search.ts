// The search over the name list: a MiniSearch index of every name of every
// entry.

import MiniSearch from 'minisearch';

import type { NameEntry } from './entry';

/** The entries a query finds, the best match first. */
export type Search = (query: string) => NameEntry[];

const MAX_RESULTS = 8;

/**
 * Index document: every name of an entry flattened into one searchable
 * string. A place must be findable under any of its dialect names no matter
 * which view is selected — somebody typing "Naibel" while the map is in
 * Fering still means Niebüll. Its id is the entry's position in the list, so
 * a hit names its entry and the index never has to know the entry's schema.
 */
interface IndexedEntry {
  id: number;
  text: string;
}

/** All of an entry's names in one string, each once. */
function searchText(entry: NameEntry): string {
  const names = [
    ...Object.values(entry.names),
    entry.local,
    entry.name_nds,
    entry.name_osm,
    entry.name_de,
  ];
  return [...new Set(names.filter(Boolean))].join(' ');
}

/** The search over `entries`: by the beginning of any name, forgiving a typo. */
export function createSearch(entries: NameEntry[]): Search {
  const index = new MiniSearch<IndexedEntry>({
    fields: ['text'],
    searchOptions: { prefix: true, fuzzy: 0.2 },
  });
  index.addAll(entries.map((entry, id) => ({ id, text: searchText(entry) })));
  return (query) =>
    index
      .search(query)
      .slice(0, MAX_RESULTS)
      .map((hit) => entries[hit.id as number]);
}
