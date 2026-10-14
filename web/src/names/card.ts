// What a place's card shows: which names, in which order, and what each one
// is. Pure; ui/PlaceCard.tsx gives every source its label and renders.

import { DIALECTS } from '../config';
import type { PlaceSelection } from '../selection/placeSelection';
import { cardNames } from './cardNames';
import type { CardNames } from './entry';
import { resolveName, type Language, type NameSource, type ShownName } from './resolveName';

/** One line of the name list below the headline. */
export interface CardLine {
  source: NameSource;
  name: string;
  /** The sub-dialect the local form belongs to (`frasch:variety`). */
  note?: string;
}

export interface CardModel {
  /** The place's name in the view; empty for a place without any name. */
  headline: string;
  /** Which of the place's names the headline is. */
  source: NameSource;
  /** The variety remark of the local form, where the headline is that form: no line below carries it then. */
  note?: string;
  /** The kind of place (`settlement`, `hallig`), where one is known. */
  kind?: string;
  lines: CardLine[];
}

/**
 * The local form as a source. It is named after the area's dialect only
 * where it IS that dialect's name: where the place has a form of its own
 * (Woiguurd, while Mooring says Waiguurd), calling both "Mooring" would
 * contradict itself.
 */
function localSource({ names, local, dialect }: CardNames): NameSource {
  const isAreaName = dialect !== undefined && names[dialect] === local;
  return isAreaName ? { kind: 'local', dialect } : { kind: 'local' };
}

/** The place's names in the dialects of the registry, in its order, but the headline's. */
function dialectLines(names: CardNames, shown: ShownName): CardLine[] {
  const isHeadline = (tag: string) => shown.source.kind === 'dialect' && shown.source.tag === tag;
  // The area's own dialect falls back to the `local` column in
  // frasch/placenames.py, so its name can be the very same string as the
  // local form. It is shown once, on the local line, which names the dialect.
  const isLocalForm = (tag: string) => tag === names.dialect && names.names[tag] === names.local;
  return DIALECTS.map(({ tag }) => ({ tag, name: names.names[tag] }))
    .filter(({ tag, name }) => name && !isHeadline(tag) && !isLocalForm(tag))
    .map(({ tag, name }) => ({ source: { kind: 'dialect', tag }, name }));
}

/**
 * The local form. Not where the headline already is that form, under the
 * same or another name: the selected dialect's name and the local one are
 * the same string wherever the place lies in that dialect's own area
 * (Niebüll in Mooring).
 */
function localLines(names: CardNames, headline: string): CardLine[] {
  const { local, variety } = names;
  if (!local || local === headline) return [];
  return [{ source: localSource(names), name: local, note: variety }];
}

/**
 * OSM's Frisian name of no dialect, for places our list does not have. Not
 * where it only repeats one of the names `shown` on the card already (it
 * usually is the same word as the dialect's): it says nothing worth a line.
 */
function frisianLines({ name_frr }: CardNames, shown: string[]): CardLine[] {
  if (!name_frr || shown.includes(name_frr)) return [];
  return [{ source: { kind: 'language', language: 'frr' }, name: name_frr }];
}

/**
 * German and Danish, and Low Saxon where it says something German does not:
 * most places are the same word in both (Husum).
 */
function languageLines({ name_nds, name_de, name_da }: CardNames, headline: string): CardLine[] {
  const names: [Language, string | undefined][] = [
    ['nds', name_nds === name_de ? undefined : name_nds],
    ['de', name_de],
    ['da', name_da],
  ];
  return names.flatMap(([language, name]) =>
    name && name !== headline ? [{ source: { kind: 'language', language }, name }] : [],
  );
}

function cardLines(names: CardNames, shown: ShownName): CardLine[] {
  const frisian = [...dialectLines(names, shown), ...localLines(names, shown.name)];
  const onCard = [shown.name, ...frisian.map((line) => line.name)];
  return [...frisian, ...frisianLines(names, onCard), ...languageLines(names, shown.name)];
}

/**
 * The card of a selection in a view: the headline is what the map labels the
 * place with there (`resolveName`), the lines are its other names.
 */
export function cardModel(selection: PlaceSelection, view: string): CardModel {
  const names = cardNames(selection);
  const shown = resolveName(names, view);
  return {
    headline: shown.name,
    source: shown.source.kind === 'local' ? localSource(names) : shown.source,
    note: names.local === shown.name ? names.variety : undefined,
    kind: names.kind || undefined,
    lines: cardLines(names, shown),
  };
}
