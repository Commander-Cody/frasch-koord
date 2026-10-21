import { describe, expect, it } from 'vitest';

import partsSchema from '../../../../names/dialect-area-parts.schema.json';
import { pinnedFields, schemaFields, type Pin } from '../../testing/schemaPin';
import {
  bboxOf,
  filterAreas,
  findByRef,
  groupByDialect,
  groupLabel,
  UNASSIGNED,
  type AreaFeature,
  type AreaProps,
} from './areas';

/** A municipality, assigned to `dialect` unless that is undefined. */
function area(name: string, dialect?: string): AreaFeature {
  const row = dialect === undefined ? {} : { dialect, note: '', line: 2 };
  return {
    type: 'Feature',
    properties: { assigned: dialect !== undefined, name, osm: `relation/${name}`, km2: 1, ...row },
    geometry: { type: 'Polygon', coordinates: [] },
  };
}

/** The groups as `key: names`. */
function grouped(features: AreaFeature[], order: string[]): string[] {
  return groupByDialect(features, order).map(
    (group) => `${group.key}: ${group.features.map((f) => f.properties.name).join(', ')}`,
  );
}

// AreaProps is written by hand; this pins it to the contract of the parts
// file, names/dialect-area-parts.schema.json (see testing/schemaPin.ts).
it('AreaProps has the fields of a part of the schema', () => {
  const pin: Pin<AreaProps> = {
    assigned: { boolean: true },
    dialect: { string: true, optional: true },
    name: { string: true },
    note: { string: true, optional: true },
    osm: { string: true },
    line: { number: true, optional: true },
    km2: { number: true },
  };
  expect(pinnedFields(pin)).toEqual(schemaFields(partsSchema.$defs.part, partsSchema));
});

describe('bboxOf', () => {
  it('spans every ring of a multipolygon', () => {
    const coordinates = [
      [
        [
          [8.1, 54.5],
          [8.3, 54.6],
          [8.2, 54.4],
        ],
      ],
      [
        [
          [9.0, 54.9],
          [8.9, 54.8],
          [9.1, 54.7],
        ],
      ],
    ];
    expect(bboxOf({ coordinates })).toEqual([
      [8.1, 54.4],
      [9.1, 54.9],
    ]);
  });

  it('has none for a geometry without a point', () => {
    expect(bboxOf({ coordinates: [] })).toBeNull();
  });
});

describe('groupByDialect', () => {
  it('puts the dialects in the order given, the unassigned last', () => {
    const features = [area('Risum', 'b'), area('Loose'), area('Naibel', 'a')];
    expect(grouped(features, ['a', 'b'])).toEqual([
      'a: Naibel',
      'b: Risum',
      `${UNASSIGNED}: Loose`,
    ]);
  });

  it('puts a dialect the order does not know after the known ones', () => {
    const features = [area('Risum', 'x'), area('Loose'), area('Naibel', 'a')];
    expect(grouped(features, ['a'])).toEqual(['a: Naibel', 'x: Risum', `${UNASSIGNED}: Loose`]);
  });

  it('sorts the municipalities of a dialect by name', () => {
    const features = [area('Risum', 'a'), area('Bargum', 'a'), area('Naibel', 'a')];
    expect(grouped(features, ['a'])).toEqual(['a: Bargum, Naibel, Risum']);
  });
});

describe('filterAreas', () => {
  it('finds a municipality by a word of its research note', () => {
    const noted = {
      ...area('Risum', 'a'),
      properties: { ...area('Risum', 'a').properties, note: 'Bökingharde' },
    };
    const names = filterAreas([area('Naibel', 'a'), noted], { text: 'böking', shown: null }).map(
      (feature) => feature.properties.name,
    );
    expect(names).toEqual(['Risum']);
  });

  it('shows the unassigned alone', () => {
    const names = filterAreas([area('Naibel', 'a'), area('Loose')], {
      text: '',
      shown: UNASSIGNED,
    }).map((feature) => feature.properties.name);
    expect(names).toEqual(['Loose']);
  });
});

describe('groupLabel', () => {
  it('calls the municipalities no row claims what they are by default: Low Saxon', () => {
    expect(groupLabel(UNASSIGNED)).toBe('no row – Low Saxon by default');
  });
});

describe('findByRef', () => {
  const foehr = {
    ...area('Föhr', 'a'),
    properties: { ...area('Föhr', 'a').properties, osm: 'relation/1; relation/9' },
  };

  it('finds a row by a later one of its references', () => {
    expect(findByRef([area('Naibel', 'a'), foehr], 'relation/9')).toBe(foehr);
  });

  it('finds nothing for a reference no row has', () => {
    expect(findByRef([area('Naibel', 'a'), foehr], 'relation/7')).toBeUndefined();
  });
});
