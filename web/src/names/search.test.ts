import { describe, expect, it } from 'vitest';

import type { NameEntry } from './entry';
import { createSearch } from './search';

function place(fields: Partial<NameEntry>): NameEntry {
  return { id: 'naibel', names: {}, name_de: '', lon: 8.83, lat: 54.79, kind: '', ...fields };
}

describe('createSearch', () => {
  // A place must be findable under any of its names, whichever view is
  // selected: somebody typing "Naibel" while the map is in Fering still means
  // Niebüll.
  it.each([
    ['a name in a dialect', { names: { 'frr-x-mooring': 'Sought' } }],
    ['its local form', { local: 'Sought' }],
    ["OSM's generic name, which the local view labels it with", { name_osm: 'Sought' }],
    ['its German name', { name_de: 'Sought' }],
  ])('finds a place by %s', (_name, names) => {
    const entry = place(names);

    expect(createSearch([entry])('Sought')).toEqual([entry]);
  });

  it('hands back the entries of the list themselves', () => {
    const entry = place({ name_de: 'Niebüll' });

    expect(createSearch([entry])('Niebüll')[0]).toBe(entry);
  });

  it('finds a place by the beginning of a name', () => {
    const entry = place({ name_de: 'Niebüll' });

    expect(createSearch([entry])('Nieb')).toEqual([entry]);
  });

  it('finds a place by a name with a typo', () => {
    const entry = place({ name_de: 'Niebüll' });

    expect(createSearch([entry])('Niebull')).toEqual([entry]);
  });

  it('leaves out the places no name of which matches', () => {
    const naibel = place({ id: 'naibel', name_de: 'Niebüll' });
    const ribe = place({ id: 'ribe', name_de: 'Ripen' });

    expect(createSearch([naibel, ribe])('Ripen')).toEqual([ribe]);
  });

  it('finds no more than eight places', () => {
    const koogs = Array.from({ length: 9 }, (_, i) => place({ id: `koog-${i}`, name_de: 'Koog' }));

    expect(createSearch(koogs)('Koog')).toHaveLength(8);
  });

  it('finds nothing for a query of spaces only', () => {
    expect(createSearch([place({ name_de: 'Niebüll' })])('  ')).toEqual([]);
  });

  it('finds nothing in an empty list', () => {
    expect(createSearch([])('Niebüll')).toEqual([]);
  });
});
