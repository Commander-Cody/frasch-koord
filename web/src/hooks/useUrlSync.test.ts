import { beforeEach, describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';

import type { UrlState } from '../urlState';
import { useUrlSync } from './useUrlSync';

beforeEach(() => {
  window.history.replaceState(null, '', '/#12/54.79/8.83');
});

describe('useUrlSync', () => {
  it('puts the view and the open place into the address bar', () => {
    renderHook(() => useUrlSync({ view: 'frr-x-local', place: 'naibel' }));
    expect(window.location.search).toBe('?view=frr-x-local&place=naibel');
  });

  it('follows a change, dropping the place once the card is closed', () => {
    const initialProps: UrlState = { view: 'frr-x-mooring', place: 'naibel' };
    const { rerender } = renderHook((state: UrlState) => useUrlSync(state), { initialProps });
    rerender({ view: 'frr-x-local' });
    expect(window.location.search).toBe('?view=frr-x-local');
  });

  it("keeps MapLibre's viewport hash", () => {
    renderHook(() => useUrlSync({ view: 'frr-x-mooring', place: 'naibel' }));
    expect(window.location.hash).toBe('#12/54.79/8.83');
  });
});
