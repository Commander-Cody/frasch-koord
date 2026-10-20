import { describe, expect, it } from 'vitest';

import type { CardNames } from './entry';
import { resolveName, type NameSource } from './resolveName';

/** The names of a place that has only those of `fields`. */
function entry(fields: Partial<CardNames> = {}): CardNames {
  return { names: {}, ...fields };
}

const LOCAL: NameSource = { kind: 'local' };
const FRISIAN: NameSource = { kind: 'language', language: 'frr' };
const LOW_SAXON: NameSource = { kind: 'dialect', tag: 'nds' };
const GERMAN: NameSource = { kind: 'language', language: 'de' };
const DANISH: NameSource = { kind: 'language', language: 'da' };
const UNKNOWN: NameSource = { kind: 'unknown' };

describe('resolveName', () => {
  it("prefers the dialect's own name over frasch:local", () => {
    const e = entry({ names: { 'frr-x-mooring': 'Naibel' }, local: 'Naibel Local' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({
      name: 'Naibel',
      source: { kind: 'dialect', tag: 'frr-x-mooring' },
    });
  });

  it('falls back to frasch:local when the dialect has no name of its own', () => {
    const e = entry({ local: 'Wik' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Wik', source: LOCAL });
  });

  it("falls back to another dialect's name, reporting that dialect as the source", () => {
    const e = entry({ names: { 'frr-x-fering': 'Feering Name' } });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({
      name: 'Feering Name',
      source: { kind: 'dialect', tag: 'frr-x-fering' },
    });
  });

  it('reports name:frr as Frisian of no dialect', () => {
    const e = entry({ name_frr: 'Rüms' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Rüms', source: FRISIAN });
  });

  it('reports name:nds as the Low Saxon of the registry', () => {
    const e = entry({ names: { nds: 'Niböl' } });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Niböl', source: LOW_SAXON });
  });

  it('prefers the local name of a place in a Frisian area over the other dialects', () => {
    const e = entry({ local: 'Wik', dialect: 'frr-x-fering', names: { 'frr-x-solring': 'Wyk' } });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Wik', source: LOCAL });
  });

  it('prefers Frisian of no dialect over the local name of a place in a Synnejysk area', () => {
    const e = entry({ local: 'Lym', dialect: 'jut', names: { jut: 'Lym' }, name_frr: 'Läigem' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Läigem', source: FRISIAN });
  });

  it('never names a place by its Synnejysk name as such in a Frisian view', () => {
    const e = entry({ names: { jut: 'Lym' }, name_de: 'Süderlügum' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Süderlügum', source: GERMAN });
  });

  it('reports the German name as German', () => {
    const e = entry({ name_de: 'Niebüll' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Niebüll', source: GERMAN });
  });

  it("reports OSM's generic name as Danish where it is the Danish name", () => {
    const e = entry({ name_osm: 'Ribe', name_da: 'Ribe', name_de: 'Ripen' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Ribe', source: DANISH });
  });

  it("reports OSM's generic name as German where it is the German name", () => {
    const e = entry({ name_osm: 'Niebüll', name_de: 'Niebüll' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Niebüll', source: GERMAN });
  });

  // Tønder, not Tondern: the local view also takes OSM's generic name before the German one.
  it("reports OSM's generic name as of unknown source where it is no name the entry knows a language of", () => {
    const e = entry({ name_osm: 'Tønder', name_de: 'Tondern' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Tønder', source: UNKNOWN });
  });

  it('falls back to Danish only as a last resort, after German has had its turn', () => {
    const e = entry({ name_da: 'Ålborg' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Ålborg', source: DANISH });
  });

  it('resolves to an empty name of unknown source when the entry has nothing at all', () => {
    expect(resolveName(entry(), 'frr-x-mooring')).toEqual({ name: '', source: UNKNOWN });
  });

  it('the local view never shows name:frr, only frasch:local then Low Saxon then German', () => {
    // name_frr is deliberately ignored by the local view (see dialects/labelChain.ts);
    // Low Saxon still wins over OSM's generic name and the German one.
    const e = entry({
      names: { nds: 'Sölerloch' },
      name_frr: 'Rüms',
      name_osm: 'Sylt',
      name_de: 'Sylt',
    });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Sölerloch', source: LOW_SAXON });
  });

  it('the local view falls back to German where there is no generic name', () => {
    expect(resolveName(entry({ name_de: 'Tondern' }), 'frr-x-local')).toEqual({
      name: 'Tondern',
      source: GERMAN,
    });
  });
});
