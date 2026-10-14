// The links at the foot of a place's card: to its OSM object and its Wikidata item.

import indexSchema from '../../../names/search-index.schema.json';
import { osmRefs } from './osmRef';
import type { NameEntry } from './entry';

/**
 * A Wikidata item id (`Q42`), as the contract of names.json spells it; the
 * patch contract (names/curate-patch.schema.json) and frasch/placelist.py
 * take the same shape.
 */
export const WIKIDATA_ID = new RegExp(indexSchema.$defs.place.properties.wikidata.pattern);

export function wikidataUrl(qid: string | undefined): string | null {
  return qid && WIKIDATA_ID.test(qid) ? `https://www.wikidata.org/wiki/${qid}` : null;
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

/**
 * The OSM reference of what the card is showing, for the link at its foot:
 * the first of the row's, else the clicked feature's object (`featureId` is
 * its tile feature id).
 */
export function placeOsmRef(
  entry: NameEntry | undefined,
  featureId?: string | number,
): string | null {
  return osmRefs(entry?.osm)[0] ?? osmRefFromFeatureId(featureId);
}
