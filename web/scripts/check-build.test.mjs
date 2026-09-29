// @vitest-environment node
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { checkBuild } from './check-build.mjs';

const WORKER = 'maplibre-gl-worker-Ab12.js';

/** A dist/ as `npm run build` leaves it: an entry chunk that names the worker, and the worker. */
let dist;

function put(path, text) {
  const file = join(dist, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
}

beforeEach(() => {
  dist = mkdtempSync(join(tmpdir(), 'check-build-'));
  put('index.html', '<!doctype html><title>Frasch Maps</title>');
  put('assets/index-Cd34.js', `setWorkerUrl(new URL("/assets/${WORKER}", import.meta.url));`);
  put(`assets/${WORKER}`, 'self.onmessage = () => {};');
});

afterEach(() => {
  rmSync(dist, { recursive: true, force: true });
});

describe('checkBuild', () => {
  it('passes a build with the worker and nothing else', () => {
    expect(checkBuild(dist).problems).toEqual([]);
  });

  it('refuses a build without the worker', () => {
    rmSync(join(dist, 'assets', WORKER));
    expect(checkBuild(dist).problems).toEqual([
      'no maplibre-gl-worker-<hash>.js in dist/assets',
      `assets/index-Cd34.js refers to assets/${WORKER}, which dist/ does not have`,
    ]);
  });

  it('refuses a worker no chunk names', () => {
    put('assets/index-Cd34.js', 'setWorkerUrl(new URL("/maplibre-gl-worker.mjs", import.meta.url));');
    expect(checkBuild(dist).problems).toEqual([`${WORKER} is emitted but no chunk refers to it`]);
  });

  it('refuses a chunk that names a worker dist/ does not have', () => {
    put('assets/other-Ij90.js', 'new Worker("/assets/maplibre-gl-worker-Stale.js")');
    expect(checkBuild(dist).problems).toEqual([
      'assets/other-Ij90.js refers to assets/maplibre-gl-worker-Stale.js, which dist/ does not have',
    ]);
  });

  it('follows an import to a chunk next to it', () => {
    put('assets/app-Kl12.js', 'import{a}from"./index-Cd34.js";');
    expect(checkBuild(dist).problems).toEqual([]);
  });

  it('refuses an import of a chunk dist/ does not have', () => {
    put('assets/app-Kl12.js', 'import{a}from"./vendor-Mn34.js";');
    expect(checkBuild(dist).problems).toEqual([
      'assets/app-Kl12.js imports ./vendor-Mn34.js, which dist/ does not have',
    ]);
  });

  it('refuses a dev tool in a chunk', () => {
    put('assets/dev-Ef56.js', 'fetch("/__curate/worklist")');
    expect(checkBuild(dist).problems).toEqual(['assets/dev-Ef56.js contains "__curate": a dev tool is in the build']);
  });

  it('refuses the dialect-area data, whatever it is called', () => {
    put('data/dialect_areas_parts.geojson', '{"type":"FeatureCollection","features":[]}');
    expect(checkBuild(dist).problems).toEqual([
      'data/dialect_areas_parts.geojson: the dialect-area review data is in the build',
    ]);
  });

  it('refuses the research notes of the area review inside a chunk', () => {
    put('assets/areas-Gh78.js', 'const note = "municipality; low: no explicit source found, best-guess Bökingharde";');
    expect(checkBuild(dist).problems).toEqual([
      'assets/areas-Gh78.js: the dialect-area research notes are in the build',
    ]);
  });

  it('refuses the review checklist', () => {
    put('review.md', '# Dialect-area review checklist (issue #2)');
    expect(checkBuild(dist).problems).toEqual(['review.md: the dialect-area research notes are in the build']);
  });
});
