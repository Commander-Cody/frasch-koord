import { createPropertyExpression, latest } from '@maplibre/maplibre-gl-style-spec';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';

import type { TileProps } from '../names/tile';

/**
 * What MapLibre's own style-spec expression engine makes of a `text-field`
 * expression for a point feature with the properties `props`: the label the
 * map would render.
 */
export function evaluateTextField(expression: ExpressionSpecification, props: TileProps): string {
  const result = createPropertyExpression(
    expression,
    'text-field',
    // The style-spec JSON's own type is looser than the (unexported)
    // StylePropertySpecification createPropertyExpression wants; go via its
    // own parameter type rather than reaching for `any`.
    latest.layout_symbol['text-field'] as unknown as Parameters<typeof createPropertyExpression>[2],
  );
  if (result.result === 'error') {
    throw new Error(`invalid text-field expression: ${JSON.stringify(result.value)}`);
  }
  const value = result.value.evaluate({ zoom: 10 }, { properties: props, type: 'Point' });
  return value.toString();
}
