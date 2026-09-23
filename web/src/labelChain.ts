import { DIALECTS, LOCAL_TAG } from './config';

// Which name a place is labelled with, defined once for everything that shows
// one: the map (style/localize.ts turns the chain into a `coalesce` over the
// tile properties) and the place card and search results (names.ts walks the
// same chain over a name-list entry). Two chains kept in sync by hand drifted
// apart before — the card said Flensburg where the map said Flensborg — so
// neither side may hardcode its own.

/**
 * The tile properties a label is taken from, first non-empty wins.
 *
 * `tag` is either a dialect tag such as "frr-x-mooring" (the corresponding
 * tile property is literally "name:frr-x-mooring") or LOCAL_TAG, the "local
 * dialect" view.
 *
 *  - dialect view: the dialect's own name first, then the local Frisian name
 *    of the place (`frasch:local`, e.g. a Fering name on Föhr while the map
 *    is in Mooring) so a Frisian name is preferred over a German one even
 *    where this dialect has none, then every other dialect's name in
 *    registry order (a place outside the dialect areas has no local name,
 *    but may still have a Wieding one), then generic Frisian, Low Saxon, German,
 *    a transliterated Latin name, and finally the generic OSM `name`.
 *  - local view: ONLY the name the people of the place use themselves, then
 *    the local majority language. Deliberately no `name:frr` (that is some
 *    other dialect's name, which is exactly what this view avoids) and no
 *    `name:de` — German comes in via `name:latin`/`name` anyway, but only
 *    after Low Saxon has had its turn.
 *
 * Phase 1 covers Schleswig-Holstein only, so `name:nds` (Low Saxon) is always
 * the local majority language outside the Frisian areas. That assumption
 * breaks as soon as the tiles leave northern Germany; the per-country
 * language zones of issue #15 are to replace the fixed Low Saxon/German steps
 * here, for the map and the card alike.
 */
export function labelChain(tag: string): string[] {
  if (tag === LOCAL_TAG) {
    return ['frasch:local', 'name:nds', 'name:latin', 'name'];
  }
  return [
    `name:${tag}`,
    'frasch:local',
    ...DIALECTS.filter((d) => d.tag !== tag).map((d) => `name:${d.tag}`),
    'name:frr',
    'name:nds',
    'name:de',
    'name:latin',
    'name',
  ];
}
