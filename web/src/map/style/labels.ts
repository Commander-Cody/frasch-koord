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

/**
 * Does this symbol layer's text-field render the feature's `name`
 * (possibly combined with `name:latin`/`name:nonlatin` in various
 * OpenMapTiles/OSM Bright templating styles)? Layers that label something
 * else entirely (e.g. `{ref}` road shields) are left untouched.
 */
function referencesName(textField: unknown): boolean {
  if (typeof textField === 'string') {
    return textField.includes('name');
  }
  if (Array.isArray(textField)) {
    // Recurse into expressions such as ["concat", ["get", "name:latin"], ...]
    return textField.some((part) => referencesName(part));
  }
  return false;
}

/**
 * `layers` with every symbol layer's name-based `text-field` rewritten to
 * `nameExpression(view)`. `view` is a dialect tag or LOCAL_TAG.
 */
export function labelLayers(layers: LayerSpecification[], view: string): LayerSpecification[] {
  const textFieldExpression = nameExpression(view);
  return layers.map((layer): LayerSpecification => {
    if (layer.type !== 'symbol' || !layer.layout) return layer;
    const textField = (layer.layout as Record<string, unknown>)['text-field'];
    if (textField === undefined || !referencesName(textField)) return layer;
    return { ...layer, layout: { ...layer.layout, 'text-field': textFieldExpression } };
  });
}
