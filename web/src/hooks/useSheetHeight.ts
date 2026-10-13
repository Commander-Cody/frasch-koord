import { useEffect } from 'react';
import type { RefObject } from 'react';

import { PHONE_MEDIA } from '../layout';

// The one place the place card is measured. On a phone it is a bottom sheet
// over the map, and both the stylesheet and a map move have to know how much
// of the map it covers.

/**
 * How many pixels at the bottom of the map `card` covers right now: its
 * height where it is the phone's bottom sheet, nothing where it sits beside
 * the map.
 */
export function sheetInset(card: HTMLElement | null): number {
  return card && window.matchMedia(PHONE_MEDIA).matches ? card.offsetHeight : 0;
}

/**
 * The place card's height as `--sheet-height` on the app element, for App.css
 * to lift the attribution above the bottom sheet on a phone. Tracked while the
 * card is open: its content changes with the place and the view.
 */
export function useSheetHeight(
  appRef: RefObject<HTMLElement | null>,
  cardRef: RefObject<HTMLElement | null>,
  cardOpen: boolean,
): void {
  useEffect(() => {
    const app = appRef.current;
    const card = cardRef.current;
    if (!app || !card) return;
    const observer = new ResizeObserver(() => {
      app.style.setProperty('--sheet-height', `${card.offsetHeight}px`);
    });
    observer.observe(card);
    return () => {
      observer.disconnect();
      app.style.removeProperty('--sheet-height');
    };
  }, [appRef, cardRef, cardOpen]);
}
