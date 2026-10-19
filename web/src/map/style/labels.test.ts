import { expect, it } from 'vitest';
import type { LayerSpecification, SymbolLayerSpecification } from 'maplibre-gl';

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
