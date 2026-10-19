import { afterEach, expect, it, vi } from 'vitest';
import type {
  StyleSpecification,
  SymbolLayerSpecification,
  VectorSourceSpecification,
} from 'maplibre-gl';

import { LOCAL_TAG } from '../../dialects/views';
import { BASE_STYLE, placeLayerIds, styleFor } from './index';
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
  vi.stubEnv('TILES_ARCHIVE', 'sh.pmtiles');
  vi.resetModules();
  // TILES_URL is read at module load: load the style afresh under the stubbed env.
  const { styleFor } = await import('./index');
  const source = styleFor(LOCAL_TAG).sources.openmaptiles as VectorSourceSpecification;
  expect(source.url).toBe(`pmtiles://${origin}/tiles/sh.pmtiles`);
});

it('names no third-party URL in the style file', () => {
  expect(JSON.stringify(BASE_STYLE)).not.toMatch(/[a-z]+:\/\//);
});

it("labels places with the view's label expression", () => {
  expect(textField('place-village')).toEqual(nameExpression(LOCAL_TAG));
});

it('leaves the road shields showing their ref', () => {
  expect(textField('highway-shield')).toBe('{ref}');
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

it('takes the symbol layers of the place source-layer for the place labels, and no other', () => {
  const style: StyleSpecification = {
    version: 8,
    sources: { tiles: { type: 'vector', url: 'pmtiles://tiles' } },
    layers: [
      { id: 'background', type: 'background' },
      { id: 'place-town', type: 'symbol', source: 'tiles', 'source-layer': 'place' },
      { id: 'place-dot', type: 'circle', source: 'tiles', 'source-layer': 'place' },
      { id: 'water-name', type: 'symbol', source: 'tiles', 'source-layer': 'water_name' },
      { id: 'place-city', type: 'symbol', source: 'tiles', 'source-layer': 'place' },
    ],
  };

  expect(placeLayerIds(style)).toEqual(['place-town', 'place-city']);
});
