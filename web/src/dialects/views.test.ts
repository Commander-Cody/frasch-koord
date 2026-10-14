import { expect, it } from 'vitest';

import { ALL_VIEW_TAGS, DEFAULT_VIEW, VIEWS, viewOption } from './views';

// The registry (src/dialects/generated/dialects.json) marks only Mooring
// `view=yes`; its order is mooring, wieding, karrhard, nordgoes, midgoes,
// suedgoes, fering, oomrang, solring, hallig, halunder.

it('offers the dialects the registry marks as views, then the local view', () => {
  expect(VIEWS.map((option) => option.tag)).toEqual(['frr-x-mooring', 'frr-x-local']);
});

it('answers a tag the selector does not offer with the default view', () => {
  expect(viewOption('frr-x-nowhere').tag).toBe(DEFAULT_VIEW);
});

it('can label the map in every dialect and in the local view', () => {
  expect(ALL_VIEW_TAGS).toEqual([
    'frr-x-mooring',
    'frr-x-wieding',
    'frr-x-karrhard',
    'frr-x-nordgoes',
    'frr-x-midgoes',
    'frr-x-suedgoes',
    'frr-x-fering',
    'frr-x-oomrang',
    'frr-x-solring',
    'frr-x-hallig',
    'frr-x-halunder',
    'frr-x-local',
  ]);
});
