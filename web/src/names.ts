// The name list as the frontend sees it: the search index (public/data/names.json),
// the one place that knows how a clicked map label maps back to a name-list row,
// and the small helpers both the search panel and the place card need.

import { useEffect, useState } from 'react';

import { DIALECTS, LOCAL_TAG } from './config';

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

/** A name together with where it came from: a dialect tag, or `local`, `frr`, `de`, `da`. */
export interface ShownName {
  name: string;
  source: string;
}

/**
 * The name to show for an entry in the selected view, and which one it is —
 * the counterpart of the label chain in style/localize.ts:
 *
 *  - dialect view: the selected dialect's own name, else the local Frisian
 *    one, else any other dialect's name the list has, else OSM's generic
 *    Frisian one, and German only when there is no Frisian name at all.
 *  - local view: only the local name, never another dialect's, then German.
 *
 * Danish is the last resort for the few places the list knows no German
 * name for (Aalborg, Skagen).
 */
export function resolveName(entry: NameEntry, labels: string): ShownName {
  // `?.` because names.json is fetched, not type-checked: an archive built
  // before the multi-dialect schema has no `names` object at all.
  const names = entry.names ?? {};
  const chain: [string, string | undefined][] =
    labels === LOCAL_TAG
      ? [['local', entry.local]]
      : [
          [labels, names[labels]],
          ['local', entry.local],
          ...DIALECTS.filter((d) => d.tag !== labels).map(
            (d): [string, string | undefined] => [d.tag, names[d.tag]],
          ),
          ['frr', entry.name_frr],
        ];
  chain.push(['de', entry.name_de], ['da', entry.name_da]);
  for (const [source, name] of chain) {
    if (name) return { name, source };
  }
  return { name: '', source: 'de' };
}

/** The name to show for an entry in the selected view, see `resolveName`. */
export function displayName(entry: NameEntry, labels: string): string {
  return resolveName(entry, labels).name;
}

// ------------------------------------------------------------- loading ----

export interface NamesData {
  entries: NameEntry[];
  /** Entries by `id` — the same string the tiles carry as `frasch:ref`. */
  byRef: Map<string, NameEntry>;
}

const EMPTY: NamesData = { entries: [], byRef: new Map() };

/**
 * Loads public/data/names.json once. Both consumers (search index and place
 * card) live in App, so the fetch belongs there rather than in either panel.
 */
export function useNames(): NamesData {
  const [data, setData] = useState<NamesData>(EMPTY);
  useEffect(() => {
    let cancelled = false;
    fetch('/data/names.json')
      .then((res) => res.json())
      .then((entries: NameEntry[]) => {
        if (cancelled) return;
        setData({ entries, byRef: new Map(entries.map((e) => [e.id, e])) });
      })
      .catch((err: unknown) => {
        console.error('Failed to load names.json', err);
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
