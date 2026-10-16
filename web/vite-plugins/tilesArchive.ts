/**
 * Hands the site the name of the tile archive web/tiles.lock pins, as
 * `import.meta.env.TILES_ARCHIVE` (read by src/site.ts): the site serves it
 * as tiles/<name>, under the name it was published by. In the dev server
 * and in a build alike.
 */
import { resolve } from 'node:path';
import type { Plugin } from 'vite';

import { readTilesPin } from './build/pins.ts';

export default function tilesArchive(): Plugin {
  return {
    name: 'frasch-tiles-archive',
    async config({ root }) {
      const { name } = await readTilesPin(resolve(root ?? process.cwd()));
      return { define: { 'import.meta.env.TILES_ARCHIVE': JSON.stringify(name) } };
    },
  };
}
