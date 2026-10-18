/**
 * A temp directory for each test, for the tests of the build checks, the dev
 * endpoints and scripts/ that work on files: a web/ checkout, a dist/, a
 * names/work/.
 */
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, beforeEach } from 'vitest';

export interface TempDir {
  /** The directory of the test that runs. */
  readonly path: string;
  /** Writes `content` to `path` inside the directory, making the folders on the way. */
  put(path: string, content: string): void;
  /** A symlink at `path` inside the directory to `target`, which need not exist. */
  link(path: string, target: string): void;
}

/**
 * A new temp directory (named `prefix` and a random suffix) before each test
 * of the calling file or `describe`, removed after it. Called before the
 * caller's own `beforeEach`, the directory is there when that one runs.
 */
export function tempDirPerTest(prefix: string): TempDir {
  let dir = '';
  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), prefix));
  });
  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });
  /** `path` inside the directory, its folder made. */
  const prepared = (path: string): string => {
    const file = join(dir, path);
    mkdirSync(dirname(file), { recursive: true });
    return file;
  };
  return {
    get path() {
      return dir;
    },
    put: (path, content) => writeFileSync(prepared(path), content),
    link: (path, target) => symlinkSync(target, prepared(path)),
  };
}
