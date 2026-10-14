// A place label of the vector tiles: which of its properties is which of a
// place's names. The one table of it in the frontend; frasch/placenames.py's
// TILE_KEY is the table the tiles are written by.

import { DIALECTS } from '../dialects/registry';
import type { CardNames } from './entry';

/** Properties of a clicked vector-tile feature (source-layer `place`). */
export type TileProps = Record<string, unknown>;

/**
 * Tile property → the field it is of a place's names. Two properties of one
 * field are in the order they are read in: our own `frasch:kind` before
 * OpenMapTiles' `class`, and `name:latin` (OpenMapTiles' Latin-script copy of
 * `name`, the same string in this part of the world) before `name`.
 *
 * OpenMapTiles' `name_de` is not in it: that is `name:de` where OSM has one
 * and the plain `name` everywhere else, which north of the border is Danish.
 * A name in a dialect is not either: its property is `name:<tag>`.
 */
const FIELD_OF_TILE_KEY = {
  'frasch:local': 'local',
  'frasch:dialect': 'dialect',
  'frasch:variety': 'variety',
  'frasch:kind': 'kind',
  class: 'kind',
  'name:frr': 'name_frr',
  'name:nds': 'name_nds',
  'name:de': 'name_de',
  'name:da': 'name_da',
  'name:latin': 'name_osm',
  name: 'name_osm',
} as const;

type TileKey = keyof typeof FIELD_OF_TILE_KEY;

/** A field of a place's names that a tile property carries. */
export type TileField = (typeof FIELD_OF_TILE_KEY)[TileKey];

const DIALECT_KEY_PREFIX = 'name:';

/** The field `key` is of a place's names, or none: a name in a dialect, see `dialectOfTileKey`. */
export function fieldOfTileKey(key: string): TileField | undefined {
  return key in FIELD_OF_TILE_KEY ? FIELD_OF_TILE_KEY[key as TileKey] : undefined;
}

/** The dialect tag of the tile property of a name in a dialect: `name:frr-x-mooring`. */
export function dialectOfTileKey(key: string): string {
  return key.slice(DIALECT_KEY_PREFIX.length);
}

function str(props: TileProps, key: string): string | undefined {
  const value = props[key];
  return typeof value === 'string' && value !== '' ? value : undefined;
}

/**
 * The names a tile feature carries: all the card has for a place the name
 * list does not have (a plain German village), and what fills the gaps of
 * one it does — OSM's `name:da` on Föhr, say, where our own `da` column is
 * empty.
 */
export function namesOfTile(props: TileProps): CardNames {
  const names: CardNames = { names: {} };
  for (const { tag } of DIALECTS) {
    const name = str(props, DIALECT_KEY_PREFIX + tag);
    if (name) names.names[tag] = name;
  }
  for (const [key, field] of Object.entries(FIELD_OF_TILE_KEY)) {
    names[field] ??= str(props, key);
  }
  return names;
}
