// The names a card has to show: those of the place's entry of the name list
// and those of the tile feature that was clicked, as one.

import type { PlaceSelection } from '../selection/placeSelection';
import type { CardNames, NameEntry } from './entry';
import { namesOfTile } from './tile';

/**
 * The names of a clicked label of a listed place: the name-list entry wins
 * field by field — it is the curated source — and the tile feature fills
 * whatever the list does not have. The exceptions are what depends on the
 * clicked object itself: its local name with the dialect area it lies in,
 * and OSM's own names.
 */
function mergedNames(entry: NameEntry, tile: CardNames): CardNames {
  return {
    ...entry,
    names: { ...tile.names, ...entry.names },
    // The tile's own local name and dialect area, never the entry's: the
    // entry lies where the first object of its row lies, and the clicked one
    // may be another object of that row, in another dialect area and with
    // another local name (Nordwarft) or outside every area, with none (Wisch).
    local: tile.local,
    dialect: tile.dialect,
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

/**
 * The names the card of a selection has: its entry's, for a search result or
 * a linked place; for a clicked label the tile feature's, merged into the
 * entry's where the list has the place.
 */
export function cardNames({ pick, entry }: PlaceSelection): CardNames {
  const tile = pick.via === 'map' ? namesOfTile(pick.props) : undefined;
  if (!tile) return entry ?? { names: {} };
  return entry ? mergedNames(entry, tile) : tile;
}
