import { useEffect } from 'react';
import type { RefObject } from 'react';

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
