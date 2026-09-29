// Where a dev panel sits over the map, for DevPanel.css and for the map moves
// that have to keep clear of it.

/** Width of a dev panel in px; DevPanel hands it to DevPanel.css as `--dev-panel-width`. */
export const PANEL_WIDTH = 420;

/** Padding that keeps what the map is fitted to clear of the panel on the left. */
export const FIT_PADDING = { left: PANEL_WIDTH + 40, top: 60, right: 60, bottom: 60 };
