// What a symbol layer of the site's style labels a place with, in a view.
// No `siteUrl` and no `import.meta.env` here: vite-plugins/build/glyphs.ts imports
// this module into the Vite config to read off what any view can show.

import type { LayerSpecification } from 'maplibre-gl';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';

import { labelChain } from '../../dialects/labelChain.ts';

/**
 * Builds the `text-field` expression for a view: a `coalesce` over the tile
 * properties of `labelChain(tag)`, the chain the place card and the search
 * results follow too (see dialects/labelChain.ts).
 */
export function nameExpression(tag: string): ExpressionSpecification {
  return [
    'coalesce',
    ...labelChain(tag).map((key) => ['get', key]),
  ] as unknown as ExpressionSpecification;
}

/** The metadata that marks a symbol layer as labelling a feature by its name. */
const LABEL_MARKER = 'frasch:label';

function isNameLabel(layer: LayerSpecification): boolean {
  return (layer.metadata as Record<string, unknown> | undefined)?.[LABEL_MARKER] === true;
}

/**
 * `layers` with the `text-field` of every layer marked `frasch:label`
 * rewritten to `nameExpression(view)`. `view` is a dialect tag or LOCAL_TAG.
 */
export function labelLayers(layers: LayerSpecification[], view: string): LayerSpecification[] {
  const textFieldExpression = nameExpression(view);
  return layers.map((layer): LayerSpecification => {
    if (layer.type !== 'symbol' || !isNameLabel(layer)) return layer;
    return { ...layer, layout: { ...layer.layout, 'text-field': textFieldExpression } };
  });
}
