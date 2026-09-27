import { describe, expect, it } from 'vitest';

import { LOCAL_TAG } from './config';
import { labelChain } from './labelChain';

// Expected chains are hand-written from the registry order in
// src/generated/dialects.json (mooring, wieding, karrhard, nordgoes, midgoes,
// suedgoes, fering, oomrang, solring, hallig, halunder), not derived by
// calling labelChain itself, so a change to the chain's logic would actually
// be caught here.

describe('labelChain', () => {
  it('puts the dialect itself first, then frasch:local, then every other dialect in registry order, then the generic tail', () => {
    expect(labelChain('frr-x-mooring')).toEqual([
      'name:frr-x-mooring',
      'frasch:local',
      'name:frr-x-wieding',
      'name:frr-x-karrhard',
      'name:frr-x-nordgoes',
      'name:frr-x-midgoes',
      'name:frr-x-suedgoes',
      'name:frr-x-fering',
      'name:frr-x-oomrang',
      'name:frr-x-solring',
      'name:frr-x-hallig',
      'name:frr-x-halunder',
      'name:frr',
      'name:nds',
      'name:de',
      'name:latin',
      'name',
    ]);
  });

  it('for a different dialect view, still lists every OTHER dialect in registry order (excluding itself)', () => {
    expect(labelChain('frr-x-fering')).toEqual([
      'name:frr-x-fering',
      'frasch:local',
      'name:frr-x-mooring',
      'name:frr-x-wieding',
      'name:frr-x-karrhard',
      'name:frr-x-nordgoes',
      'name:frr-x-midgoes',
      'name:frr-x-suedgoes',
      'name:frr-x-oomrang',
      'name:frr-x-solring',
      'name:frr-x-hallig',
      'name:frr-x-halunder',
      'name:frr',
      'name:nds',
      'name:de',
      'name:latin',
      'name',
    ]);
  });

  it('the local view is only frasch:local, then the local majority language, never name:frr or name:de', () => {
    const chain = labelChain(LOCAL_TAG);
    expect(chain).toEqual(['frasch:local', 'name:nds', 'name:latin', 'name']);
    expect(chain).not.toContain('name:frr');
    expect(chain).not.toContain('name:de');
  });
});
