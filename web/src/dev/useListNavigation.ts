import { useEffect } from 'react';

const NEXT_KEYS = new Set(['ArrowDown', 'j']);
const PREVIOUS_KEYS = new Set(['ArrowUp', 'k']);

/** Whether a key press goes into a form field rather than to the page. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable;
}

/**
 * ↓/↑ and `j`/`k` walk a dev panel's list: `select` gets the item after or
 * before `selected`, the first one when nothing is selected yet, and never
 * one past either end. Global so the keys work wherever the eye is, but
 * never while typing.
 */
export function useListNavigation<T>(items: readonly T[], selected: T | null, select: (item: T) => void): void {
  useEffect(() => {
    const move = (delta: number) => {
      if (items.length === 0) return;
      const at = selected === null ? -1 : items.indexOf(selected);
      const next = at < 0 ? 0 : Math.min(items.length - 1, Math.max(0, at + delta));
      select(items[next]);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTyping(event.target)) return;
      const delta = NEXT_KEYS.has(event.key) ? 1 : PREVIOUS_KEYS.has(event.key) ? -1 : 0;
      if (delta === 0) return;
      event.preventDefault();
      move(delta);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [items, selected, select]);
}
