/** What the build and `npm run fetch-assets` ask of a file on disk. */
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { pipeline } from 'node:stream/promises';

/** The file's sha256, or undefined when there is no such file. */
export async function sha256Of(file: string): Promise<string | undefined> {
  const hash = createHash('sha256');
  try {
    await pipeline(createReadStream(file), hash);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return undefined;
    throw err;
  }
  return hash.digest('hex');
}

/** Whether the path leads to a file, its links followed. */
export async function exists(path: string): Promise<boolean> {
  try {
    await stat(path);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return false;
    throw err;
  }
  return true;
}
