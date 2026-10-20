import { describe, expect, it } from 'vitest';

import { duplicates } from './newPlaces';
import type { ListedPlace } from './worklist';

const HOORN: ListedPlace = { id: 'hoorn', kind: 'warft', names: { mooring: 'Hoorn', de: 'Horn' } };
const NORDWARW: ListedPlace = {
  id: 'nordwarw',
  kind: 'warft',
  names: { mooring: 'Nordwärw; Nordwarw (alt)', de: 'Nordwarft' },
};
const PLACES = [HOORN, NORDWARW];

describe('duplicates', () => {
  it('are the places that have a name typed, in whichever column', () => {
    expect(duplicates({ fering: 'Horn' }, PLACES)).toEqual([HOORN]);
  });

  it('match a variant of a cell, its remarks left out', () => {
    expect(duplicates({ mooring: 'Nordwarw' }, PLACES)).toEqual([NORDWARW]);
  });

  it('match each variant typed', () => {
    expect(duplicates({ de: 'Hörn; Nordwarft (neu)' }, PLACES)).toEqual([NORDWARW]);
  });

  it('ignore case', () => {
    expect(duplicates({ de: 'horn' }, PLACES)).toEqual([HOORN]);
  });

  it('are none for a name only a part of one is', () => {
    expect(duplicates({ de: 'Hor' }, PLACES)).toEqual([]);
  });
});
