import { describe, expect, it } from 'vitest';
import { featureFilter } from '@maplibre/maplibre-gl-style-spec';
import type { FilterSpecification } from 'maplibre-gl';

import { DIALECTS } from '../../dialects/registry';
import { UNASSIGNED, type AreaProps } from './areas';
import { areaLayers, DIALECT_COLORS, type AreaLayerState } from './areaLayers';

const MULTI: AreaProps = {
  assigned: true,
  dialect: 'frr-x-fering',
  name: 'Föhr',
  osm: 'relation/1; relation/9',
  km2: 82,
};
const SINGLE: AreaProps = { ...MULTI, name: 'Wyk', osm: 'relation/1' };
const LOOSE: AreaProps = { assigned: false, name: 'Loose', osm: 'relation/5', km2: 3 };

/** The names of the municipalities layer `id` draws in `state`. */
function drawn(state: AreaLayerState, id: string): string[] {
  const layers = areaLayers(state);
  const at = layers.findIndex((spec) => spec.id === id);
  const layer = layers[at];
  const filter = 'filter' in layer ? layer.filter : undefined;
  const matches = featureFilter(filter as FilterSpecification | undefined, `layers[${at}].filter`);
  return [MULTI, SINGLE, LOOSE]
    .filter((properties) => matches.filter({ zoom: 10 }, { type: 3, properties } as never))
    .map((properties) => properties.name);
}

it('has a colour for exactly the dialects of the registry', () => {
  expect(Object.keys(DIALECT_COLORS).sort()).toEqual(DIALECTS.map((dialect) => dialect.tag).sort());
});

describe('areaLayers', () => {
  it('outlines the municipality of a row with several references, and no other', () => {
    expect(drawn({ selectedOsm: MULTI.osm, shown: null }, 'areas-selected')).toEqual(['Föhr']);
  });

  it('outlines nothing while nothing is selected', () => {
    expect(drawn({ selectedOsm: null, shown: null }, 'areas-selected')).toEqual([]);
  });

  it('draws every municipality while no group is shown alone', () => {
    expect(drawn({ selectedOsm: null, shown: null }, 'areas-fill')).toEqual([
      'Föhr',
      'Wyk',
      'Loose',
    ]);
  });

  it('draws the unassigned alone', () => {
    expect(drawn({ selectedOsm: null, shown: UNASSIGNED }, 'areas-line')).toEqual(['Loose']);
  });

  it('draws one dialect alone', () => {
    expect(drawn({ selectedOsm: null, shown: 'frr-x-fering' }, 'areas-fill')).toEqual([
      'Föhr',
      'Wyk',
    ]);
  });
});
