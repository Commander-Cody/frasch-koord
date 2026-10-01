import { useCallback, useEffect, useRef } from 'react';
import type { RefObject } from 'react';

import type { PlaceSelection } from '../names';

/** What useCardFocus needs to reach: the card's heading, and the search field it hands focus back to. */
export interface CardFocusTargets {
  card: RefObject<HTMLElement | null>;
  heading: RefObject<HTMLElement | null>;
  searchField: RefObject<HTMLElement | null>;
}

/**
 * Keyboard focus around the place card. `focusNextCard` asks for the heading
 * of the card the next selection opens to take focus, which also has screen
 * readers announce it: a search pick leaves the field it was made in.
 * `closeByKeyboard` closes the card and, when focus was in it, hands focus
 * back to the search field rather than dropping it to the page. A pointer
 * close leaves focus alone: on a phone, focus in the field is a keyboard
 * popping up.
 */
export function useCardFocus(
  { card, heading, searchField }: CardFocusTargets,
  selection: PlaceSelection | null,
  close: () => void,
) {
  const pending = useRef(false);
  useEffect(() => {
    if (!pending.current) return;
    pending.current = false;
    heading.current?.focus();
  }, [heading, selection]);

  const focusNextCard = useCallback(() => {
    pending.current = true;
  }, []);

  const closeByKeyboard = useCallback(() => {
    const focusInCard = card.current?.contains(document.activeElement) ?? false;
    close();
    if (focusInCard) searchField.current?.focus();
  }, [card, searchField, close]);

  return { focusNextCard, closeByKeyboard };
}
