// Which of a place's names is shown, and which one it is: the label chain of
// the map (labelChain.ts), walked over a place's names instead of the tile
// properties.

import { labelChain } from '../labelChain';
import type { CardEntry } from './entry';

/**
 * A name together with where it came from: a dialect tag, or `local`, `frr`,
 * `nds`, `de`, `da`, or `osm` for OSM's generic name in no known language.
 */
export interface ShownName {
  name: string;
  source: string;
}

/**
 * The source to report for OSM's generic name: the language whose name it
 * is, where the entry knows one (Ribe is the Danish name, Niebüll the German
 * one), else `osm` — the card then names no language rather than a wrong one.
 */
function osmNameSource({ name_osm, name_de, name_da }: CardEntry): string {
  if (!name_osm) return 'osm';
  if (name_osm === name_de) return 'de';
  if (name_osm === name_da) return 'da';
  return 'osm';
}

/** The entry's value for one tile property of the label chain, and its source. */
function chainStep(entry: CardEntry, key: string): { name?: string; source: string } {
  switch (key) {
    case 'frasch:local':
      return { name: entry.local, source: 'local' };
    case 'name:frr':
      return { name: entry.name_frr, source: 'frr' };
    case 'name:nds':
      return { name: entry.name_nds, source: 'nds' };
    case 'name:de':
      return { name: entry.name_de, source: 'de' };
    // Both are OSM's generic name: `name:latin` is OpenMapTiles' Latin-script
    // copy of `name`, the same string in this part of the world.
    case 'name:latin':
    case 'name':
      return { name: entry.name_osm, source: osmNameSource(entry) };
  }
  const tag = key.replace(/^name:/, '');
  return { name: entry.names[tag], source: tag };
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
export function resolveName(entry: CardEntry, view: string): ShownName {
  for (const key of labelChain(view)) {
    const { name, source } = chainStep(entry, key);
    if (name) return { name, source };
  }
  if (entry.name_da) return { name: entry.name_da, source: 'da' };
  return { name: '', source: 'de' };
}

/** The name to show for an entry in the selected view, see `resolveName`. */
export function displayName(entry: CardEntry, view: string): string {
  return resolveName(entry, view).name;
}
