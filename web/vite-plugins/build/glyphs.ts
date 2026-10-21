/**
 * The glyphs a build ships: they have to be exactly the ranges web/fonts.lock
 * lists, and those have to cover the labels.
 *
 * Vite copies public/fonts/ into the build as it is, so what
 * `npm run fetch-assets` put there is what the site ships. And a label
 * character outside the listed ranges would be a glyph request that fails
 * (issue #29), so every string a symbol layer of the site's style can show
 * -- in any view, read off the label layers src/map/style/labels.ts builds
 * -- is taken from the pinned tile archive and checked. vite-plugins/build/
 * assets.ts runs the check when a build starts.
 */
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { StyleSpecification } from 'maplibre-gl';

import { ALL_VIEW_TAGS } from '../../src/dialects/views.ts';
import { labelLayers } from '../../src/map/style/labels.ts';
import { glyphInstall, type GlyphInstall } from './glyphInstall.ts';
import { readFontsPin } from './pins.ts';
import { vectorTiles } from './archive.ts';

/** web/, whose src/ holds the site's style, whatever root a build runs in. */
const WEB = fileURLToPath(new URL('../..', import.meta.url));

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

/**
 * The properties a text-field takes: the `{key}`s of a template, the
 * `["get", key]`s of an expression — of a `case` only those of its outputs,
 * since its conditions show nothing.
 */
function textFieldKeys(textField: unknown): string[] {
  if (typeof textField === 'string') {
    return [...textField.matchAll(/\{([^}]+)\}/g)].map(([, key]) => key);
  }
  if (!Array.isArray(textField)) return [];
  if (textField[0] === 'get' && typeof textField[1] === 'string') return [textField[1]];
  if (textField[0] === 'case') return caseOutputs(textField).flatMap(textFieldKeys);
  return textField.flatMap(textFieldKeys);
}

/** The outputs of `["case", condition, output, …, fallback]`: every other argument, and the last. */
function caseOutputs([, ...args]: unknown[]): unknown[] {
  return args.filter((_, i) => i % 2 === 1 || i === args.length - 1);
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

/** The first few of a list of files, and how many more there are. */
function few(files: string[]): string {
  const shown = files.slice(0, 3).join(', ');
  return files.length > 3 ? `${shown} and ${files.length - 3} more` : shown;
}

/** Whether public/fonts/ holds anything but the listed ranges of the listed stacks. */
function installProblem({ missing, extra }: GlyphInstall): string | undefined {
  if (missing.length === 0 && extra.length === 0) return undefined;
  const what = [
    missing.length > 0 ? `missing: ${few(missing)}` : '',
    extra.length > 0 ? `not listed: ${few(extra)}` : '',
  ].filter(Boolean);
  return `public/fonts/ does not hold the glyphs fonts.lock lists (${what.join('; ')}): run \`npm run fetch-assets\``;
}

/** Every field a symbol layer of `base` shows, in any view of the site. */
export function siteFields(base: StyleSpecification): Field[] {
  const layers = ALL_VIEW_TAGS.flatMap((view) => labelLayers(base.layers, view));
  return renderedFields({ ...base, layers });
}

/**
 * The site's own style, before a view is applied. Read from the file, not
 * imported as BASE_STYLE: src/map/style/index.ts reads `import.meta.env`
 * (through site.ts), which the Vite config has not.
 */
async function siteStyle(): Promise<StyleSpecification> {
  return JSON.parse(await readFile(join(WEB, 'src/map/style/frasch-bright.json'), 'utf8'));
}

/**
 * What stands in the way of the glyphs: public/fonts/ not holding exactly
 * the listed ranges, and labels of the pinned `archive` that need a range
 * fonts.lock does not list. The labels are checked only when the archive
 * is there (undefined when it is not fetched).
 */
export async function fontProblems(root: string, archive: string | undefined): Promise<string[]> {
  const pin = await readFontsPin(root);
  const install = installProblem(await glyphInstall(root, pin));
  const labels = archive
    ? glyphProblems(await archiveLabels(archive, siteFields(await siteStyle())), pin.ranges)
    : [];
  return [...(install === undefined ? [] : [install]), ...labels];
}
