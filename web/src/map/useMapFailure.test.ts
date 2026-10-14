import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { useMapFailure } from './useMapFailure';
import type { FailureMap } from './useMapFailure';

/** A map that raises the events a test fires. */
function fakeMap() {
  const listeners = new Map<string, Set<(event: unknown) => void>>();
  const map = {
    on: (type: string, listener: (event: unknown) => void) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(listener);
      return { unsubscribe: () => listeners.get(type)!.delete(listener) };
    },
  } as unknown as FailureMap;
  const fire = (type: string, event: unknown = {}) =>
    act(() => listeners.get(type)?.forEach((listener) => listener(event)));
  return { map, fire };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('reports an error the map raises', () => {
  const { map, fire } = fakeMap();
  const { result } = renderHook(() => useMapFailure(map));

  fire('error', { error: new Error('tile 404') });

  expect(result.current.failure).toBe('error');
});

it('reports a map that has not loaded after 30 seconds', () => {
  const { map } = fakeMap();
  const { result } = renderHook(() => useMapFailure(map));

  act(() => vi.advanceTimersByTime(30_000));

  expect(result.current.failure).toBe('timeout');
});

it('takes the timeout back when the map loads after all', () => {
  const { map, fire } = fakeMap();
  const { result } = renderHook(() => useMapFailure(map));
  act(() => vi.advanceTimersByTime(30_000));

  fire('load');

  expect(result.current.failure).toBeNull();
});

it('keeps an error when the map loads after it', () => {
  const { map, fire } = fakeMap();
  const { result } = renderHook(() => useMapFailure(map));
  fire('error', { error: new Error('glyphs 404') });

  fire('load');

  expect(result.current.failure).toBe('error');
});

it('reports nothing once dismissed', () => {
  const { map, fire } = fakeMap();
  const { result } = renderHook(() => useMapFailure(map));
  fire('error', { error: new Error('tile 404') });

  act(() => result.current.dismiss());

  expect(result.current.failure).toBeNull();
});
