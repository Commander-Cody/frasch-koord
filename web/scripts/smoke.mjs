#!/usr/bin/env node
// Smoke check of the production build: serves dist/ with `vite preview`,
// opens it in headless Chromium and checks that the map loads, search finds a
// place and its card opens, and that the dev tools stay off. Run after a
// build: `npm run smoke`. Needs the PMTiles archive in public/tiles/ at build
// time (or VITE_TILES_URL) and the glyphs in public/fonts/, see README.md.
//
// Browser: Playwright's headless Chromium (`npx playwright install
// chromium-headless-shell` once).

import { chromium } from 'playwright';
import { preview } from 'vite';

/** Niebüll and around: the name list is densest here. */
const VIEW = '#11/54.79/8.83';
const SEARCH = 'Naibel';
const TIMEOUT = 60_000;

const server = await preview({ preview: { port: 4173, strictPort: false, open: false } });
const url = server.resolvedUrls?.local[0];
if (!url) throw new Error('vite preview reports no URL');

const problems = [];
let browser;

try {
  // Software WebGL: headless has no GPU, and Chromium only falls back to
  // SwiftShader for WebGL when told to.
  browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] });
  const page = await browser.newPage();
  page.on('pageerror', (err) => problems.push(`page error: ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`console error: ${msg.text()}`);
  });
  page.on('response', (res) => {
    const path = new URL(res.url()).pathname;
    if (res.status() >= 400) problems.push(`HTTP ${res.status()} for ${path}`);
    // The failure this check exists for: a script request answered with the
    // SPA's index.html. (A reload revalidated from cache has no content-type.)
    if (/\.m?js$/.test(path) && /html/.test(res.headers()['content-type'] ?? '')) {
      problems.push(`${path} is served as HTML, not JavaScript`);
    }
  });

  await page.goto(`${url}${VIEW}`);
  // Map.tsx sets data-state once MapLibre fires `load`: style, tiles, glyphs
  // and sprites fetched, tiles parsed by the worker, first frame drawn.
  await page.waitForSelector('.map-container[data-state="loaded"]', { timeout: TIMEOUT });
  if (await page.locator('.map-error').count()) problems.push('the map shows its error banner');

  // Search needs names.json; the card needs a result.
  await page.fill('.search-input', SEARCH);
  await page.locator('.search-results button').first().click({ timeout: TIMEOUT });
  await page.waitForSelector('.place-card', { timeout: TIMEOUT });
  if (await page.locator('.search-error').count()) problems.push('search shows its load error');

  // The dev tools are not in the build: `?curate` is the public map.
  await page.goto(`${url}?curate${VIEW}`);
  await page.waitForSelector('.search-input', { timeout: TIMEOUT });
  if (await page.locator('.curate-panel, .area-panel').count()) problems.push('?curate opens a dev tool');
} catch (err) {
  problems.push(String(err));
} finally {
  await browser?.close();
  await server.close();
}

if (problems.length > 0) {
  for (const p of problems) console.error(`smoke: ${p}`);
  process.exit(1);
}
console.log('smoke: ok (map loaded, search and card work, no dev tools)');
