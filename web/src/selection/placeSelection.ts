// The selected place: how it was picked, what the card shows for it, and what
// the map does about it. usePlaceSelection.ts holds the state.

import type { LngLat, LngLatLike, MapGeoJSONFeature } from 'maplibre-gl';

import type { MapMarker } from '../map/MapView';
import type { NameEntry } from '../names/entry';
import type { EntryLookup } from '../names/load';
import { displayName } from '../names/resolveName';
import type { TileProps } from '../names/tile';

/** A click on a place label of the map. */
export interface MapPick {
  via: 'map';
  /**
   * `frasch:ref`, the id of the feature's row in the name list
   * (frasch/inject_names.py writes it, frasch/searchindex.py uses it as the
   * entry id; tiles built before the row ids carry the row's OSM reference,
   * which the list's lookup knows too). A feature without one, or one the
   * list does not have, still gets a card, from the tile's own attributes.
   */
  ref?: string;
  /** The tile properties of the clicked feature. */
  props: TileProps;
  /** Its tile feature id, see names/links.ts `osmRefFromFeatureId`. */
  featureId?: string | number;
  /** Where the click was. */
  at: LngLat;
}

/** A search result. */
export interface SearchPick {
  via: 'search';
  ref: string;
}

/** The place a shared link names (`?place=`, see url/linkState.ts). */
export interface LinkPick {
  via: 'link';
  ref: string;
  /** The link says where to look: mark the place there, do not fly to it. */
  keepViewport: boolean;
}

/** What was picked, and by which way. `ref` names its row of the name list. */
export type PlacePick = MapPick | SearchPick | LinkPick;

/** How a card was closed: Escape, Enter or Space; or a click or tap. */
export type CloseMeans = 'keyboard' | 'pointer';

/**
 * A pick together with its entry of the name list: what the card shows. A
 * clicked label has a card of its own (the tile's attributes) and may have no
 * entry, or none yet; a search result and a linked place are their entry.
 */
export type PlaceSelection = ClickedLabel | ListedPlace;
type ClickedLabel = { pick: MapPick; entry?: NameEntry };
type ListedPlace = { pick: SearchPick | LinkPick; entry: NameEntry };

function isClickedLabel(selection: PlaceSelection): selection is ClickedLabel {
  return selection.pick.via === 'map';
}

export function mapPick(feature: MapGeoJSONFeature, at: LngLat): MapPick {
  const props = feature.properties as TileProps;
  const ref = props['frasch:ref'];
  return {
    via: 'map',
    ref: typeof ref === 'string' ? ref : undefined,
    props,
    featureId: feature.id,
    at,
  };
}

/**
 * The selection of `pick`, or none while there is nothing to show for it: a
 * linked place before the name list has loaded, or one the list does not
 * have. The entry is looked up on every call, so a card opened before the
 * list has loaded gets it once the list is there.
 */
export function selectionOf(pick: PlacePick, find: EntryLookup): PlaceSelection | null {
  const entry = pick.ref === undefined ? undefined : find(pick.ref);
  if (pick.via === 'map') return { pick, entry };
  return entry ? { pick, entry } : null;
}

/**
 * The marker of a selection: a search result and a linked place get one,
 * named as their label is in `view`. A clicked label says itself where the
 * place is; a marker would only sit beside it.
 */
export function markerOf(selection: PlaceSelection | null, view: string): MapMarker | null {
  if (!selection || isClickedLabel(selection)) return null;
  const { entry } = selection;
  return { at: [entry.lon, entry.lat], title: displayName(entry, view) };
}

/** Target zoom per feature kind: large areas get a wider view than villages. */
const ZOOM_BY_KIND: Record<string, number> = {
  landscape: 10,
  island: 11,
  koog: 12,
  water: 12,
  sand: 12,
  hallig: 13,
  helgoland: 13,
  settlement: 14,
  warft: 15,
};
const DEFAULT_TARGET_ZOOM = 14;

/**
 * Where the map goes for a selection. With a `zoom` it flies there; without
 * one it stays, and only brings `to` out from under the card.
 */
export interface MapMove {
  to: LngLatLike;
  zoom?: number;
}

/**
 * A search result is flown to, and so is a linked place, unless its link
 * says where to look. A clicked label is on screen already; so is a link's
 * viewport, though the place in it may lie under a phone's sheet the sharer
 * on a desktop never had in the way.
 */
export function mapMove(selection: PlaceSelection): MapMove {
  if (isClickedLabel(selection)) return { to: selection.pick.at };
  const { pick, entry } = selection;
  const to: [number, number] = [entry.lon, entry.lat];
  if (pick.via === 'link' && pick.keepViewport) return { to };
  return { to, zoom: ZOOM_BY_KIND[entry.kind] ?? DEFAULT_TARGET_ZOOM };
}
