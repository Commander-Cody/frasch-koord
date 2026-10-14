// The views of the map: what the selector offers and the map is labelled in.
// A view is a dialect of the registry, or the local view.

import { DIALECTS, dialectLabelKey } from './registry.ts';

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

/** View selected on first load. */
export const DEFAULT_VIEW = 'frr-x-mooring';

/** An entry of the selector: a dialect view or the local view. */
export interface ViewOption {
  /** Dialect tag, or LOCAL_TAG for the local view. Drives the label expression. */
  tag: string;
  /** i18n key of the view's name. */
  labelKey: string;
  /** Fallback name where the key has no translation (the registry label of a dialect). */
  label?: string;
  /** UI language to switch to when this view is picked. */
  uiLanguage: string;
}

/**
 * The views the selector offers: the dialects the registry marks `view=yes`
 * (today only Mooring — the others have too little name coverage to be worth
 * a whole map view), then the local view.
 */
export const VIEWS: ViewOption[] = [
  ...DIALECTS.filter((d) => d.view === 'yes').map((d) => ({
    tag: d.tag,
    labelKey: dialectLabelKey(d.tag),
    label: d.label,
    // A dialect view speaks its own dialect.
    uiLanguage: d.tag,
  })),
  { tag: LOCAL_TAG, labelKey: 'view.local', uiLanguage: LOCAL_VIEW_UI_LANGUAGE },
];

/**
 * Every tag the map can be labelled in, offered by the selector or not: each
 * dialect of the registry, then the local view. What has to hold in any view
 * (the glyphs a label needs, the map and the card agreeing) is checked over
 * these.
 */
export const ALL_VIEW_TAGS: string[] = [...DIALECTS.map((d) => d.tag), LOCAL_TAG];

/**
 * The view of `tag`, falling back to the default view (and, should the
 * default ever be misconfigured, to the first one) so that a stale tag — e.g.
 * from an old URL or a dialect that lost `view=yes` — can never leave the app
 * without a UI language.
 */
export function viewOption(tag: string): ViewOption {
  return VIEWS.find((o) => o.tag === tag) ?? VIEWS.find((o) => o.tag === DEFAULT_VIEW) ?? VIEWS[0];
}
