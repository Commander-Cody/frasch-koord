import type { Map as MapLibreMap, MapGeoJSONFeature, Point } from 'maplibre-gl';

import { TOUCH_MEDIA } from '../layout';

/** Half-width in pixels of the box a click queries: a mouse pointer is not a pixel. */
const CLICK_SLOP = 6;
/** The same for a finger, which is wider still (a 24 px box). */
const TOUCH_CLICK_SLOP = 12;

function clickSlop(): number {
  return window.matchMedia(TOUCH_MEDIA).matches ? TOUCH_CLICK_SLOP : CLICK_SLOP;
}

/** What a hit test asks of the map. */
export type HitTestMap = Pick<MapLibreMap, 'getLayer' | 'queryRenderedFeatures'>;

/**
 * Which place label a pointer at `point` is on: the topmost feature of
 * `layers` in a small box around it, or none. `layers` are read off the style
 * once (every view has the same label layers, only their text-field differs);
 * the ones a style in flight has not added yet are skipped.
 */
export function placeHitTest(
  map: HitTestMap,
  layers: string[],
): (point: Point) => MapGeoJSONFeature | undefined {
  return (point) => {
    const slop = clickSlop();
    return map.queryRenderedFeatures(
      [
        [point.x - slop, point.y - slop],
        [point.x + slop, point.y + slop],
      ],
      { layers: layers.filter((id) => map.getLayer(id)) },
    )[0];
  };
}
