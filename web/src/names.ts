// The name list as the frontend sees it: the search index (public/data/names.json),
// the one place that knows how a clicked map label maps back to a name-list row,
// and the small helpers both the search panel and the place card need.

import { useEffect, useState } from 'react';

import { DIALECTS, siteUrl } from './config';
import { labelChain } from './labelChain';

/**
 * One entry of public/data/names.json, written by names/export_search_index.py.
 * Only non-empty values are exported, so every optional field is genuinely
 * absent rather than an empty string.
 */
export interface NameEntry {
  /** Stable identifier, e.g. "node/240044177" (or "<osm id>#<csv line>" for a second row on the same object), or "local/<slug>" for a place OSM does not have. */
  id: string;
  /** Dialect names by registry tag, e.g. { "frr-x-mooring": "Naibel" }. */
  names: Record<string, string>;
  /** Name used by the people of the place itself (tile attribute `frasch:local`). */
  local?: string;
  /** Dialect area the place lies in, e.g. "frr-x-fering". */
  dialect?: string;
  /** Sub-dialect remark of the local name, e.g. "Foortuftinge". */
  variety?: string;
  /**
   * Frisian name of no particular dialect — OSM's own `name:frr`, never our
   * name list, which always knows which dialect a name is in. Only set on an
   * entry built from a tile feature; the style labels with it too (see the
   * label chain in style/localize.ts), so the card has to know about it or it
   * would contradict the label the user just clicked.
   */
  name_frr?: string;
  /**
   * Low Saxon name — OSM's `name:nds`, never our name list (it has no Low
   * Saxon column). names/export_search_index.py takes it from the matched OSM
   * object, a tile feature carries it itself. The label chain falls back to it
   * before German, so the card needs it for the same reason as `name_frr`.
   */
  name_nds?: string;
  /** German name, shown as a hint next to a Frisian one. */
  name_de: string;
  /** Danish name, where the list has one. */
  name_da?: string;
  /** Wikidata QID of the place, where the row has one. */
  wikidata?: string;
  lon: number;
  lat: number;
  kind: string;
}

/** Properties of a clicked vector-tile feature (source-layer `place`). */
export type TileProps = Record<string, unknown>;

/** What the place card is showing. */
export interface PlaceSelection {
  /** The name-list entry, when the place has one. */
  entry?: NameEntry;
  /** Tile properties of the clicked feature; absent when the search opened the card. */
  props?: TileProps;
  /** Tile feature id of the clicked feature, see `osmRefFromFeatureId`. */
  featureId?: string | number;
}

/** A name together with where it came from: a dialect tag, or `local`, `frr`, `nds`, `de`, `da`. */
export interface ShownName {
  name: string;
  source: string;
}

/** The entry's value for one tile property of the label chain, and its source. */
function chainStep(entry: NameEntry, key: string): { name?: string; source: string } {
  switch (key) {
    case 'frasch:local':
      return { name: entry.local, source: 'local' };
    case 'name:frr':
      return { name: entry.name_frr, source: 'frr' };
    case 'name:nds':
      return { name: entry.name_nds, source: 'nds' };
    // `name_de` already is the tile's `name:de`, else its plain `name` (see
    // entryFromTile), so the generic tail of the chain lands here too.
    case 'name:de':
    case 'name:latin':
    case 'name':
      return { name: entry.name_de, source: 'de' };
  }
  const tag = key.replace(/^name:/, '');
  // `?.` because names.json is fetched, not type-checked: an archive built
  // before the multi-dialect schema has no `names` object at all.
  return { name: entry.names?.[tag], source: tag };
}

/**
 * The name to show for an entry in the selected view, and which one it is:
 * the same label chain the map follows (labelChain.ts), walked over the
 * entry instead of the tile properties, so the card and the search results
 * name a place exactly as its map label does.
 *
 * Danish is the last resort for the few places the list knows no German
 * name for (Aalborg, Skagen).
 */
export function resolveName(entry: NameEntry, labels: string): ShownName {
  for (const key of labelChain(labels)) {
    const { name, source } = chainStep(entry, key);
    if (name) return { name, source };
  }
  if (entry.name_da) return { name: entry.name_da, source: 'da' };
  return { name: '', source: 'de' };
}

/** The name to show for an entry in the selected view, see `resolveName`. */
export function displayName(entry: NameEntry, labels: string): string {
  return resolveName(entry, labels).name;
}

// ------------------------------------------------------------- loading ----

export interface NamesData {
  /**
   * `error` when names.json could not be loaded: search then has nothing to
   * search and `?place=` links nothing to open, which the UI has to say
   * rather than answer every query with "no results".
   */
  status: 'loading' | 'ready' | 'error';
  entries: NameEntry[];
  /** Entries by `id` — the same string the tiles carry as `frasch:ref`. */
  byRef: Map<string, NameEntry>;
}

const LOADING: NamesData = { status: 'loading', entries: [], byRef: new Map() };
const FAILED: NamesData = { status: 'error', entries: [], byRef: new Map() };

/** Where the name list is served, under the site's base path. */
export function namesUrl(): string {
  return siteUrl('data/names.json');
}

/**
 * Loads public/data/names.json once. Both consumers (search index and place
 * card) live in App, so the fetch belongs there rather than in either panel.
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
      .then((entries: unknown) => {
        if (!Array.isArray(entries)) throw new Error('not a list of entries');
        if (cancelled) return;
        const list = entries as NameEntry[];
        setData({ status: 'ready', entries: list, byRef: new Map(list.map((e) => [e.id, e])) });
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

// ---------------------------------------------------- tiles -> entries ----

function str(props: TileProps | undefined, key: string): string | undefined {
  const v = props?.[key];
  return typeof v === 'string' && v !== '' ? v : undefined;
}

/**
 * A name-list-shaped view of a tile feature, for places the name list does
 * not have (a plain German village) and to fill gaps in the ones it does —
 * OSM's `name:da` on Föhr, say, where our own `da` column is empty.
 * Coordinates are not part of it; nothing on the card needs them.
 */
export function entryFromTile(props: TileProps): NameEntry {
  const names: Record<string, string> = {};
  for (const d of DIALECTS) {
    const name = str(props, `name:${d.tag}`);
    if (name) names[d.tag] = name;
  }
  return {
    id: str(props, 'frasch:ref') ?? '',
    names,
    local: str(props, 'frasch:local'),
    dialect: str(props, 'frasch:dialect'),
    variety: str(props, 'frasch:variety'),
    name_frr: str(props, 'name:frr'),
    name_nds: str(props, 'name:nds'),
    // `name_de` is OpenMapTiles' own German field; `name` is whatever OSM
    // calls the place, which in this region is the German name.
    name_de: str(props, 'name:de') ?? str(props, 'name_de') ?? str(props, 'name') ?? '',
    name_da: str(props, 'name:da'),
    lon: 0,
    lat: 0,
    kind: str(props, 'frasch:kind') ?? str(props, 'class') ?? '',
  };
}

/**
 * What the card renders: the name-list entry wins field by field — it is the
 * curated source — and the clicked tile feature fills whatever the list does
 * not have. Without an entry the tile alone carries the card.
 */
export function cardEntry(selection: PlaceSelection): NameEntry {
  const tile = selection.props ? entryFromTile(selection.props) : undefined;
  const entry = selection.entry;
  if (!entry) return tile ?? { id: '', names: {}, name_de: '', lon: 0, lat: 0, kind: '' };
  if (!tile) return entry;
  return {
    ...entry,
    names: { ...tile.names, ...entry.names },
    local: entry.local ?? tile.local,
    dialect: entry.dialect ?? tile.dialect,
    variety: entry.variety ?? tile.variety,
    name_frr: tile.name_frr,
    // The tile's own value first: it is what the label the user just clicked
    // shows, while the entry's comes from the OSM extract the name list was
    // matched against, which may be older.
    name_nds: tile.name_nds ?? entry.name_nds,
    name_de: entry.name_de || tile.name_de,
    name_da: entry.name_da ?? tile.name_da,
    kind: entry.kind || tile.kind,
  };
}

// --------------------------------------------------------------- links ----

const OSM_TYPES = new Set(['node', 'way', 'relation']);

/**
 * The OSM object of a reference (`node/240042766`), or null for one that is
 * not an OSM object: our own `local/<slug>` places, and the QID a row without
 * an `osm` column is keyed by.
 */
export function osmUrl(ref: string | undefined): string | null {
  if (!ref) return null;
  // A second row on the same object is exported as "<ref>#<csv line>".
  const [type, rest] = ref.split('#')[0].split('/');
  if (!OSM_TYPES.has(type) || !/^\d+$/.test(rest ?? '')) return null;
  return `https://www.openstreetmap.org/${type}/${rest}`;
}

export function wikidataUrl(qid: string | undefined): string | null {
  return qid && /^Q\d+$/.test(qid) ? `https://www.wikidata.org/wiki/${qid}` : null;
}

/**
 * The OSM object behind a tile feature id. Planetiler encodes it as
 * `osmId * 10 + type` (1 = node, 2 = way, 3 = relation) — verified against
 * our archive: Niebüll 2400427661 = node/240042766, Föhr 33525413 =
 * relation/3352541, Gröde 10871603522 = way/1087160352.
 *
 * Only needed for features the name list does not have, which carry no
 * `frasch:ref`; everything else is keyed by that. Returns null for anything
 * that does not decode (a synthetic object of ours, a missing id), and the
 * card then simply shows no OSM link.
 */
export function osmRefFromFeatureId(id: string | number | undefined): string | null {
  const n = typeof id === 'string' ? Number(id) : id;
  if (typeof n !== 'number' || !Number.isSafeInteger(n) || n <= 0) return null;
  const type = ['', 'node', 'way', 'relation'][n % 10];
  return type ? `${type}/${(n - (n % 10)) / 10}` : null;
}

/** The reference of what the card is showing, for the links at its foot. */
export function placeRef(selection: PlaceSelection): string | null {
  return (
    selection.entry?.id ??
    str(selection.props, 'frasch:ref') ??
    osmRefFromFeatureId(selection.featureId)
  );
}
