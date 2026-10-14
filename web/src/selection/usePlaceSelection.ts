import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';

import type { MapMoves } from '../map/MapView';
import type { NamesData } from '../names/load';
import { mapMove, selectionOf } from './placeSelection';
import type { CloseMeans, PlacePick, PlaceSelection } from './placeSelection';
import { linkedPlace, writePlace } from '../url/linkState';
import { sheetInset } from './useSheetHeight';

/** What a selection reaches for: the map it moves, and where keyboard focus goes. */
export interface SelectionTargets {
  map: RefObject<MapMoves | null>;
  card: RefObject<HTMLElement | null>;
  /** The card's headline. */
  heading: RefObject<HTMLElement | null>;
  searchField: RefObject<HTMLElement | null>;
}

export interface PlaceSelectionState {
  /** The place whose card is open, from a map click, a search result or a link. */
  selection: PlaceSelection | null;
  select: (pick: PlacePick) => void;
  /**
   * Closes the card, if one is open: a linked place whose list still loads
   * has none, and stays to be opened. From the keyboard, with focus in the
   * card, focus goes back to the search field rather than dropping to the
   * page. A pointer close leaves focus alone: on a phone, focus in the field
   * is a keyboard popping up.
   */
  close: (means: CloseMeans) => void;
}

/**
 * Moves the map for a selection and, for a search pick, focus to its card's
 * headline, which also has screen readers announce it: the pick leaves the
 * field it was made in. Once per pick, when its card is laid out and before
 * paint, so the map starts moving in the frame the card shows: on a phone the
 * card is a bottom sheet, and where the place should land depends on its
 * height.
 */
function useShowPick(
  selection: PlaceSelection | null,
  { map, card, heading }: SelectionTargets,
): void {
  // The selection of a pick changes again when the name list arrives after
  // a click, which is no reason to move the map twice.
  const shown = useRef<PlacePick | null>(null);
  useLayoutEffect(() => {
    if (!selection || shown.current === selection.pick) return;
    shown.current = selection.pick;
    const { to, zoom } = mapMove(selection);
    const inset = sheetInset(card.current);
    if (zoom === undefined) map.current?.reveal(to, inset);
    else map.current?.flyTo(to, zoom, inset);
    if (selection.pick.via === 'search') heading.current?.focus();
  }, [selection, map, card, heading]);
}

/** The pick the page opens with, when its link names a place. */
function linkPick(): PlacePick | null {
  const linked = linkedPlace();
  return linked ? { via: 'link', ...linked } : null;
}

/**
 * Which place's card is open. Starts with the place the page's link names;
 * its card opens once the name list has it, unless another was picked by
 * then. Keeps the link's `?place=` the open card's place: the entry's id, or,
 * while the list is not there to look it up in, what was picked.
 */
export function usePlaceSelection(
  { status, find }: NamesData,
  targets: SelectionTargets,
): PlaceSelectionState {
  const [pick, select] = useState<PlacePick | null>(linkPick);
  const selection = useMemo(() => pick && selectionOf(pick, find), [pick, find]);
  useShowPick(selection, targets);

  const place = selection?.entry?.id ?? (status === 'ready' ? undefined : pick?.ref);
  useEffect(() => writePlace(place), [place]);

  const { card, searchField } = targets;
  const cardOpen = selection !== null;
  const close = useCallback(
    (means: CloseMeans) => {
      if (!cardOpen) return;
      const focusInCard = card.current?.contains(document.activeElement) ?? false;
      select(null);
      if (means === 'keyboard' && focusInCard) searchField.current?.focus();
    },
    [cardOpen, card, searchField],
  );

  return { selection, select, close };
}
