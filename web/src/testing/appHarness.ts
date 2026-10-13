// What a test of the whole App needs around it: a name list it can hold
// back, and the browser APIs jsdom has not.

import { act } from '@testing-library/react';
import { vi } from 'vitest';

import type { NameEntry } from '../names';

/** Serves names.json once the test calls the returned function. */
export function holdNames(entries: NameEntry[]): () => Promise<void> {
  let serve!: () => void;
  const served = new Promise<void>((resolve) => (serve = resolve));
  vi.stubGlobal('fetch', async () => {
    await served;
    return new Response(JSON.stringify({ built_from: {}, places: entries }), { status: 200 });
  });
  return async () => {
    await act(async () => serve());
  };
}

/**
 * Stands in for the layout APIs App asks: a desktop, where no sheet covers
 * the map, unless `phone`; and a ResizeObserver that never reports. To be
 * undone with `vi.unstubAllGlobals()`.
 */
export function stubLayout({ phone = false } = {}): void {
  vi.stubGlobal('matchMedia', () => ({ matches: phone }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  );
}
