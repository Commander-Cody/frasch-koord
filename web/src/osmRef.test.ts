import { describe, expect, it } from 'vitest';

import { osmRefs, osmUrl, parseOsmRef } from './osmRef';

describe('osmRefs', () => {
  it('splits a cell into its references', () => {
    expect(osmRefs('way/1347936331; node/1332249790')).toEqual([
      'way/1347936331',
      'node/1332249790',
    ]);
  });

  it('does not need a space after the semicolon', () => {
    expect(osmRefs('way/1;node/2')).toEqual(['way/1', 'node/2']);
  });

  it('keeps a local reference as the one it is', () => {
    expect(osmRefs('local/westerheide-amrum')).toEqual(['local/westerheide-amrum']);
  });

  it.each(['', undefined])('has none for the empty cell %j', (cell) => {
    expect(osmRefs(cell)).toEqual([]);
  });
});

describe('osmUrl', () => {
  it('links a node', () => {
    expect(osmUrl('node/240042766')).toBe('https://www.openstreetmap.org/node/240042766');
  });

  it('links a way', () => {
    expect(osmUrl('way/1087160352')).toBe('https://www.openstreetmap.org/way/1087160352');
  });

  it('links a relation', () => {
    expect(osmUrl('relation/3352541')).toBe('https://www.openstreetmap.org/relation/3352541');
  });

  it('returns null for a synthetic local/ place', () => {
    expect(osmUrl('local/some-slug')).toBeNull();
  });

  it('returns null for a bare Wikidata QID', () => {
    expect(osmUrl('Q123')).toBeNull();
  });

  it('returns null for a whole cell of several references', () => {
    expect(osmUrl('way/1347936331; node/1332249790')).toBeNull();
  });

  it('returns null when there is no reference at all', () => {
    expect(osmUrl(undefined)).toBeNull();
  });
});

describe('parseOsmRef', () => {
  it('takes a reference as a cell spells it', () => {
    expect(parseOsmRef('way/177387348')).toBe('way/177387348');
  });

  it('takes the object of a pasted openstreetmap.org URL', () => {
    expect(parseOsmRef('https://www.openstreetmap.org/way/177387348#map=17/54.7/8.8')).toBe(
      'way/177387348',
    );
  });

  it('spells the type in lowercase', () => {
    expect(parseOsmRef('Relation/3352541')).toBe('relation/3352541');
  });

  it('ignores the space around what was typed', () => {
    expect(parseOsmRef(' node/123 ')).toBe('node/123');
  });

  it.each(['', 'node/abc', 'local/some-slug', 'Q123', 'way/1 way/2'])(
    'returns null for %j, which names no OSM object',
    (text) => {
      expect(parseOsmRef(text)).toBeNull();
    },
  );
});
