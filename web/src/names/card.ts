// What a place's card shows: the place's entry of the name list, filled up
// from the tile feature that was clicked.

import { DIALECTS } from '../config';
import type { CardEntry, NameEntry } from './entry';

/** Properties of a clicked vector-tile feature (source-layer `place`). */
export type TileProps = Record<string, unknown>;

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
export function entryFromTile(props: TileProps): CardEntry {
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
    // `name_de` is OpenMapTiles' own German field. The plain `name` is not a
    // German one north of the border, so it only goes into `name_osm`.
    name_de: str(props, 'name:de') ?? str(props, 'name_de') ?? '',
    name_osm: str(props, 'name:latin') ?? str(props, 'name'),
    name_da: str(props, 'name:da'),
    lon: 0,
    lat: 0,
    kind: str(props, 'frasch:kind') ?? str(props, 'class') ?? '',
  };
}

/**
 * What the card renders: the name-list entry wins field by field — it is the
 * curated source — and the clicked tile feature fills whatever the list does
 * not have. The exceptions are what depends on the clicked object itself:
 * its local name with the dialect area it lies in, and OSM's own names.
 * Without an entry the tile alone carries the card.
 *
 * `entry` is the place's name-list entry, when it has one; `props` are the
 * tile properties of the clicked feature, absent when no click opened the
 * card.
 */
export function cardEntry(entry: NameEntry | undefined, props?: TileProps): CardEntry {
  const tile = props ? entryFromTile(props) : undefined;
  if (!entry) return tile ?? { id: '', names: {}, name_de: '', lon: 0, lat: 0, kind: '' };
  if (!tile) return entry;
  return {
    ...entry,
    names: { ...tile.names, ...entry.names },
    // The tile's own local name first, and with it the tile's dialect area:
    // the entry lies where the first object of its row lies, and the clicked
    // one may be another object of that row, in another dialect area and
    // with another local name (Nordwarft).
    local: tile.local ?? entry.local,
    dialect: tile.local ? tile.dialect : (entry.dialect ?? tile.dialect),
    variety: entry.variety ?? tile.variety,
    name_frr: tile.name_frr,
    // The tile's own value first: it is what the label the user just clicked
    // shows, while the entry's comes from the OSM extract the name list was
    // matched against, which may be older.
    name_nds: tile.name_nds ?? entry.name_nds,
    // Likewise: the label may be the tile's generic name.
    name_osm: tile.name_osm ?? entry.name_osm,
    name_de: entry.name_de || tile.name_de,
    name_da: entry.name_da ?? tile.name_da,
    kind: entry.kind || tile.kind,
  };
}
