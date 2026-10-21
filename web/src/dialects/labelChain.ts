import { DIALECTS, frisianTags, type DialectEntry } from './registry.ts';
import { LOCAL_TAG } from './views.ts';

// Which name a place is labelled with, defined once for everything that shows
// one: the map (map/style/labels.ts turns the chain into a `coalesce` over the
// tile properties) and the place card and search results (names/resolveName.ts
// walks the same chain over a place's names). Two chains kept in sync by hand drifted
// apart before — the card said Flensburg where the map said Flensborg — so
// neither side may hardcode its own.

/**
 * The tile properties a label is taken from, first non-empty wins, for a
 * place that does (`inFrisianArea`) or does not lie in the area of a Frisian
 * dialect (`frasch:dialect`; no area at all counts as not).
 *
 * `tag` is either a Frisian dialect tag such as "frr-x-mooring" (the
 * corresponding tile property is literally "name:frr-x-mooring") or
 * LOCAL_TAG, the "local dialect" view.
 *
 *  - dialect view: the dialect's own name first, then the local name of the
 *    place (`frasch:local`) where it lies in a Frisian dialect area (a Fering
 *    name on Föhr while the map is in Mooring) so a Frisian name is preferred
 *    over a German one even where this dialect has none, then every other
 *    Frisian dialect's name in registry order (a place outside the dialect
 *    areas has no local name, but may still have a Wieding one), then
 *    generic Frisian. Only then the local name of a place elsewhere — a
 *    Synnejysk name in a Synnejysk area, a Low Saxon one in a Low Saxon area
 *    or in none —, so a Frisian view never shows a Synnejysk or Low Saxon
 *    name where it knows a Frisian one, and never a Synnejysk exonym of a
 *    place outside the Synnejysk areas. Then Low Saxon, German, a
 *    transliterated Latin name, and finally the generic OSM `name`.
 *  - local view: ONLY the name the people of the place use themselves, then
 *    the local majority language. Deliberately no `name:frr` (outside the
 *    dialect areas that is a Frisian exonym or some other dialect's name,
 *    which is exactly what this view avoids; inside a Frisian area the tile
 *    build has already written it into `frasch:local` where the name list
 *    gives no local name, issue #81), and
 *    `name:de` only as the very last resort, for a feature without a generic
 *    `name` (issue #32): German comes in via `name:latin`/`name` anyway, but
 *    only after Low Saxon has had its turn.
 *
 * Phase 1 covers Schleswig-Holstein only, so `name:nds` (Low Saxon) is always
 * the local majority language outside the Frisian areas. That assumption
 * breaks as soon as the tiles leave northern Germany; the per-country
 * language zones of issue #15 are to replace the fixed Low Saxon/German steps
 * here, for the map and the card alike.
 *
 * `dialects` is the registry whose Frisian dialects the chain names, the real
 * one unless a test hands in its own.
 */
export function labelChain(
  tag: string,
  inFrisianArea: boolean,
  dialects: readonly Pick<DialectEntry, 'tag' | 'language'>[] = DIALECTS,
): string[] {
  if (tag === LOCAL_TAG) {
    return ['frasch:local', 'name:nds', 'name:latin', 'name', 'name:de'];
  }
  const frisian = frisianTags(dialects);
  return [
    `name:${tag}`,
    ...(inFrisianArea ? ['frasch:local'] : []),
    ...frisian.filter((other) => other !== tag).map((other) => `name:${other}`),
    'name:frr',
    ...(inFrisianArea ? [] : ['frasch:local']),
    'name:nds',
    'name:de',
    'name:latin',
    'name',
  ];
}
