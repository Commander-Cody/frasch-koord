import { expect, it } from 'vitest';
import type { LayerSpecification, SymbolLayerSpecification } from 'maplibre-gl';

import { evaluateTextField } from '../../testing/textField';
import { labelLayers, nameExpression } from './labels';

function symbolLayer(layer: Partial<SymbolLayerSpecification>): LayerSpecification {
  return { id: 'label', type: 'symbol', source: 'tiles', ...layer };
}

function textFieldOf(layers: LayerSpecification[]): unknown {
  return (layers[0] as SymbolLayerSpecification).layout?.['text-field'];
}

it('labels a layer marked frasch:label by the chain of the view', () => {
  const marked = symbolLayer({
    metadata: { 'frasch:label': true },
    layout: { 'text-field': ['get', 'name'] },
  });

  expect(textFieldOf(labelLayers([marked], 'frr-x-mooring'))).toEqual(
    nameExpression('frr-x-mooring'),
  );
});

it('leaves the text-field of an unmarked layer as it is', () => {
  const unmarked = symbolLayer({ layout: { 'text-field': '{name}' } });

  expect(textFieldOf(labelLayers([unmarked], 'frr-x-mooring'))).toBe('{name}');
});

it('labels a place in a Frisian area by its local name before the other dialects', () => {
  const wik = {
    'frasch:local': 'Wik',
    'frasch:dialect': 'frr-x-fering',
    'name:frr-x-solring': 'Wiik',
  };

  expect(evaluateTextField(nameExpression('frr-x-mooring'), wik)).toBe('Wik');
});

it('labels a place in a Synnejysk area by its Frisian name before its local one', () => {
  const laigem = { 'frasch:local': 'Lym', 'frasch:dialect': 'jut', 'name:frr': 'Läigem' };

  expect(evaluateTextField(nameExpression('frr-x-mooring'), laigem)).toBe('Läigem');
});

it('labels a place in no area by its local name before its Low Saxon one', () => {
  const garding = { 'frasch:local': 'Garn', 'name:nds': 'Garding', 'name:de': 'Garding' };

  expect(evaluateTextField(nameExpression('frr-x-mooring'), garding)).toBe('Garn');
});
