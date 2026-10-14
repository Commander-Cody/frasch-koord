// A place as the frontend sees it: an entry of public/data/names.json, and
// the names a card shows, of an entry or of a tile feature.

/**
 * One entry of public/data/names.json, written by frasch/searchindex.py.
 * Only non-empty values are exported, so every optional field is genuinely
 * absent rather than an empty string. The contract itself is
 * names/search-index.schema.json; entry.test.ts pins NameEntry to it.
 */
export interface NameEntry {
  /** The name-list row's `id`, e.g. "naibel" — stable across edits to the list and OSM alike; the tiles carry it as `frasch:ref`. */
  id: string;
  /** The row's OSM references, e.g. "node/240042766" or "way/1; node/2", or "local/<slug>" for a place OSM does not have. */
  osm?: string;
  /** Dialect names by registry tag, e.g. { "frr-x-mooring": "Naibel" }. */
  names: Record<string, string>;
  /**
   * Name used by the people of the place itself (tile attribute
   * `frasch:local`): the name list's, else OSM's `name:frr` where the place
   * lies in a dialect area (issue #81).
   */
  local?: string;
  /** Dialect area the place lies in, e.g. "frr-x-fering". */
  dialect?: string;
  /** Sub-dialect remark of the local name, e.g. "Foortuftinge". */
  variety?: string;
  /**
   * Low Saxon name — OSM's `name:nds`, never our name list (it has no Low
   * Saxon column). frasch/searchindex.py takes it from the object's
   * entry in names/osm_objects.json, a tile feature carries it itself. The label chain falls back to it
   * before German, so the card needs it for the same reason as `name_frr`.
   */
  name_nds?: string;
  /**
   * German name — the list's `de`, shown as a hint next to a Frisian one. The
   * tiles carry the same as `name:de` on the place's objects (issue #61).
   */
  name_de: string;
  /**
   * The place's generic name — OSM's plain `name`, the chain's generic
   * steps near its end (`name:latin`, `name`) and therefore what the local
   * view labels a place with that has neither a local nor a Low Saxon name. In this region
   * that is usually the German name, but north of the border it is the Danish
   * one (Ribe, where German says Ripen). frasch/searchindex.py takes it
   * from names/osm_objects.json, a tile feature carries it itself.
   */
  name_osm?: string;
  /** Danish name, where the list has one. */
  name_da?: string;
  /** Wikidata QID of the place, where the row has one. */
  wikidata?: string;
  lon: number;
  lat: number;
  kind: string;
}

/** The fields of an entry that name or describe the place, rather than identify or locate it. */
type NameField =
  | 'local'
  | 'dialect'
  | 'variety'
  | 'name_nds'
  | 'name_de'
  | 'name_osm'
  | 'name_da'
  | 'kind';

/**
 * The names of a place as its card shows them: those of its entry, any of
 * which a tile feature may carry too, and what only a tile feature knows.
 * Neither id nor coordinates: a feature the name list does not have has none.
 */
export interface CardNames extends Partial<Pick<NameEntry, NameField>> {
  names: NameEntry['names'];
  /**
   * Frisian name of no particular dialect — OSM's own `name:frr`, never our
   * name list, which always knows which dialect a name is in. The style
   * labels with it too (see dialects/labelChain.ts), so the card has to know about it
   * or it would contradict the label the user just clicked.
   */
  name_frr?: string;
}
