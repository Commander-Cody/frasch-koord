#!/usr/bin/env node
// Checks the output of `npm run build` for what broke deployments before
// (issue #20). Run it after a build: `npm run check:build`.
//
//  - The bundle points MapLibre at a worker file that dist/ really contains.
//    MapLibre's own default (`maplibre-gl-worker.mjs` next to its module) is
//    never emitted, and a request for it gets index.html, so without the
//    explicit setWorkerUrl in src/components/Map.tsx no tile is ever parsed.
//  - Every relative import between the emitted chunks resolves.
//  - The dev tools (`?curate`, `?areas`, see src/main.tsx) are not in it.
//
// Exits non-zero with one line per problem.

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
const assets = join(dist, 'assets');

/** Strings only the dev tools contain: their endpoints and the curation panel's heading. */
const DEV_ONLY = ['__curate', '__areas', 'Curation review'];

const problems = [];

if (!existsSync(assets)) {
  console.error(`No ${assets}: run \`npm run build\` first.`);
  process.exit(1);
}

const files = readdirSync(assets);
const code = Object.fromEntries(
  files.filter((f) => /\.(m?js|css)$/.test(f)).map((f) => [f, readFileSync(join(assets, f), 'utf8')]),
);
const scripts = Object.keys(code).filter((f) => /\.m?js$/.test(f));

// The worker: a hashed file under assets/, named in some other chunk.
const workers = files.filter((f) => /^maplibre-gl-worker-[\w-]+\.m?js$/.test(f));
if (workers.length === 0) {
  problems.push('no maplibre-gl-worker-<hash>.js in dist/assets');
}
for (const worker of workers) {
  const referenced = scripts.some((f) => f !== worker && code[f].includes(`assets/${worker}`));
  if (!referenced) problems.push(`${worker} is emitted but no chunk refers to it`);
}
// And no chunk refers to a worker that is not there (a stale hash, a file
// named in the bundle but never copied).
for (const f of scripts) {
  for (const [, name] of code[f].matchAll(/assets\/(maplibre-gl-worker[\w.-]*?\.m?js)/g)) {
    if (!files.includes(name)) problems.push(`${f} refers to assets/${name}, which dist/ does not have`);
  }
}

// Relative imports between chunks (`from"./x.js"`, `import("./x.js")`).
for (const f of scripts) {
  for (const [, spec] of code[f].matchAll(/(?:from|import)\s*\(?\s*["'`](\.\.?\/[^"'`]+)["'`]/g)) {
    if (!existsSync(resolve(assets, spec))) problems.push(`${f} imports ${spec}, which dist/ does not have`);
  }
}

for (const [f, text] of Object.entries(code)) {
  for (const needle of DEV_ONLY) {
    if (text.includes(needle)) problems.push(`${f} contains "${needle}": a dev tool is in the build`);
  }
}

if (problems.length > 0) {
  for (const p of problems) console.error(`check-build: ${p}`);
  process.exit(1);
}
console.log(`check-build: ok (${scripts.length} scripts, worker ${workers.join(', ')})`);
