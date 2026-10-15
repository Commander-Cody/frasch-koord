/**
 * For the tests: writes a small PMTiles v3 archive of vector tiles whose
 * features carry the given properties. Every feature is a point.
 */
import { writeFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { PbfWriter } from 'pbf';
import { zxyToTileId } from 'pmtiles';

/** A tile and its layers: each a list of features, each a feature's properties. */
export interface TestTile {
  z: number;
  x: number;
  y: number;
  layers: Record<string, Record<string, string>[]>;
}

const HEADER_BYTES = 127;
const NO_COMPRESSION = 1;
const GZIP = 2;
const MVT = 1;

/** A point at the tile's corner: MoveTo(1), then (0, 0). */
const POINT = [9, 0, 0];

function encodeLayer(name: string, features: Record<string, string>[], pbf: PbfWriter): void {
  const keys = [...new Set(features.flatMap(Object.keys))];
  const values = [...new Set(features.flatMap(Object.values))];
  pbf.writeVarintField(15, 2);
  pbf.writeStringField(1, name);
  for (const props of features) {
    pbf.writeMessage(
      2,
      (_: unknown, f: PbfWriter) => {
        const tags = Object.entries(props).flatMap(([k, v]) => [
          keys.indexOf(k),
          values.indexOf(v),
        ]);
        f.writePackedVarint(2, tags);
        f.writeVarintField(3, 1);
        f.writePackedVarint(4, POINT);
      },
      null,
    );
  }
  for (const key of keys) pbf.writeStringField(3, key);
  for (const value of values) {
    pbf.writeMessage(4, (_: unknown, v: PbfWriter) => v.writeStringField(1, value), null);
  }
  pbf.writeVarintField(5, 4096);
}

function encodeTile(layers: TestTile['layers']): Uint8Array {
  const pbf = new PbfWriter();
  for (const [name, features] of Object.entries(layers)) {
    pbf.writeMessage(3, (_: unknown, l: PbfWriter) => encodeLayer(name, features, l), null);
  }
  return pbf.finish();
}

interface DirEntry {
  tileId: number;
  offset: number;
  length: number;
  runLength: number;
}

/** A directory as the PMTiles spec lays it out: column by column, ids as deltas. */
function encodeDirectory(entries: DirEntry[]): Uint8Array {
  const pbf = new PbfWriter();
  pbf.writeVarint(entries.length);
  entries.forEach((e, i) => pbf.writeVarint(e.tileId - (entries[i - 1]?.tileId ?? 0)));
  for (const e of entries) pbf.writeVarint(e.runLength);
  for (const e of entries) pbf.writeVarint(e.length);
  for (const e of entries) pbf.writeVarint(e.offset + 1);
  return pbf.finish();
}

function header(fields: {
  root: Uint8Array;
  leaves: Uint8Array;
  tileData: number;
  tiles: number;
  maxZoom: number;
  tileCompression: number;
}): Uint8Array {
  const bytes = new Uint8Array(HEADER_BYTES);
  const view = new DataView(bytes.buffer);
  bytes.set(new TextEncoder().encode('PMTiles'));
  view.setUint8(7, 3);
  const metadata = HEADER_BYTES + fields.root.length;
  const leaves = metadata;
  const tileData = leaves + fields.leaves.length;
  const u64 = [
    HEADER_BYTES,
    fields.root.length,
    metadata,
    0,
    leaves,
    fields.leaves.length,
    tileData,
    fields.tileData,
    fields.tiles,
    fields.tiles,
    fields.tiles,
  ];
  u64.forEach((value, i) => view.setBigUint64(8 + 8 * i, BigInt(value), true));
  [1, NO_COMPRESSION, fields.tileCompression, MVT, 0, fields.maxZoom].forEach((value, i) =>
    view.setUint8(96 + i, value),
  );
  return bytes;
}

/**
 * Writes `tiles` to `file` as a PMTiles archive, uncompressed. With
 * `gzip`, the tiles are gzip-compressed, as Planetiler writes them. With
 * `leaf`, the root directory points to a leaf directory that holds the
 * tiles, as in an archive too large for one directory.
 */
export function writeTestArchive(
  file: string,
  tiles: TestTile[],
  { gzip = false, leaf = false } = {},
): void {
  const encode = (t: TestTile) => (gzip ? gzipSync(encodeTile(t.layers)) : encodeTile(t.layers));
  const sorted = tiles
    .map((t) => ({ tileId: zxyToTileId(t.z, t.x, t.y), data: encode(t) }))
    .sort((a, b) => a.tileId - b.tileId);
  let offset = 0;
  const entries = sorted.map(({ tileId, data }) => {
    const entry = { tileId, offset, length: data.length, runLength: 1 };
    offset += data.length;
    return entry;
  });
  const leaves = leaf ? encodeDirectory(entries) : new Uint8Array();
  const root = leaf
    ? encodeDirectory([{ tileId: 0, offset: 0, length: leaves.length, runLength: 0 }])
    : encodeDirectory(entries);
  const maxZoom = Math.max(...tiles.map((t) => t.z));
  const parts = [
    header({
      root,
      leaves,
      tileData: offset,
      tiles: tiles.length,
      maxZoom,
      tileCompression: gzip ? GZIP : NO_COMPRESSION,
    }),
    root,
    leaves,
    ...sorted.map((t) => t.data),
  ];
  writeFileSync(file, Buffer.concat(parts));
}
