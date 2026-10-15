// The `pmtiles://` protocol MapLibre reads the map's PMTiles archive through.

import { addProtocol } from 'maplibre-gl';
import { Protocol } from 'pmtiles';

const protocol = new Protocol();
let protocolRegistered = false;

/** Registers the `pmtiles://` protocol with MapLibre, once however often a map mounts. */
export function registerPmtilesProtocol(): void {
  if (protocolRegistered) return;
  addProtocol('pmtiles', protocol.tile);
  protocolRegistered = true;
}
