// A click on a map label in the curation view: one of an OSM object the
// name list does not have (no `frasch:ref`) can start a new place (#113).

import { useEffect, useRef } from 'react';
import type { Map as MapLibreMap, MapGeoJSONFeature, MapMouseEvent } from 'maplibre-gl';

import { placeHitTest } from '../../map/hitTest';
import { PLACE_LAYERS } from '../../map/style';
import { osmRefFromFeatureId } from '../../names/links';
import type { TileProps } from '../../names/tile';

/** A clicked label of an object the name list does not have. */
export interface ClickedLabel {
  /** Its OSM object, from the tile feature id; undefined when that does not decode. */
  ref?: string;
  /** OSM's name of it, for the panel to say which label it was. */
  name: string;
  /** The names a new place from it starts with. */
  de: string;
  da: string;
}

function text(props: TileProps, key: string): string {
  const value = props[key];
  return typeof value === 'string' ? value : '';
}

/**
 * What a click on `feature` offers, or none for a label of a row of the
 * name list. Its German and Danish names are its `name:de` and `name:da`;
 * an object with neither starts with OSM's plain `name` as the German one,
 * which is right south of the border.
 */
export function clickedLabel(feature: MapGeoJSONFeature): ClickedLabel | null {
  const props = (feature.properties ?? {}) as TileProps;
  if (text(props, 'frasch:ref')) return null;
  const name = text(props, 'name');
  const [de, da] = [text(props, 'name:de'), text(props, 'name:da')];
  return {
    ref: osmRefFromFeatureId(feature.id) ?? undefined,
    name: name || de || da,
    de: de || (da ? '' : name),
    da,
  };
}

/**
 * Hands every click on a place label to `onLabel`. Registered once; reads
 * the current `onLabel` through a ref, as MapView's own place clicks do.
 */
export function useLabelClicks(
  map: MapLibreMap,
  onLabel: (feature: MapGeoJSONFeature) => void,
): void {
  const onLabelRef = useRef(onLabel);
  useEffect(() => {
    onLabelRef.current = onLabel;
  }, [onLabel]);
  useEffect(() => {
    const hit = placeHitTest(map, PLACE_LAYERS);
    const onClick = (event: MapMouseEvent) => {
      const feature = hit(event.point);
      if (feature) onLabelRef.current(feature);
    };
    map.on('click', onClick);
    return () => {
      map.off('click', onClick);
    };
  }, [map]);
}
