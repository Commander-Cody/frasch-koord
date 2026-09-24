import { afterEach, describe, expect, it, vi } from 'vitest';
import type { StyleSpecification } from 'maplibre-gl';

import fraschBright from './frasch-bright.json';
import { buildStyle } from './localize';

const base = fraschBright as unknown as StyleSpecification;
const origin = window.location.origin;

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('buildStyle', () => {
  it('serves glyphs and sprites from the site root by default', () => {
    const style = buildStyle(base, 'pmtiles://x', 'frr-x-mooring');
    expect(style.glyphs).toBe(`${origin}/fonts/{fontstack}/{range}.pbf`);
    expect(style.sprite).toBe(`${origin}/sprites/sprite`);
  });

  it('respects a non-root base', () => {
    vi.stubEnv('BASE_URL', '/frasch-koord/');
    const style = buildStyle(base, 'pmtiles://x', 'frr-x-mooring');
    // The placeholders stay as they are, not percent-encoded.
    expect(style.glyphs).toBe(`${origin}/frasch-koord/fonts/{fontstack}/{range}.pbf`);
    expect(style.sprite).toBe(`${origin}/frasch-koord/sprites/sprite`);
  });
});

describe('TILES_URL', () => {
  it('points at the archive under a non-root base', async () => {
    vi.stubEnv('BASE_URL', '/frasch-koord/');
    vi.stubEnv('VITE_TILES_URL', '');
    // Read at module load, so load the module afresh under the stubbed env.
    const { TILES_URL } = await import('../config');
    expect(TILES_URL).toBe(`pmtiles://${origin}/frasch-koord/tiles/schleswig-holstein.pmtiles`);
  });
});
