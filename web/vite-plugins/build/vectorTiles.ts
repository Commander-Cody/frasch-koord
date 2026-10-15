/**
 * Reads the vector tiles of a local PMTiles archive, every distinct tile
 * once: the archive's own directory walked, leaf directories included.
 */
import { closeSync, openSync, readSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { VectorTile } from '@mapbox/vector-tile';
import { PbfReader } from 'pbf';
import { Compression, type Header, PMTiles, type RangeResponse, type Source } from 'pmtiles';

/**
 * A PMTiles source on a local file. It reads synchronously, and gzip is
 * left to zlib (`decompressTile`): for the ~20 000 small reads of a whole
 * archive that takes a fifth of the time the async file API and pmtiles'
 * own DecompressionStream take.
 */
function fileSource(path: string): Source & { close(): void } {
  const fd = openSync(path, 'r');
  return {
    getKey: () => path,
    async getBytes(offset: number, length: number): Promise<RangeResponse> {
      const buffer = Buffer.alloc(length);
      const bytesRead = readSync(fd, buffer, 0, length, offset);
      return { data: buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + bytesRead) };
    },
    close: () => closeSync(fd),
  };
}

/** A tile's bytes as stored, decompressed. */
function decompressTile(archive: PMTiles, data: ArrayBuffer, compression: Compression) {
  return compression === Compression.Gzip
    ? gunzipSync(data)
    : archive.decompress(data, compression);
}

/** The tiles of the directory at `directory`, and of the leaf directories it points to. */
async function* tilesOf(
  archive: PMTiles,
  header: Header,
  directory: { offset: number; length: number },
  seen: Set<number>,
): AsyncGenerator<VectorTile> {
  const entries = await archive.cache.getDirectory(
    archive.source,
    directory.offset,
    directory.length,
    header,
  );
  for (const { offset, length, runLength } of entries) {
    if (runLength === 0) {
      const leaf = { offset: header.leafDirectoryOffset + offset, length };
      yield* tilesOf(archive, header, leaf, seen);
    } else if (!seen.has(offset)) {
      // a tile repeated across the map (open sea) is stored once
      seen.add(offset);
      const { data } = await archive.source.getBytes(header.tileDataOffset + offset, length);
      const tile = await decompressTile(archive, data, header.tileCompression);
      yield new VectorTile(new PbfReader(new Uint8Array(tile)));
    }
  }
}

/** Every distinct tile of the archive at `path`. */
export async function* vectorTiles(path: string): AsyncGenerator<VectorTile> {
  const source = fileSource(path);
  try {
    const archive = new PMTiles(source);
    const header = await archive.getHeader();
    const root = { offset: header.rootDirectoryOffset, length: header.rootDirectoryLength };
    yield* tilesOf(archive, header, root, new Set());
  } finally {
    source.close();
  }
}
