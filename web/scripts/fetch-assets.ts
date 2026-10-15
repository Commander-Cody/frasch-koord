/**
 * `npm run fetch-assets`: puts what the locks pin where the dev server and
 * the build look for it. Neither is in git.
 *
 *  - The tile archive web/tiles.lock pins (~125 MB) goes into
 *    .cache/tiles/<sha256>.pmtiles, and public/tiles/schleswig-holstein.pmtiles
 *    is linked to it for the dev server. The build takes it from the cache
 *    (vite-plugins/build/tiles.ts).
 *  - The glyph ranges web/fonts.lock lists (~2.6 MB), and nothing else, go
 *    into public/fonts/, which Vite ships as it is: when one is missing, they
 *    are taken from the zip fonts.lock pins; when all are there, whatever
 *    else is there (an earlier, fuller fetch) is deleted.
 *
 * Each download is checked against its sha256 before it is put in place,
 * and nothing is downloaded that is already there.
 *
 * Usage: node scripts/fetch-assets.ts
 */
import { createHash } from 'node:crypto';
import { createWriteStream } from 'node:fs';
import {
  access,
  mkdir,
  readdir,
  readFile,
  readlink,
  rename,
  rm,
  rmdir,
  symlink,
  writeFile,
} from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { unzipSync } from 'fflate';

import {
  ARCHIVE_NAME,
  type FontsPin,
  readFontsPin,
  readTilesPin,
  TILE_CACHE_DIR,
} from '../vite-plugins/build/pins.ts';
import { sha256Of } from '../vite-plugins/build/sha256.ts';
import { FONTS_DIR, glyphInstall } from '../vite-plugins/build/glyphInstall.ts';
import { danglingLinkProblems } from '../vite-plugins/build/tiles.ts';

/** Where the fetch says what it did (`info`) and what needs a hand (`warn`). */
export interface Report {
  info(line: string): void;
  warn(line: string): void;
}

/** The dev server's archive, under the web/ root. */
const LINK = `public/tiles/${ARCHIVE_NAME}`;

/** Where the glyphs are put together before they replace public/fonts/, under the web/ root. */
const FONTS_PART = '.cache/fonts.part';

/**
 * Downloads `url` to `dest`, by way of a `.part` file that only becomes
 * `dest` once its sha256 is the expected one.
 */
async function fetchVerified(url: string, dest: string, sha256: string): Promise<void> {
  const part = `${dest}.part`;
  await mkdir(dirname(dest), { recursive: true });
  try {
    const actual = await download(url, part);
    if (actual !== sha256) {
      throw new Error(`checksum mismatch for ${url}: expected ${sha256}, got ${actual}`);
    }
  } catch (err) {
    await rm(part, { force: true });
    throw err;
  }
  await rename(part, dest);
}

/** Downloads `url` to `file`; returns the sha256 of what it got. */
async function download(url: string, file: string): Promise<string> {
  const response = await fetch(url).catch((err: Error) => {
    throw new Error(
      `download failed: ${url} (${(err.cause as Error | undefined)?.message ?? err.message})`,
    );
  });
  if (!response.ok || !response.body) {
    throw new Error(`download failed: ${url} (HTTP ${response.status})`);
  }
  const hash = createHash('sha256');
  const body = Readable.fromWeb(response.body);
  body.on('data', (chunk: Buffer) => hash.update(chunk));
  await pipeline(body, createWriteStream(file));
  return hash.digest('hex');
}

/** Like fetchVerified, but keeps what is already at `dest` when it matches. */
async function fetchPinned(url: string, dest: string, sha256: string): Promise<void> {
  if ((await sha256Of(dest)) === sha256) return;
  await fetchVerified(url, dest, sha256);
}

/**
 * Where the dev server's archive link leads: undefined when there is none,
 * `a file` when it is a file of its own.
 */
async function linkTarget(path: string): Promise<string | undefined> {
  try {
    return await readlink(path);
  } catch (err) {
    const { code } = err as NodeJS.ErrnoException;
    if (code === 'ENOENT') return undefined;
    if (code === 'EINVAL') return 'a file';
    throw err;
  }
}

/** Whether the path leads to a file, its links followed. */
async function reachable(path: string): Promise<boolean> {
  return access(path).then(
    () => true,
    () => false,
  );
}

/**
 * Links public/tiles/ to the fetched archive when the link there is ours to
 * (re)point: no archive there yet, or a link to an earlier fetch. Anything
 * else is someone's own archive, e.g. a link to tiles/data/, and is kept;
 * one that leads nowhere is danglingLinkProblems' to warn about.
 */
async function linkForDevServer(root: string, cachePath: string, report: Report): Promise<void> {
  const link = join(root, LINK);
  const target = await linkTarget(link);
  if (target === undefined || target.startsWith(`../../${TILE_CACHE_DIR}/`)) {
    await rm(link, { force: true });
    await symlink(`../../${cachePath}`, link);
  } else if (await reachable(link)) {
    report.info(
      `kept ${LINK} (-> ${target}): the dev server serves that, a build the fetched archive`,
    );
  }
}

/** Drops the archives of earlier pins: ~125 MB each, and nothing uses them any more. */
async function pruneEarlierArchives(root: string, cachePath: string): Promise<void> {
  const cache = join(root, TILE_CACHE_DIR);
  const pinned = basename(cachePath);
  const earlier = (await readdir(cache)).filter((f) => f.endsWith('.pmtiles') && f !== pinned);
  await Promise.all(earlier.map((f) => rm(join(cache, f))));
}

/** Fetches the archive tiles.lock pins into the cache and links public/tiles/ to it. */
export async function fetchTiles(root: string, report: Report): Promise<void> {
  const pin = await readTilesPin(root);
  await fetchPinned(pin.url, join(root, pin.cachePath), pin.sha256);
  await linkForDevServer(root, pin.cachePath, report);
  // Someone's own link to an archive that is not built yet: theirs to keep.
  for (const problem of await danglingLinkProblems(root)) report.warn(problem);
  await pruneEarlierArchives(root, pin.cachePath);
  report.info(`tile archive: ${pin.cachePath} (pinned in tiles.lock)`);
}

/** The zip fonts.lock pins, downloaded and checked. */
async function downloadFontsZip(root: string, pin: FontsPin): Promise<Uint8Array> {
  const zip = join(root, '.cache/fonts.zip');
  await fetchVerified(pin.url, zip, pin.sha256);
  try {
    return await readFile(zip);
  } finally {
    await rm(zip);
  }
}

/** The listed files out of the zip, found under any directory of it, by `<stack>/<range>.pbf`. */
function unzipListed(zip: Uint8Array, pin: FontsPin): Map<string, Uint8Array> {
  const listed = new Set(pin.listedFiles);
  const found = new Map<string, Uint8Array>();
  const entries = unzipSync(zip, { filter: ({ name }) => listed.has(stackFile(name)) });
  for (const [name, data] of Object.entries(entries)) found.set(stackFile(name), data);
  const lacking = pin.listedFiles.find((file) => !found.has(file));
  if (lacking !== undefined) {
    const [stack, range] = lacking.replace(/\.pbf$/, '').split('/');
    throw new Error(`${pin.url} has no range ${range} of ${stack}`);
  }
  return found;
}

/** The last two parts of a path in the zip: `<stack>/<range>.pbf` for a glyph file. */
function stackFile(name: string): string {
  return name.split('/').slice(-2).join('/');
}

/** Deletes these files under public/fonts/, and the directories that leaves empty. */
async function pruneUnlisted(root: string, files: string[]): Promise<void> {
  const fonts = join(root, FONTS_DIR);
  await Promise.all(files.map((file) => rm(join(fonts, file))));
  const dirs = (await readdir(fonts, { recursive: true, withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .map((entry) => join(entry.parentPath, entry.name))
    .sort((a, b) => b.length - a.length);
  for (const dir of dirs) {
    if ((await readdir(dir)).length === 0) await rmdir(dir);
  }
}

/** Makes public/fonts/ hold these files and nothing else, put together beside it first. */
async function replaceFonts(root: string, glyphs: Map<string, Uint8Array>): Promise<void> {
  const part = join(root, FONTS_PART);
  await rm(part, { recursive: true, force: true });
  for (const [file, data] of glyphs) {
    await mkdir(dirname(join(part, file)), { recursive: true });
    await writeFile(join(part, file), data);
  }
  const fonts = join(root, FONTS_DIR);
  await rm(fonts, { recursive: true, force: true });
  await mkdir(dirname(fonts), { recursive: true });
  await rename(part, fonts);
}

/** Puts the listed glyph ranges, and nothing else, into public/fonts/. */
export async function fetchFonts(root: string, report: Report): Promise<void> {
  const pin = await readFontsPin(root);
  const { missing, extra } = await glyphInstall(root, pin);
  if (missing.length === 0) {
    await pruneUnlisted(root, extra);
    report.info(
      extra.length > 0
        ? `removed ${extra.length} glyph files fonts.lock does not list`
        : 'glyphs already present',
    );
    return;
  }
  const glyphs = unzipListed(await downloadFontsZip(root, pin), pin);
  await replaceFonts(root, glyphs);
  report.info(`glyphs: ${glyphs.size} files in ${FONTS_DIR}/ (listed in fonts.lock)`);
}

if (import.meta.main) {
  const root = fileURLToPath(new URL('..', import.meta.url));
  const report: Report = {
    info: console.log,
    warn: (line) => console.warn(`fetch-assets: ${line}`),
  };
  try {
    await fetchFonts(root, report);
    await fetchTiles(root, report);
  } catch (err) {
    console.error(`fetch-assets: ${(err as Error).message}`);
    process.exit(1);
  }
}
