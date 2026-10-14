// The name list as loaded: public/data/names.json, fetched once, with the
// lookup of the entry a reference names and the search over all of them.

import { useEffect, useState } from 'react';

import { siteUrl } from '../site';
import { osmRefs } from './osmRef';
import type { BuiltFrom } from '../map/provenance';
import type { NameEntry } from './entry';
import { createSearch, type Search } from './search';

export interface NamesData {
  /**
   * `error` when names.json could not be loaded: search then has nothing to
   * search and `?place=` links nothing to open, which the UI has to say
   * rather than answer every query with "no results".
   */
  status: 'loading' | 'ready' | 'error';
  /** The entry a `?place=` link or a tile's `frasch:ref` names, see `entryLookup`. */
  find: EntryLookup;
  /** The entries a typed query finds, see names/search.ts. */
  search: Search;
  /** What the list was built from, to compare with the tiles' (see provenance.ts). */
  builtFrom?: BuiltFrom;
}

/** Finds the entry a reference names, see `entryLookup`. */
export type EntryLookup = (ref: string) => NameEntry | undefined;

/**
 * Looks entries up by the row id — what the tiles carry as `frasch:ref` and a
 * `?place=` link names — and, for what was shared or built before the row
 * ids, by the reference that used to be the id: any of the row's OSM
 * references, or the QID of a row without one. No two rows have one object
 * or item (frasch/placelist.py refuses such a list), and ids are lowercase
 * slugs without a `/`, so they never clash with a reference or a QID. The
 * `#<csv line>` an old link may end in told two rows on one object apart;
 * it is ignored.
 */
export function entryLookup(entries: NameEntry[]): EntryLookup {
  const byRef = new Map<string, NameEntry>();
  for (const entry of entries) {
    for (const ref of [entry.id, ...osmRefs(entry.osm), entry.wikidata]) {
      if (ref) byRef.set(ref, entry);
    }
  }
  return (ref) => byRef.get(ref) ?? byRef.get(ref.split('#')[0]);
}

/** names.json as loaded: its entries, and what it was built from. */
export interface NameList {
  entries: NameEntry[];
  builtFrom: BuiltFrom;
}

/**
 * The name list of a fetched names.json — the one place that looks at what
 * came over the wire; from here on the app trusts the types. Throws on what
 * is no name list at all, and drops (and logs) a place without an id or with
 * a repeated one: either would take the whole search index down.
 */
export function parseNames(json: unknown): NameList {
  const { built_from: builtFrom, places } = (json ?? {}) as {
    built_from: BuiltFrom;
    places?: unknown;
  };
  if (!Array.isArray(places)) throw new Error('no list of places');
  const ids = new Set<string>();
  const entries = (places as NameEntry[]).filter(({ id }) => {
    if (typeof id !== 'string' || id === '' || ids.has(id)) return false;
    ids.add(id);
    return true;
  });
  if (entries.length < places.length) {
    const dropped = places.length - entries.length;
    console.warn(`names.json: skipped ${dropped} places without an id or with a repeated one`);
  }
  return { entries, builtFrom };
}

/** The list before it has loaded, or after it failed to: nothing to find. */
const EMPTY = { find: () => undefined, search: () => [] } satisfies Partial<NamesData>;
const LOADING: NamesData = { status: 'loading', ...EMPTY };
const FAILED: NamesData = { status: 'error', ...EMPTY };

function loaded({ entries, builtFrom }: NameList): NamesData {
  return { status: 'ready', find: entryLookup(entries), search: createSearch(entries), builtFrom };
}

/** Where the name list is served, under the site's base path. */
export function namesUrl(): string {
  return siteUrl('data/names.json');
}

/**
 * Loads public/data/names.json once. Both consumers (the search box and the
 * place card) live in App, so the fetch belongs there rather than in either.
 */
export function useNames(): NamesData {
  const [data, setData] = useState<NamesData>(LOADING);
  useEffect(() => {
    let cancelled = false;
    fetch(namesUrl())
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        // An SPA fallback answers a missing file with index.html and a 200;
        // res.json() rejects that, and anything else that is not the list.
        return res.json();
      })
      .then((json: unknown) => {
        if (!cancelled) setData(loaded(parseNames(json)));
      })
      .catch((err: unknown) => {
        console.error('Failed to load names.json', err);
        if (!cancelled) setData(FAILED);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return data;
}
