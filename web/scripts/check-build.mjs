#!/usr/bin/env node
// Checks the output of `npm run build` for what broke deployments before
// (issue #20), and for what must not be published. Run it after a build:
// `npm run check:build`.
//
//  - The bundle points MapLibre at a worker file that dist/ really contains.
//    MapLibre's own default (`maplibre-gl-worker.mjs` next to its module) is
//    never emitted, and a request for it gets index.html, so without the
//    explicit setWorkerUrl in src/components/Map.tsx no tile is ever parsed.
//  - Every relative import between the emitted chunks resolves.
//  - The dev tools (`?curate`, `?areas`, see src/main.tsx) are not in it.
//  - Neither is the dialect-area review: its data
//    (names/dialect_areas_parts.geojson) or its research notes, which quote
//    unconfirmed assignments (names/dialect_areas.csv, docs/dialect-area-review.md).
//
// Exits non-zero with one line per problem.

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** Strings only the dev tools contain: their endpoints and the curation panel's heading. */
const DEV_ONLY = ['__curate', '__areas', 'Curation review'];

/** The file the area review reads its geometry and notes from, under any path. */
const AREA_DATA = 'dialect_areas_parts';

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

/** Every file under `dist`, as a path relative to it with `/` separators. */
function listFiles(dist) {
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
function workerProblems(assets, code) {
  const problems = [];
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
function importProblems(dist, code) {
  const problems = [];
  for (const [f, text] of Object.entries(code)) {
    for (const [, spec] of text.matchAll(/(?:from|import)\s*\(?\s*["'`](\.\.?\/[^"'`]+)["'`]/g)) {
      if (!existsSync(resolve(dist, dirname(f), spec))) {
        problems.push(`${f} imports ${spec}, which dist/ does not have`);
      }
    }
  }
  return problems;
}

function devToolProblems(assetText) {
  return Object.entries(assetText).flatMap(([f, text]) =>
    DEV_ONLY.filter((needle) => text.includes(needle)).map(
      (needle) => `${f} contains "${needle}": a dev tool is in the build`,
    ),
  );
}

function areaReviewProblems(files, text) {
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
export function checkBuild(dist) {
  if (!existsSync(join(dist, 'assets'))) {
    return {
      problems: [`no ${join(dist, 'assets')}: run \`npm run build\` first`],
      scripts: 0,
      workers: [],
    };
  }
  const files = listFiles(dist);
  const text = Object.fromEntries(
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

if (import.meta.main) {
  const dist = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
  const { problems, scripts, workers } = checkBuild(dist);
  if (problems.length > 0) {
    for (const p of problems) console.error(`check-build: ${p}`);
    process.exit(1);
  }
  console.log(`check-build: ok (${scripts} scripts, worker ${workers.join(', ')})`);
}
