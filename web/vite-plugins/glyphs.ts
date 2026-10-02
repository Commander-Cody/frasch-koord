/**
 * Stops a build whose glyphs are not the ranges web/fonts.lock lists, or
 * whose labels need a range it does not list.
 *
 * Vite copies public/fonts/ into the build as it is, so what
 * scripts/fetch-fonts.sh put there is what the site ships: it has to be
 * exactly the listed ranges of the listed stacks. And a label character
 * outside them would be a glyph request that fails (issue #29), so every
 * string a symbol layer of the site's style can show -- in any view, read
 * off the style that src/style/localize.ts builds -- is taken from the
 * pinned tile archive and checked. With VITE_TILES_URL the build needs no
 * archive; then the fetched one is checked if there is one, else the build
 * warns that it checked no labels.
 *
 * Build only (`apply: 'build'`); the dev server reads public/ in place.
 */
import { access, readdir, readFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { StyleSpecification } from 'maplibre-gl';
import { type Plugin, runnerImport } from 'vite';

import { lockValue } from './lock.ts';
import { pinnedArchive } from './tiles.ts';
import { vectorTiles } from './vectorTiles.ts';

/** web/, whose src/ the site's style is built from, whatever root a build runs in. */
const WEB = fileURLToPath(new URL('..', import.meta.url));

/** A tile property a symbol layer shows: `key` of the features of `sourceLayer`. */
export interface Field {
  sourceLayer: string;
  key: string;
  uppercase: boolean;
}

/** A string a symbol layer can show, and whether the layer shows it in capitals. */
export interface Label {
  text: string;
  uppercase: boolean;
}

/** The glyph file a code point is in, e.g. `256-511` for ā. */
function rangeOf(codePoint: number): string {
  const start = Math.floor(codePoint / 256) * 256;
  return `${start}-${start + 255}`;
}

function codePointName(char: string): string {
  return `U+${char.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}`;
}

/**
 * One line per glyph range the labels need and `ranges` lacks, naming a
 * character that needs it and a label (as shown) that has the character.
 */
export function glyphProblems(labels: Iterable<Label>, ranges: readonly string[]): string[] {
  const shipped = new Set(ranges);
  const problems = new Map<string, string>();
  for (const { text, uppercase } of labels) {
    const shown = uppercase ? text.toUpperCase() : text;
    for (const char of shown) {
      const range = rangeOf(char.codePointAt(0)!);
      if (shipped.has(range) || problems.has(range)) continue;
      problems.set(
        range,
        `"${char}" (${codePointName(char)}) in "${shown}" needs the glyph range ${range}, which fonts.lock does not list`,
      );
    }
  }
  return [...problems.values()];
}

/** The properties a text-field takes: the `{key}`s of a template, the `["get", key]`s of an expression. */
function textFieldKeys(textField: unknown): string[] {
  if (typeof textField === 'string') {
    return [...textField.matchAll(/\{([^}]+)\}/g)].map(([, key]) => key);
  }
  if (!Array.isArray(textField)) return [];
  if (textField[0] === 'get' && typeof textField[1] === 'string') return [textField[1]];
  return textField.flatMap(textFieldKeys);
}

/** Every tile property a symbol layer of `style` can show, each once. */
export function renderedFields(style: StyleSpecification): Field[] {
  const fields = new Map<string, Field>();
  for (const layer of style.layers) {
    if (layer.type !== 'symbol' || !layer.layout) continue;
    const uppercase = layer.layout['text-transform'] === 'uppercase';
    for (const key of textFieldKeys(layer.layout['text-field'])) {
      const field = { sourceLayer: layer['source-layer'] ?? '', key, uppercase };
      fields.set(JSON.stringify(field), field);
    }
  }
  return [...fields.values()];
}

/** The labels `fields` take from the features of every tile of the archive, each once. */
export async function archiveLabels(path: string, fields: readonly Field[]): Promise<Label[]> {
  const labels = new Map<string, Label>();
  for await (const tile of vectorTiles(path)) {
    for (const [sourceLayer, layer] of Object.entries(tile.layers)) {
      const shown = fields.filter((f) => f.sourceLayer === sourceLayer);
      for (let i = 0; shown.length > 0 && i < layer.length; i++) {
        const { properties } = layer.feature(i);
        for (const { key, uppercase } of shown) {
          const text = properties[key];
          if (typeof text === 'string') labels.set(`${uppercase} ${text}`, { text, uppercase });
        }
      }
    }
  }
  return [...labels.values()];
}

/** What web/fonts.lock asks for: these ranges of each of these stacks. */
interface FontsLock {
  stacks: string[];
  ranges: string[];
}

async function readFontsLock(root: string): Promise<FontsLock> {
  const file = join(root, 'fonts.lock');
  return {
    stacks: (await lockValue(file, 'STACKS')).split(',').filter(Boolean),
    ranges: (await lockValue(file, 'RANGES')).split(/\s+/).filter(Boolean),
  };
}

/** The files under public/fonts/, as `<stack>/<range>.pbf`. */
async function installedGlyphs(root: string): Promise<string[]> {
  const fonts = join(root, 'public/fonts');
  const entries = await readdir(fonts, { recursive: true, withFileTypes: true }).catch(() => []);
  return entries
    .filter((entry) => !entry.isDirectory())
    .map((entry) => relative(fonts, join(entry.parentPath, entry.name)).split('\\').join('/'))
    .sort();
}

/** The first few of a list of files, and how many more there are. */
function few(files: string[]): string {
  const shown = files.slice(0, 3).join(', ');
  return files.length > 3 ? `${shown} and ${files.length - 3} more` : shown;
}

/** Whether public/fonts/ holds anything but the listed ranges of the listed stacks. */
function installProblem({ stacks, ranges }: FontsLock, installed: string[]): string | undefined {
  const listed = stacks.flatMap((stack) => ranges.map((range) => `${stack}/${range}.pbf`));
  const missing = listed.filter((file) => !installed.includes(file));
  const extra = installed.filter((file) => !listed.includes(file));
  if (missing.length === 0 && extra.length === 0) return undefined;
  const what = [
    missing.length > 0 ? `missing: ${few(missing)}` : '',
    extra.length > 0 ? `not listed: ${few(extra)}` : '',
  ].filter(Boolean);
  return `public/fonts/ does not hold the glyphs fonts.lock lists (${what.join('; ')}): run \`npm run fetch-assets\``;
}

/** What the plugin needs of src/config.ts and src/style/localize.ts. */
interface SiteModules {
  config: { DIALECTS: { tag: string }[]; LOCAL_TAG: string };
  localize: {
    buildStyle(base: StyleSpecification, tilesUrl: string, view: string): StyleSpecification;
  };
}

/**
 * Loads a module of the site through Vite, as a build would: they read
 * `import.meta.env`, which a plain import in a Vite config does not have.
 */
async function siteModule<T>(path: string): Promise<T> {
  const options = { configFile: false as const, root: WEB, logLevel: 'silent' as const };
  return (await runnerImport<T>(join(WEB, path), options)).module;
}

/** Every field a symbol layer of the site's style shows, in any of its views. */
async function siteFields(): Promise<Field[]> {
  const config = await siteModule<SiteModules['config']>('src/config.ts');
  const localize = await siteModule<SiteModules['localize']>('src/style/localize.ts');
  const base = JSON.parse(await readFile(join(WEB, 'src/style/frasch-bright.json'), 'utf8'));
  const views = [config.LOCAL_TAG, ...config.DIALECTS.map((d) => d.tag)];
  const layers = views.flatMap((view) => localize.buildStyle(base, '', view).layers);
  return renderedFields({ ...base, layers });
}

/**
 * The labels of the pinned archive that need a range `ranges` lacks; none
 * when the archive is not fetched (the tiles plugin stops such a build, or
 * with VITE_TILES_URL `warn` says that nothing was checked).
 */
async function labelProblems(
  root: string,
  ranges: string[],
  { external, warn }: { external: boolean; warn(message: string): void },
): Promise<string[]> {
  const archive = await pinnedArchive(root);
  const fetched = await access(archive).then(
    () => true,
    () => false,
  );
  if (!fetched) {
    if (external) {
      warn(
        'the pinned tile archive is not fetched, so the labels were not checked against the glyph ranges fonts.lock lists (`npm run fetch-tiles` fetches it)',
      );
    }
    return [];
  }
  return glyphProblems(await archiveLabels(archive, await siteFields()), ranges);
}

export default function glyphs(): Plugin {
  let root: string;
  let external: boolean;
  return {
    name: 'frasch-glyphs',
    apply: 'build',
    configResolved(config) {
      root = config.root;
      external = Boolean(config.env.VITE_TILES_URL);
    },
    async buildStart() {
      const lock = await readFontsLock(root);
      const problems = [
        installProblem(lock, await installedGlyphs(root)),
        ...(await labelProblems(root, lock.ranges, { external, warn: (m) => this.warn(m) })),
      ].filter((p) => p !== undefined);
      if (problems.length > 0) this.error(problems.join('\n'));
    },
  };
}
