import { expect, it, vi } from 'vitest';
import type { AddProtocolAction, RequestParameters } from 'maplibre-gl';
import type { Header } from 'pmtiles';

import { pmtilesArchive, registerPmtilesProtocol } from './pmtiles';

// The protocol MapLibre would call for every `pmtiles://` request.
const maplibre = vi.hoisted(() => ({ protocols: new Map<string, AddProtocolAction>() }));
vi.mock('maplibre-gl', () => ({
  addProtocol: (name: string, action: AddProtocolAction) => maplibre.protocols.set(name, action),
}));

const ARCHIVE_URL = 'pmtiles://https://tiles.example/schleswig-holstein.pmtiles';

it("reads the map's tiles from the archive everyone else reads", async () => {
  registerPmtilesProtocol();
  const archive = pmtilesArchive(ARCHIVE_URL)!;
  const header = { minZoom: 0, maxZoom: 14, minLon: 8, minLat: 54, maxLon: 9, maxLat: 55 };
  const getHeader = vi.spyOn(archive, 'getHeader').mockResolvedValue(header as Header);

  const request: RequestParameters = { url: ARCHIVE_URL, type: 'json' };
  await maplibre.protocols.get('pmtiles')!(request, new AbortController());

  expect(getHeader).toHaveBeenCalled();
});

it('has no archive for a tile source that is not a PMTiles archive', () => {
  expect(pmtilesArchive('https://tiles.example/tiles.json')).toBeUndefined();
});
