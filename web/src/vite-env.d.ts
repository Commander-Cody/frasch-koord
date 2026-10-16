/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_TILES_URL?: string;
  /** The file name of the tile archive tiles.lock pins (vite-plugins/tilesArchive.ts). */
  readonly TILES_ARCHIVE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
