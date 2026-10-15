// Checks the output of a build for what broke deployments before (issue
// #20), and for what must not be published. vite-plugins/build/assets.ts
// runs it once the build is written, so every build is checked, `vite build`
// as well as `npm run build`.
//
//  - The bundle points MapLibre at a worker file that dist/ really contains.
//    MapLibre's own default (`maplibre-gl-worker.mjs` next to its module) is
//    never emitted, and a request for it gets index.html, so without the
//    explicit setWorkerUrl in src/map/createMap.ts no tile is ever parsed.
//  - Every relative import between the emitted chunks resolves.
//  - The dev tools (`?curate`, `?areas`, see src/main.tsx) are not in it.
//  - Neither is the dialect-area review: its data
//    (names/dialect_areas_parts.geojson) or its research notes, which quote
//    unconfirmed assignments (names/dialect_areas.csv, docs/dialect-area-review.md).
//
// One line per problem.

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

import { AREAS_BASE, AREA_PARTS_FILE, CURATE_BASE } from '../devToolNames.ts';

/**
 * Strings only the dev tools contain: the bases of their endpoints, which
 * every one of their views fetches through. Without the slashes, which a
 * bundler may escape (`\/__curate\/`).
 */
const DEV_ONLY = [CURATE_BASE, AREAS_BASE].map((base) => base.replaceAll('/', ''));

/** The file the area review reads its geometry and notes from, under any path and extension. */
const AREA_DATA = AREA_PARTS_FILE.replace(/\.geojson$/, '');

/**
 * What only the area review's research prose says: a row's confidence and
 * its reason (`municipality; low: …`, see names/README.md), and the
 * checklist's heading.
 */
const RESEARCH_NOTES = [/; (?:medium|low): /, /Dialect-area review/];

/** Files that can carry text; the tiles and glyphs are binary. */
const TEXT = /\.(?:m?js|css|html|json|geojson|md|txt|csv)$/;

const WORKER = /^maplibre-gl-worker-[\w-]+\.m?js$/;
const SCRIPT = /\.m?js$/;

/** Text files by their path under dist/. */
type Files = Record<string, string>;

/** What checkBuild found: the problems, the number of scripts and the worker file(s). */
export interface BuildCheck {
  problems: string[];
  scripts: number;
  workers: string[];
}

/** Every file under `dist`, as a path relative to it with `/` separators. */
function listFiles(dist: string): string[] {
  return readdirSync(dist, { recursive: true, withFileTypes: true })
    .filter((entry) => !entry.isDirectory())
    .map((entry) =>
      join(entry.parentPath, entry.name)
        .slice(dist.length + 1)
        .split('\\')
        .join('/'),
    );
}

/** The worker: a hashed file under assets/, named in some other chunk, and no chunk naming one that is not there. */
function workerProblems(assets: string[], code: Files): { workers: string[]; problems: string[] } {
  const problems: string[] = [];
  const workers = assets.filter((name) => WORKER.test(name));
  if (workers.length === 0) problems.push('no maplibre-gl-worker-<hash>.js in dist/assets');
  for (const worker of workers) {
    const path = `assets/${worker}`;
    const referenced = Object.entries(code).some(([f, text]) => f !== path && text.includes(path));
    if (!referenced) problems.push(`${worker} is emitted but no chunk refers to it`);
  }
  for (const [f, text] of Object.entries(code)) {
    for (const [, name] of text.matchAll(/assets\/(maplibre-gl-worker[\w.-]*?\.m?js)/g)) {
      if (!assets.includes(name))
        problems.push(`${f} refers to assets/${name}, which dist/ does not have`);
    }
  }
  return { workers, problems };
}

/** Relative imports between chunks (`from"./x.js"`, `import("./x.js")`). */
function importProblems(dist: string, code: Files): string[] {
  const problems: string[] = [];
  for (const [f, text] of Object.entries(code)) {
    for (const [, spec] of text.matchAll(/(?:from|import)\s*\(?\s*["'`](\.\.?\/[^"'`]+)["'`]/g)) {
      if (!existsSync(resolve(dist, dirname(f), spec))) {
        problems.push(`${f} imports ${spec}, which dist/ does not have`);
      }
    }
  }
  return problems;
}

function devToolProblems(assetText: Files): string[] {
  return Object.entries(assetText).flatMap(([f, text]) =>
    DEV_ONLY.filter((needle) => text.includes(needle)).map(
      (needle) => `${f} contains "${needle}": a dev tool is in the build`,
    ),
  );
}

function areaReviewProblems(files: string[], text: Files): string[] {
  const data = files
    .filter((f) => f.includes(AREA_DATA))
    .map((f) => `${f}: the dialect-area review data is in the build`);
  const notes = Object.entries(text)
    .filter(
      ([f, content]) => !f.includes(AREA_DATA) && RESEARCH_NOTES.some((note) => note.test(content)),
    )
    .map(([f]) => `${f}: the dialect-area research notes are in the build`);
  return [...data, ...notes];
}

/**
 * The problems of the build in `dist`, and what it found: the number of
 * scripts and the worker file(s).
 */
export function checkBuild(dist: string): BuildCheck {
  if (!existsSync(join(dist, 'assets'))) {
    return {
      problems: [`no ${join(dist, 'assets')}: the build wrote no assets`],
      scripts: 0,
      workers: [],
    };
  }
  const files = listFiles(dist);
  const text: Files = Object.fromEntries(
    files.filter((f) => TEXT.test(f)).map((f) => [f, readFileSync(join(dist, f), 'utf8')]),
  );
  const assetText = Object.fromEntries(
    Object.entries(text).filter(([f]) => /^assets\/[^/]+\.(?:m?js|css)$/.test(f)),
  );
  const code = Object.fromEntries(Object.entries(assetText).filter(([f]) => SCRIPT.test(f)));
  const assets = files.filter((f) => f.startsWith('assets/')).map((f) => f.slice('assets/'.length));

  const worker = workerProblems(assets, code);
  const problems = [
    ...worker.problems,
    ...importProblems(dist, code),
    ...devToolProblems(assetText),
    ...areaReviewProblems(files, text),
  ];
  return { problems, scripts: Object.keys(code).length, workers: worker.workers };
}
