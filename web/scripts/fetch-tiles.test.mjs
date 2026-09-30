// @vitest-environment node
/**
 * scripts/fetch-tiles.sh, run as `npm run fetch-tiles` would run it, on a
 * temp web/ root whose tiles.lock pins a file:// URL.
 */
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, readlinkSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), 'fetch-tiles.sh');
const LINK = 'public/tiles/schleswig-holstein.pmtiles';

const PUBLISHED = 'the published archive';
const PUBLISHED_SHA256 = createHash('sha256').update(PUBLISHED).digest('hex');

/** A web/ checkout, and a directory standing in for the release server. */
let root;
let server;

function put(dir, path, text) {
  const file = join(dir, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
  return file;
}

function pin(url, sha256) {
  put(root, 'tiles.lock', `# pinned\nARCHIVE_URL=${url}\nARCHIVE_SHA256=${sha256}\n`);
}

function fetchTiles() {
  return spawnSync('bash', [SCRIPT, root], { encoding: 'utf8' });
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'fetch-tiles-web-'));
  server = mkdtempSync(join(tmpdir(), 'fetch-tiles-server-'));
  put(root, 'public/tiles/.gitkeep', '');
  const published = put(server, 'schleswig-holstein.pmtiles', PUBLISHED);
  pin(pathToFileURL(published).href, PUBLISHED_SHA256);
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
  rmSync(server, { recursive: true, force: true });
});

describe('fetch-tiles.sh', () => {
  it('fetches the pinned archive and links the site to it', () => {
    const result = fetchTiles();

    expect(result.status, result.stderr).toBe(0);
    expect(readFileSync(join(root, `.cache/tiles/${PUBLISHED_SHA256}.pmtiles`), 'utf8')).toBe(PUBLISHED);
    expect(readlinkSync(join(root, LINK))).toBe(`../../.cache/tiles/${PUBLISHED_SHA256}.pmtiles`);
  });

  it('fetches nothing when the pinned archive is already there', () => {
    fetchTiles();
    rmSync(server, { recursive: true });

    const result = fetchTiles();

    expect(result.status, result.stderr).toBe(0);
    expect(readFileSync(join(root, LINK), 'utf8')).toBe(PUBLISHED);
  });

  it("keeps a tile builder's own archive linked, and says so", () => {
    symlinkSync('../../../tiles/data/schleswig-holstein.pmtiles', join(root, LINK));

    const result = fetchTiles();

    expect(result.status, result.stderr).toBe(0);
    expect(readlinkSync(join(root, LINK))).toBe('../../../tiles/data/schleswig-holstein.pmtiles');
    expect(result.stdout).toContain(`kept ${LINK}`);
  });

  it('moves on from an earlier pinned archive, and drops it', () => {
    const OLD = `.cache/tiles/${'0'.repeat(64)}.pmtiles`;
    put(root, OLD, 'last month\'s archive');
    symlinkSync(`../../${OLD}`, join(root, LINK));

    const result = fetchTiles();

    expect(result.status, result.stderr).toBe(0);
    expect(readlinkSync(join(root, LINK))).toBe(`../../.cache/tiles/${PUBLISHED_SHA256}.pmtiles`);
    expect(readdirSync(join(root, '.cache/tiles'))).toEqual([`${PUBLISHED_SHA256}.pmtiles`]);
  });

  it('refuses an archive that is not the pinned one', () => {
    put(server, 'schleswig-holstein.pmtiles', 'a re-uploaded archive');

    const result = fetchTiles();

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain('checksum mismatch');
    expect(readdirSync(join(root, 'public/tiles'))).toEqual(['.gitkeep']);
    expect(readdirSync(join(root, '.cache/tiles'))).toEqual([]);
  });

  it('refuses a lock that pins no archive', () => {
    pin('https://example.org/schleswig-holstein.pmtiles', '../../elsewhere');

    const result = fetchTiles();

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain('tiles.lock pins no sha256');
  });
});
