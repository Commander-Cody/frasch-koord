/**
 * What public/fonts/ holds against what fonts.lock lists: the one rule that
 * `npm run fetch-assets` makes true and the build checks. Vite ships
 * public/fonts/ as it is, so it has to hold exactly the listed files.
 */
import { readdir } from 'node:fs/promises';
import { join, relative } from 'node:path';

import type { FontsPin } from './pins.ts';

/** Where the site's glyphs are, under the web/ root. */
export const FONTS_DIR = 'public/fonts';

/** The listed files public/fonts/ lacks, and the files it has that are not listed. */
export interface GlyphInstall {
  missing: string[];
  extra: string[];
}

/** The files under public/fonts/, as `<stack>/<range>.pbf`. */
async function installedGlyphs(root: string): Promise<string[]> {
  const fonts = join(root, FONTS_DIR);
  const entries = await readdir(fonts, { recursive: true, withFileTypes: true }).catch(() => []);
  return entries
    .filter((entry) => !entry.isDirectory())
    .map((entry) => relative(fonts, join(entry.parentPath, entry.name)).split('\\').join('/'))
    .sort();
}

export async function glyphInstall(root: string, { listedFiles }: FontsPin): Promise<GlyphInstall> {
  const installed = await installedGlyphs(root);
  return {
    missing: listedFiles.filter((file) => !installed.includes(file)),
    extra: installed.filter((file) => !listedFiles.includes(file)),
  };
}
