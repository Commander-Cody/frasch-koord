// @vitest-environment node
/**
 * scripts/fetch-fonts.sh, run as `npm run fetch-fonts` would run it, on a
 * temp web/ root whose fonts.lock pins a file:// URL.
 */
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), 'fetch-fonts.sh');
const STACKS = ['Noto Sans Regular', 'Noto Sans Italic', 'Noto Sans Bold'];
/** What the zip has of each stack; fonts.lock lists the first two. */
const ZIPPED = ['0-255', '256-511', '20224-20479'];
const LISTED = ['0-255.pbf', '256-511.pbf'];

/** A web/ checkout, and a directory standing in for the release server. */
let root;
let server;
let zipUrl;
let zipSha256;

function put(dir, path, text) {
  const file = join(dir, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
}

function lock({ url = zipUrl, ranges = '0-255 256-511' } = {}) {
  put(
    root,
    'fonts.lock',
    `# pinned\nFONTS_URL=${url}\nFONTS_SHA256=${zipSha256}\nSTACKS=${STACKS.join(',')}\nRANGES=${ranges}\n`,
  );
}

/** Puts these ranges of every stack into public/fonts/, as an earlier fetch left them. */
function install(ranges) {
  for (const stack of STACKS) {
    for (const range of ranges) put(root, `public/fonts/${stack}/${range}.pbf`, `old ${range}`);
  }
}

function fetchFonts() {
  return spawnSync('bash', [SCRIPT, root], { encoding: 'utf8' });
}

function installed(stack) {
  return readdirSync(join(root, 'public/fonts', stack)).sort();
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'fetch-fonts-web-'));
  server = mkdtempSync(join(tmpdir(), 'fetch-fonts-server-'));
  for (const stack of STACKS) {
    for (const range of ZIPPED) put(server, `noto-sans/${stack}/${range}.pbf`, `${stack} ${range}`);
  }
  const zip = spawnSync('zip', ['-qr', 'noto-sans.zip', 'noto-sans'], { cwd: server });
  if (zip.status !== 0) throw new Error(`zip failed: ${zip.stderr}`);
  const zipFile = join(server, 'noto-sans.zip');
  zipUrl = pathToFileURL(zipFile).href;
  zipSha256 = createHash('sha256').update(readFileSync(zipFile)).digest('hex');
  lock();
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
  rmSync(server, { recursive: true, force: true });
});

describe('fetch-fonts.sh', () => {
  it('fetches the listed ranges of each stack, and no others', () => {
    const run = fetchFonts();

    expect(run.status, run.stderr).toBe(0);
    for (const stack of STACKS) expect(installed(stack)).toEqual(LISTED);
    expect(readFileSync(join(root, 'public/fonts/Noto Sans Bold/256-511.pbf'), 'utf8')).toBe(
      'Noto Sans Bold 256-511',
    );
  });

  it('leaves an install of exactly the listed ranges alone', () => {
    install(['0-255', '256-511']);
    lock({ url: pathToFileURL(join(server, 'gone.zip')).href });

    const run = fetchFonts();

    expect(run.status, run.stderr).toBe(0);
    expect(readFileSync(join(root, 'public/fonts/Noto Sans Bold/0-255.pbf'), 'utf8')).toBe(
      'old 0-255',
    );
  });

  it('prunes an earlier, fuller install down to the listed ranges without fetching', () => {
    install(['0-255', '256-511', '20224-20479']);
    put(root, 'public/fonts/Noto Sans Medium/0-255.pbf', 'a stack nobody lists');
    lock({ url: pathToFileURL(join(server, 'gone.zip')).href });

    const run = fetchFonts();

    expect(run.status, run.stderr).toBe(0);
    expect(readdirSync(join(root, 'public/fonts')).sort()).toEqual([...STACKS].sort());
    for (const stack of STACKS) expect(installed(stack)).toEqual(LISTED);
  });

  it('repairs a partial install', () => {
    install(['0-255', '256-511']);
    rmSync(join(root, 'public/fonts/Noto Sans Italic/256-511.pbf'));

    const run = fetchFonts();

    expect(run.status, run.stderr).toBe(0);
    for (const stack of STACKS) expect(installed(stack)).toEqual(LISTED);
    expect(readFileSync(join(root, 'public/fonts/Noto Sans Italic/256-511.pbf'), 'utf8')).toBe(
      'Noto Sans Italic 256-511',
    );
  });

  it('refuses a listed range the download does not have, and leaves the fonts as they were', () => {
    install(['0-255']);
    lock({ ranges: '0-255 512-767' });

    const run = fetchFonts();

    expect(run.status).not.toBe(0);
    expect(run.stderr).toContain('512-767');
    expect(installed('Noto Sans Bold')).toEqual(['0-255.pbf']);
    expect(existsSync(join(root, 'public/fonts/Noto Sans Bold/512-767.pbf'))).toBe(false);
  });
});
