import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

it('points at the archive under a non-root base', async () => {
  vi.stubEnv('BASE_URL', '/frasch-koord/');
  vi.stubEnv('VITE_TILES_URL', '');
  // Read at module load, so load the module afresh under the stubbed env.
  const { TILES_URL } = await import('./site');
  expect(TILES_URL).toBe(
    `pmtiles://${window.location.origin}/frasch-koord/tiles/schleswig-holstein.pmtiles`,
  );
});
