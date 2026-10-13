import { describe, expect, it } from 'vitest';

import type { CardEntry } from './entry';
import { resolveName } from './resolveName';

/** A minimal, otherwise-empty entry, for tests that only care about a few fields. */
function entry(fields: Partial<CardEntry> = {}): CardEntry {
  return { id: '', names: {}, name_de: '', lon: 0, lat: 0, kind: '', ...fields };
}

describe('resolveName', () => {
  it("prefers the dialect's own name over frasch:local", () => {
    const e = entry({ names: { 'frr-x-mooring': 'Naibel' }, local: 'Naibel Local' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Naibel', source: 'frr-x-mooring' });
  });

  it('falls back to frasch:local when the dialect has no name of its own', () => {
    const e = entry({ local: 'Wik' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Wik', source: 'local' });
  });

  it("falls back to another dialect's name, reporting that dialect as the source", () => {
    const e = entry({ names: { 'frr-x-fering': 'Feering Name' } });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({
      name: 'Feering Name',
      source: 'frr-x-fering',
    });
  });

  it('reports name:frr as source "frr"', () => {
    const e = entry({ name_frr: 'Rüms' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Rüms', source: 'frr' });
  });

  it('reports name:nds as source "nds"', () => {
    const e = entry({ name_nds: 'Niböl' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Niböl', source: 'nds' });
  });

  it('reports the German name as source "de"', () => {
    const e = entry({ name_de: 'Niebüll' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Niebüll', source: 'de' });
  });

  it("reports OSM's generic name as Danish where it is the Danish name", () => {
    const e = entry({ name_osm: 'Ribe', name_da: 'Ribe', name_de: 'Ripen' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Ribe', source: 'da' });
  });

  it("reports OSM's generic name as German where it is the German name", () => {
    const e = entry({ name_osm: 'Niebüll', name_de: 'Niebüll' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Niebüll', source: 'de' });
  });

  it('reports OSM\'s generic name as source "osm" where it is no name the entry knows a language of', () => {
    const e = entry({ name_osm: 'Tønder', name_de: 'Tondern' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Tønder', source: 'osm' });
  });

  it('falls back to Danish only as a last resort, after German has had its turn', () => {
    const e = entry({ name_da: 'Ålborg' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Ålborg', source: 'da' });
  });

  it('resolves to an empty name when the entry has nothing at all', () => {
    expect(resolveName(entry(), 'frr-x-mooring')).toEqual({ name: '', source: 'de' });
  });

  it('the local view never shows name:frr, only frasch:local then Low Saxon then German', () => {
    // name_frr is deliberately ignored by the local view (see labelChain.ts);
    // Low Saxon still wins over OSM's generic name and the German one.
    const e = entry({ name_frr: 'Rüms', name_nds: 'Sölerloch', name_osm: 'Sylt', name_de: 'Sylt' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Sölerloch', source: 'nds' });
  });

  it("the local view prefers OSM's generic name over the German one", () => {
    const e = entry({ name_osm: 'Tønder', name_de: 'Tondern' });
    expect(resolveName(e, 'frr-x-local').name).toBe('Tønder');
  });

  it('the local view falls back to German where there is no generic name', () => {
    expect(resolveName(entry({ name_de: 'Tondern' }), 'frr-x-local')).toEqual({
      name: 'Tondern',
      source: 'de',
    });
  });
});
