import { afterEach, expect, it, vi } from 'vitest';
import type { SymbolLayerSpecification, VectorSourceSpecification } from 'maplibre-gl';

import { styleFor } from './index';

const origin = window.location.origin;

afterEach(() => {
  vi.unstubAllEnvs();
});

function textField(layerId: string): unknown {
  const layer = styleFor('frr-x-local').layers.find((l) => l.id === layerId);
  return (layer as SymbolLayerSpecification).layout?.['text-field'];
}

it("reads the tiles from the site's archive", () => {
  const source = styleFor('frr-x-local').sources.openmaptiles as VectorSourceSpecification;
  expect(source.url).toBe(`pmtiles://${origin}/tiles/schleswig-holstein.pmtiles`);
});

it("labels places with the view's label chain", () => {
  expect(textField('place-village')).toEqual([
    'coalesce',
    ['get', 'frasch:local'],
    ['get', 'name:nds'],
    ['get', 'name:latin'],
    ['get', 'name'],
    ['get', 'name:de'],
  ]);
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
