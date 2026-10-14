// The PMTiles archive behind the map: one `PMTiles` instance per archive,
// shared by MapLibre's `pmtiles://` protocol and the provenance check, so the
// archive's header and directories are read once.

import { addProtocol } from 'maplibre-gl';
import { PMTiles, Protocol } from 'pmtiles';

const PMTILES_PREFIX = 'pmtiles://';

const protocol = new Protocol();
let protocolRegistered = false;

/** Registers the `pmtiles://` protocol with MapLibre, once however often a map mounts. */
export function registerPmtilesProtocol(): void {
  if (protocolRegistered) return;
  addProtocol('pmtiles', protocol.tile);
  protocolRegistered = true;
}

/**
 * The archive a `pmtiles://` tiles URL names, the instance the map's tiles
 * are read from too; none for a tile source that is not a PMTiles archive.
 */
export function pmtilesArchive(tilesUrl: string): PMTiles | undefined {
  if (!tilesUrl.startsWith(PMTILES_PREFIX)) return undefined;
  const url = tilesUrl.slice(PMTILES_PREFIX.length);
  const known = protocol.get(url);
  if (known) return known;
  const archive = new PMTiles(url);
  protocol.add(archive);
  return archive;
}
