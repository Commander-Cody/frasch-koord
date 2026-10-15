import { expect, it, vi } from 'vitest';

import { registerPmtilesProtocol } from './pmtiles';

const maplibre = vi.hoisted(() => ({ addProtocol: vi.fn() }));
vi.mock('maplibre-gl', () => ({ addProtocol: maplibre.addProtocol }));

it('registers the protocol with MapLibre once, however often a map mounts', () => {
  registerPmtilesProtocol();
  registerPmtilesProtocol();

  expect(maplibre.addProtocol).toHaveBeenCalledOnce();
  expect(maplibre.addProtocol).toHaveBeenCalledWith('pmtiles', expect.any(Function));
});
