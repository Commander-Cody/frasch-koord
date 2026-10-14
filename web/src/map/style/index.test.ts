import { afterEach, expect, it, vi } from 'vitest';
import type { SymbolLayerSpecification, VectorSourceSpecification } from 'maplibre-gl';

import { LOCAL_TAG } from '../../dialects/views';
import { styleFor } from './index';
import { nameExpression } from './labels';

const origin = window.location.origin;

afterEach(() => {
  vi.unstubAllEnvs();
});

function textField(layerId: string): unknown {
  const layer = styleFor(LOCAL_TAG).layers.find((l) => l.id === layerId);
  return (layer as SymbolLayerSpecification).layout?.['text-field'];
}

it("reads the tiles from the site's archive", async () => {
  vi.stubEnv('VITE_TILES_URL', '');
  vi.resetModules();
  // TILES_URL is read at module load: load the style afresh under the stubbed env.
  const { styleFor } = await import('./index');
  const source = styleFor(LOCAL_TAG).sources.openmaptiles as VectorSourceSpecification;
  expect(source.url).toBe(`pmtiles://${origin}/tiles/schleswig-holstein.pmtiles`);
});

it("labels places with the view's label expression", () => {
  expect(textField('place-village')).toEqual(nameExpression(LOCAL_TAG));
});

it('serves glyphs and sprites from the site root by default', () => {
  const style = styleFor('frr-x-mooring');
  expect(style.glyphs).toBe(`${origin}/fonts/{fontstack}/{range}.pbf`);
  expect(style.sprite).toBe(`${origin}/sprites/sprite`);
});

it('respects a non-root base', () => {
  vi.stubEnv('BASE_URL', '/frasch-koord/');
  const style = styleFor('frr-x-mooring');
  // The placeholders stay as they are, not percent-encoded.
  expect(style.glyphs).toBe(`${origin}/frasch-koord/fonts/{fontstack}/{range}.pbf`);
  expect(style.sprite).toBe(`${origin}/frasch-koord/sprites/sprite`);
});
