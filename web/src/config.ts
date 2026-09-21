// Central place for tile hosting and label/dialect configuration.
// The tiles URL is the ONLY place the frontend depends on how/where tiles are hosted.

import registry from './generated/dialects.json';

/**
 * URL of the PMTiles archive (or any MapLibre-compatible vector source URL).
 *
 * Defaults to a PMTiles file served from this site's own /tiles/ directory
 * (see web/public/tiles/), resolved relative to the site origin. Override via
 * the VITE_TILES_URL environment variable, e.g. to point at a CDN-hosted
 * PMTiles archive.
 */
export const TILES_URL: string =
  import.meta.env.VITE_TILES_URL || 'pmtiles:///tiles/schleswig-holstein.pmtiles';

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
  /** "living" | "extinct" — Südergoesharde names are historic. */
  status: string;
  /** "yes" = offered as its own map view in the selector. */
  view: string;
}

/**
 * The dialect registry, in registry order. Generated from names/dialects.csv
 * by names/export_search_index.py — do not edit generated/dialects.json by hand.
 */
export const DIALECTS: DialectEntry[] = registry;

/**
 * Pseudo-tag of the "local dialect" view: every place labelled the way the
 * people of that place speak (tile attribute `frasch:local`), so a single map
 * can mix Mooring, Fering, Sölring, … It is NOT a BCP 47 tag of a real
 * dialect and has no `name:<tag>` tile property of its own.
 */
export const LOCAL_TAG = 'frr-x-local';

/**
 * UI language used while the local view is selected. The local view has no
 * single dialect of its own, so the chrome has to pick one; the owner chose
 * Mooring. One place to change if that ever becomes e.g. a "mixed" UI.
 */
export const LOCAL_VIEW_UI_LANGUAGE = 'frr-x-mooring';

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

/** Label option selected on first load. */
export const DEFAULT_LABELS = 'frr-x-mooring';

/** An entry of the (single) label selector: a dialect view or the local view. */
export interface LabelOption {
  /** Dialect tag, or LOCAL_TAG for the local view. Drives the label expression. */
  tag: string;
  /** i18n key of the option's name. */
  labelKey: string;
  /** Fallback name where the key has no translation (the registry label of a dialect). */
  label?: string;
  /** UI language to switch to when this option is picked. */
  uiLanguage: string;
}

/**
 * Options of the one dropdown: the dialects the registry marks `view=yes`
 * (today only Mooring — the others have too little name coverage to be worth
 * a whole map view), then the local view.
 */
export const LABEL_OPTIONS: LabelOption[] = [
  ...DIALECTS.filter((d) => d.view === 'yes').map((d) => ({
    tag: d.tag,
    labelKey: dialectLabelKey(d.tag),
    label: d.label,
    // A dialect view speaks its own dialect.
    uiLanguage: d.tag,
  })),
  { tag: LOCAL_TAG, labelKey: 'dialect.local', uiLanguage: LOCAL_VIEW_UI_LANGUAGE },
];

/**
 * The option for `tag`, falling back to the default option (and, should the
 * default ever be misconfigured, to the first one) so that a stale tag — e.g.
 * from an old URL or a dialect that lost `view=yes` — can never leave the app
 * without a UI language.
 */
export function labelOption(tag: string): LabelOption {
  return (
    LABEL_OPTIONS.find((o) => o.tag === tag) ??
    LABEL_OPTIONS.find((o) => o.tag === DEFAULT_LABELS) ??
    LABEL_OPTIONS[0]
  );
}
