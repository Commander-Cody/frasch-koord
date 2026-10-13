import { beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_VIEW, LOCAL_TAG } from '../config';
import { initialView, linkedPlace, writePlace, writeView } from './linkState';

function setLocation(url: string) {
  window.history.replaceState(null, '', url);
}

beforeEach(() => {
  setLocation('/');
});

describe('initialView', () => {
  it("is the link's view", () => {
    setLocation(`/?view=${LOCAL_TAG}`);
    expect(initialView()).toBe(LOCAL_TAG);
  });

  it('is the default view for a link without one', () => {
    expect(initialView()).toBe(DEFAULT_VIEW);
  });

  it('is the default view for a tag the selector does not offer', () => {
    setLocation('/?view=frr-x-nowhere');
    expect(initialView()).toBe(DEFAULT_VIEW);
  });
});

describe('linkedPlace', () => {
  it('is the place the link names, to fly to', () => {
    setLocation('/?place=naibel');
    expect(linkedPlace()).toEqual({ ref: 'naibel', keepViewport: false });
  });

  it("keeps the link's own viewport", () => {
    setLocation('/?place=naibel#12/54.79/8.83');
    expect(linkedPlace()).toEqual({ ref: 'naibel', keepViewport: true });
  });

  it('is nothing for a link without a place', () => {
    setLocation('/?view=frr-x-mooring#12/54.79/8.83');
    expect(linkedPlace()).toBeUndefined();
  });
});

describe('writeView', () => {
  it('puts the view into the address bar', () => {
    writeView(LOCAL_TAG);
    expect(window.location.search).toBe(`?view=${LOCAL_TAG}`);
  });
});

describe('writePlace', () => {
  it('puts the open place into the address bar, next to the view', () => {
    setLocation('/?view=frr-x-mooring');
    writePlace('naibel');
    expect(window.location.search).toBe('?view=frr-x-mooring&place=naibel');
  });

  it('takes the place out once no card is open', () => {
    setLocation('/?view=frr-x-mooring&place=naibel');
    writePlace(undefined);
    expect(window.location.search).toBe('?view=frr-x-mooring');
  });
});
