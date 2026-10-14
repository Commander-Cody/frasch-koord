// Which of a place's names is shown, and which one it is: the label chain of
// the map (labelChain.ts), walked over a place's names instead of the tile
// properties.

import { labelChain } from '../labelChain';
import type { CardNames } from './entry';
import { dialectOfTileKey, fieldOfTileKey, type TileField } from './tile';

/** A language a name is in that is no dialect of the registry; `frr` is OSM's Frisian of no particular dialect. */
export type Language = 'frr' | 'nds' | 'de' | 'da';

/**
 * Which of a place's names a name is: its name in a dialect of the registry,
 * its local form (with the dialect of its area, where a card says the local
 * form is that dialect's name), its name in a language, or `unknown` for
 * OSM's generic name where it is the name in no language known of the place.
 */
export type NameSource =
  | { kind: 'dialect'; tag: string }
  | { kind: 'local'; dialect?: string }
  | { kind: 'language'; language: Language }
  | { kind: 'unknown' };

/** A name together with which of the place's names it is. */
export interface ShownName {
  name: string;
  source: NameSource;
}

const LANGUAGE_OF_FIELD: Partial<Record<TileField, Language>> = {
  name_frr: 'frr',
  name_nds: 'nds',
  name_de: 'de',
  name_da: 'da',
};

/**
 * The language of OSM's generic name, where the place has a name in a
 * language that is the same one (Ribe is the Danish name, Niebüll the German
 * one). None otherwise: a card then names no language rather than a wrong one.
 */
function genericNameLanguage({ name_osm, name_de, name_da }: CardNames): Language | undefined {
  if (name_osm === name_de) return 'de';
  if (name_osm === name_da) return 'da';
  return undefined;
}

function sourceOfField(field: TileField, names: CardNames): NameSource {
  if (field === 'local') return { kind: 'local' };
  const language = field === 'name_osm' ? genericNameLanguage(names) : LANGUAGE_OF_FIELD[field];
  return language ? { kind: 'language', language } : { kind: 'unknown' };
}

/** The place's name for one tile property of the label chain, where it has one. */
function chainStep(names: CardNames, key: string): ShownName | undefined {
  const field = fieldOfTileKey(key);
  const tag = dialectOfTileKey(key);
  const name = field ? names[field] : names.names[tag];
  if (!name) return undefined;
  return { name, source: field ? sourceOfField(field, names) : { kind: 'dialect', tag } };
}

/**
 * The name to show for a place in the selected view, and which one it is:
 * the same label chain the map follows (labelChain.ts), walked over the
 * place's names instead of the tile properties, so the card and the search
 * results name a place exactly as its map label does.
 *
 * Danish is the last resort for the few places the list knows no German
 * name for (Aalborg, Skagen). A place without any name has an empty one, of
 * unknown source.
 */
export function resolveName(names: CardNames, view: string): ShownName {
  for (const key of labelChain(view)) {
    const shown = chainStep(names, key);
    if (shown) return shown;
  }
  if (names.name_da) return { name: names.name_da, source: { kind: 'language', language: 'da' } };
  return { name: '', source: { kind: 'unknown' } };
}

/** The name to show for a place in the selected view, see `resolveName`. */
export function displayName(names: CardNames, view: string): string {
  return resolveName(names, view).name;
}
