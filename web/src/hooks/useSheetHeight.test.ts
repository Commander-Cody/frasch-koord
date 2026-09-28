import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useSheetHeight } from './useSheetHeight';

/** jsdom lays nothing out: a card of a given height, and a way to change it. */
function cardOf(height: number) {
  const card = document.createElement('section');
  const setHeight = (px: number) => Object.defineProperty(card, 'offsetHeight', { value: px, configurable: true });
  setHeight(height);
  return { card, setHeight };
}

/** jsdom has no ResizeObserver; this one reports on demand. */
class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  readonly callback: () => void;
  constructor(callback: () => void) {
    this.callback = callback;
    FakeResizeObserver.instances.push(this);
  }
  observe() {
    this.callback();
  }
  disconnect() {}
  static resizeAll() {
    for (const observer of FakeResizeObserver.instances) observer.callback();
  }
}

beforeEach(() => {
  FakeResizeObserver.instances = [];
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useSheetHeight', () => {
  it("sets the open card's height on the app, for App.css", () => {
    const app = document.createElement('div');
    const { card } = cardOf(240);
    renderHook(() => useSheetHeight({ current: app }, { current: card }, true));
    expect(app.style.getPropertyValue('--sheet-height')).toBe('240px');
  });

  it('follows the card as its content changes', () => {
    const app = document.createElement('div');
    const { card, setHeight } = cardOf(240);
    renderHook(() => useSheetHeight({ current: app }, { current: card }, true));
    setHeight(310);
    FakeResizeObserver.resizeAll();
    expect(app.style.getPropertyValue('--sheet-height')).toBe('310px');
  });

  it('clears the height when the card closes', () => {
    const app = document.createElement('div');
    const { card } = cardOf(240);
    const cardRef: { current: HTMLElement | null } = { current: card };
    const { rerender } = renderHook((open: boolean) => useSheetHeight({ current: app }, cardRef, open), {
      initialProps: true,
    });
    cardRef.current = null;
    rerender(false);
    expect(app.style.getPropertyValue('--sheet-height')).toBe('');
  });
});
