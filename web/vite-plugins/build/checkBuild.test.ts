// @vitest-environment node
import { rmSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';

import { checkBuild } from './checkBuild.ts';
import { tempDirPerTest } from '../testDir.ts';

const WORKER = 'maplibre-gl-worker-Ab12.js';

/** A dist/ as `npm run build` leaves it: an entry chunk that names the worker, and the worker. */
const dist = tempDirPerTest('check-build-');

beforeEach(() => {
  dist.put('index.html', '<!doctype html><title>Frasch Maps</title>');
  dist.put('assets/index-Cd34.js', `setWorkerUrl(new URL("/assets/${WORKER}", import.meta.url));`);
  dist.put(`assets/${WORKER}`, 'self.onmessage = () => {};');
});

describe('checkBuild', () => {
  it('passes a build with the worker and nothing else', () => {
    expect(checkBuild(dist.path)).toEqual([]);
  });

  it('refuses a build without the worker', () => {
    rmSync(join(dist.path, 'assets', WORKER));
    expect(checkBuild(dist.path)).toEqual([
      'no maplibre-gl-worker-<hash>.js in dist/assets',
      `assets/index-Cd34.js refers to assets/${WORKER}, which dist/ does not have`,
    ]);
  });

  it('refuses a worker no chunk names', () => {
    dist.put(
      'assets/index-Cd34.js',
      'setWorkerUrl(new URL("/maplibre-gl-worker.mjs", import.meta.url));',
    );
    expect(checkBuild(dist.path)).toEqual([`${WORKER} is emitted but no chunk refers to it`]);
  });

  it('refuses a chunk that names a worker dist/ does not have', () => {
    dist.put('assets/other-Ij90.js', 'new Worker("/assets/maplibre-gl-worker-Stale.js")');
    expect(checkBuild(dist.path)).toEqual([
      'assets/other-Ij90.js refers to assets/maplibre-gl-worker-Stale.js, which dist/ does not have',
    ]);
  });

  it('follows an import to a chunk next to it', () => {
    dist.put('assets/app-Kl12.js', 'import{a}from"./index-Cd34.js";');
    expect(checkBuild(dist.path)).toEqual([]);
  });

  it('refuses an import of a chunk dist/ does not have', () => {
    dist.put('assets/app-Kl12.js', 'import{a}from"./vendor-Mn34.js";');
    expect(checkBuild(dist.path)).toEqual([
      'assets/app-Kl12.js imports ./vendor-Mn34.js, which dist/ does not have',
    ]);
  });

  it('refuses a dev tool in a chunk', () => {
    dist.put('assets/dev-Ef56.js', 'fetch("/__curate/worklist")');
    expect(checkBuild(dist.path)).toEqual([
      'assets/dev-Ef56.js contains "__curate": a dev tool is in the build',
    ]);
  });

  it('refuses the dialect-area data, whatever it is called', () => {
    dist.put('data/dialect_areas_parts.geojson', '{"type":"FeatureCollection","features":[]}');
    expect(checkBuild(dist.path)).toEqual([
      'data/dialect_areas_parts.geojson: the dialect-area review data is in the build',
    ]);
  });

  it('refuses the research notes of the area review inside a chunk', () => {
    dist.put(
      'assets/areas-Gh78.js',
      'const note = "municipality; low: no explicit source found, best-guess Bökingharde";',
    );
    expect(checkBuild(dist.path)).toEqual([
      'assets/areas-Gh78.js: the dialect-area research notes are in the build',
    ]);
  });

  it('refuses the review checklist', () => {
    dist.put('review.md', '# Dialect-area review checklist (issue #2)');
    expect(checkBuild(dist.path)).toEqual([
      'review.md: the dialect-area research notes are in the build',
    ]);
  });
});
