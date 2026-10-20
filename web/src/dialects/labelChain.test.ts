import { describe, expect, it } from 'vitest';

import { LOCAL_TAG } from './views';
import { labelChain } from './labelChain';

// A registry of its own, so the expected chains are written out by hand and
// a dialect added to names/dialects.csv changes nothing here.
const REGISTRY = [
  { tag: 'frr-x-a', language: 'frr' },
  { tag: 'frr-x-b', language: 'frr' },
  { tag: 'frr-x-c', language: 'frr' },
  { tag: 'nds', language: 'nds' },
  { tag: 'jut', language: 'jut' },
];

const GENERIC_TAIL = ['name:frr', 'name:nds', 'name:de', 'name:latin', 'name'];

describe('labelChain', () => {
  it('in a Frisian area puts the dialect itself first, then frasch:local, then every other Frisian dialect in registry order, then the generic tail', () => {
    expect(labelChain('frr-x-b', true, REGISTRY)).toEqual([
      'name:frr-x-b',
      'frasch:local',
      'name:frr-x-a',
      'name:frr-x-c',
      ...GENERIC_TAIL,
    ]);
  });

  it('elsewhere reads frasch:local only after name:frr, before name:nds', () => {
    expect(labelChain('frr-x-b', false, REGISTRY)).toEqual([
      'name:frr-x-b',
      'name:frr-x-a',
      'name:frr-x-c',
      'name:frr',
      'frasch:local',
      'name:nds',
      'name:de',
      'name:latin',
      'name',
    ]);
  });

  it('counts no Synnejysk name among the other dialects', () => {
    expect(labelChain('frr-x-b', true, REGISTRY)).not.toContain('name:jut');
  });

  it('the local view is only frasch:local, then the local majority language, never name:frr, and German only last', () => {
    for (const inFrisianArea of [true, false]) {
      expect(labelChain(LOCAL_TAG, inFrisianArea, REGISTRY)).toEqual([
        'frasch:local',
        'name:nds',
        'name:latin',
        'name',
        'name:de',
      ]);
    }
  });
});
