import { readFile } from 'node:fs/promises';

/** The value of `KEY=value` in a lock file such as web/tiles.lock, or '' when it has none. */
export async function lockValue(file: string, key: string): Promise<string> {
  const lock = await readFile(file, 'utf8');
  return lock.match(new RegExp(`^${key}=(.*)$`, 'm'))?.[1] ?? '';
}
