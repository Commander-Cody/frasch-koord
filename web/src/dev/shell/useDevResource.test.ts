import { describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { useDevResource } from './useDevResource';

/** A fetcher whose every call waits until the test settles it. */
function fetcher() {
  const calls: { resolve: (data: string) => void; reject: (err: Error) => void }[] = [];
  const load = () =>
    new Promise<string>((resolve, reject) => {
      calls.push({ resolve, reject });
    });
  return { load, calls };
}

describe('useDevResource', () => {
  it('gives what was loaded', async () => {
    const { load, calls } = fetcher();
    const { result } = renderHook(() => useDevResource(load));
    await act(async () => calls[0].resolve('worklist'));
    expect(result.current.data).toBe('worklist');
  });

  it('says why loading failed', async () => {
    const { load, calls } = fetcher();
    const { result } = renderHook(() => useDevResource(load));
    await act(async () => calls[0].reject(new Error('HTTP 404')));
    expect(result.current.error).toBe('HTTP 404');
  });

  it('keeps showing what it had while it loads again', async () => {
    const { load, calls } = fetcher();
    const { result } = renderHook(() => useDevResource(load));
    await act(async () => calls[0].resolve('before'));
    act(() => result.current.reload());
    expect(result.current.data).toBe('before');
    await act(async () => calls[1].resolve('after'));
    expect(result.current.data).toBe('after');
  });

  it('forgets a failure once loading again worked', async () => {
    const { load, calls } = fetcher();
    const { result } = renderHook(() => useDevResource(load));
    await act(async () => calls[0].reject(new Error('HTTP 404')));
    act(() => result.current.reload());
    await act(async () => calls[1].resolve('worklist'));
    expect(result.current.error).toBeNull();
  });

  it('drops an answer a later reload has overtaken', async () => {
    const { load, calls } = fetcher();
    const { result } = renderHook(() => useDevResource(load));
    act(() => result.current.reload());
    await act(async () => calls[1].resolve('new'));
    await act(async () => calls[0].resolve('old'));
    expect(result.current.data).toBe('new');
  });

  it('keeps what the panel changed of what was loaded', async () => {
    const { load, calls } = fetcher();
    const { result } = renderHook(() => useDevResource(load));
    await act(async () => calls[0].resolve('worklist'));
    act(() => result.current.update((data) => `${data} + 1 decision`));
    expect(result.current.data).toBe('worklist + 1 decision');
  });
});
