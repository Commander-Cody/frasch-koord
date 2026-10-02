import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useDeepLinkParam } from './useDeepLinkParam';

/** `selection.made` stands in for the panel's selection, as it is when the effect runs. */
function renderDeepLink(ready: boolean) {
  const open = vi.fn();
  const selection = { made: false };
  const hook = renderHook(
    (props: { ready: boolean }) => useDeepLinkParam('row', props.ready, open, () => selection.made),
    {
      initialProps: { ready },
    },
  );
  return { ...hook, open, selection };
}

beforeEach(() => {
  window.history.replaceState(null, '', '/?curate&row=schorkewarw-2');
});

describe('useDeepLinkParam', () => {
  it('opens the linked value once the data is there', () => {
    const { open, rerender } = renderDeepLink(false);
    expect(open).not.toHaveBeenCalled();
    rerender({ ready: true });
    expect(open).toHaveBeenCalledWith('schorkewarw-2');
  });

  it('opens it only once, however often the panel renders', () => {
    const { open, rerender } = renderDeepLink(true);
    rerender({ ready: false });
    rerender({ ready: true });
    expect(open).toHaveBeenCalledTimes(1);
  });

  it('reads the parameter at mount, before the panel writes its own', () => {
    const { open, rerender } = renderDeepLink(false);
    window.history.replaceState(null, '', '/?curate&row=alkersem');
    rerender({ ready: true });
    expect(open).toHaveBeenCalledWith('schorkewarw-2');
  });

  it('leaves a selection the user made before the data arrived', () => {
    const { open, rerender, selection } = renderDeepLink(false);
    selection.made = true;
    rerender({ ready: true });
    expect(open).not.toHaveBeenCalled();
  });

  it('does not open the link later, once the user has chosen without it', () => {
    const { open, rerender, selection } = renderDeepLink(false);
    selection.made = true;
    rerender({ ready: true });
    selection.made = false;
    rerender({ ready: false });
    rerender({ ready: true });
    expect(open).not.toHaveBeenCalled();
  });

  it('opens nothing without the parameter', () => {
    window.history.replaceState(null, '', '/?curate');
    const { open } = renderDeepLink(true);
    expect(open).not.toHaveBeenCalled();
  });
});
