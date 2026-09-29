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
