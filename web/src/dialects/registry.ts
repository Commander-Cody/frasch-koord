// The dialect registry as the frontend compiles it in. No `import.meta.env`
// here: vite-plugins/glyphs.ts imports this module (through views.ts and
// labelChain.ts) into the Vite config, where there is none.

import registry from './generated/dialects.json' with { type: 'json' };

/** One dialect of the registry (names/dialects.csv, exported to generated/dialects.json). */
export interface DialectEntry {
  /** BCP 47 language tag, e.g. "frr-x-mooring". Tile property: "name:<tag>". */
  tag: string;
  /** Column of that dialect in names/places.csv. Not used by the frontend, kept for traceability. */
  column: string;
  /**
   * Human-readable label, e.g. "Mooring". Only the last-resort fallback for
   * display: the UI shows `dialects.<tag>` from the locale files (see
   * dialectLabelKey), so the name follows the UI language.
   */
  label: string;
  /** Südergoesharde names are historic. */
  status: 'living' | 'extinct';
  /** "yes" = offered as a view of its own in the selector (see views.ts). */
  view: 'yes' | 'no';
}

/**
 * The dialect registry, in registry order. Generated from names/dialects.csv
 * by `frasch build dialects` (`just rebuild dialects`) — do not edit generated/dialects.json by hand.
 * Cast because a JSON import widens every value to `string`;
 * frasch/dialects.py checks `status` and `view` before it exports them.
 */
export const DIALECTS = registry as DialectEntry[];

/**
 * The registry entry of a dialect tag, or undefined for a tag the registry
 * does not have (LOCAL_TAG, a stale URL, an older archive's `name:<tag>`).
 */
export function dialect(tag: string): DialectEntry | undefined {
  return DIALECTS.find((d) => d.tag === tag);
}

/**
 * i18n key of a dialect's display name. Callers pass the registry label as
 * `defaultValue`, so a dialect newly added to the registry still shows a name
 * before the locale files catch up.
 */
export function dialectLabelKey(tag: string): string {
  return `dialects.${tag}`;
}
