import { beforeEach, describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import i18n from '../i18n';
import { DEFAULT_VIEW, LOCAL_TAG, viewOption } from './views';
import { useView } from './useView';

beforeEach(async () => {
  window.history.replaceState(null, '', '/');
  // A language no label option brings along, so a switch shows.
  await i18n.changeLanguage('de');
});

describe('useView', () => {
  it("starts in the link's view", () => {
    window.history.replaceState(null, '', `/?view=${LOCAL_TAG}`);
    const { result } = renderHook(() => useView());
    expect(result.current[0]).toBe(LOCAL_TAG);
  });

  it('puts the UI into the language of the view the page opens in', () => {
    renderHook(() => useView());
    expect(i18n.language).toBe(viewOption(DEFAULT_VIEW).uiLanguage);
  });

  it('puts the UI into the language of the view switched to', async () => {
    const { result } = renderHook(() => useView());
    await act(() => i18n.changeLanguage('de'));
    act(() => result.current[1](LOCAL_TAG));
    expect(i18n.language).toBe(viewOption(LOCAL_TAG).uiLanguage);
  });

  it('puts the view the page opens in into the address bar', () => {
    renderHook(() => useView());
    expect(window.location.search).toBe(`?view=${DEFAULT_VIEW}`);
  });

  it('keeps the view in the address bar', () => {
    const { result } = renderHook(() => useView());
    act(() => result.current[1](LOCAL_TAG));
    expect(window.location.search).toBe(`?view=${LOCAL_TAG}`);
  });
});
