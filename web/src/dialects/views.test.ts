import { expect, it } from 'vitest';

import { DIALECTS } from './registry';
import { ALL_VIEW_TAGS, DEFAULT_VIEW, LOCAL_TAG, VIEWS, viewOption } from './views';

// Held to the registry's flags rather than to today's registry, so that a
// dialect gaining or losing `view=yes` needs no edit here.

it('offers the dialects the registry marks as views, in registry order', () => {
  const offered = DIALECTS.filter((d) => d.view === 'yes').map((d) => d.tag);
  expect(VIEWS.slice(0, -1).map((option) => option.tag)).toEqual(offered);
});

it('offers the local view last', () => {
  expect(VIEWS.at(-1)?.tag).toBe(LOCAL_TAG);
});

it('answers a tag the selector does not offer with the default view', () => {
  expect(viewOption('frr-x-nowhere').tag).toBe(DEFAULT_VIEW);
});

it('can label the map in every dialect of the registry, offered or not, and in the local view', () => {
  expect([...ALL_VIEW_TAGS].sort()).toEqual([...DIALECTS.map((d) => d.tag), LOCAL_TAG].sort());
});
