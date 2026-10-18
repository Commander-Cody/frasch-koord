import { describe, expect, it } from 'vitest';

import { LOCAL_TAG } from './views';
import { labelChain } from './labelChain';

// A registry of its own, so the expected chains are written out by hand and
// a dialect added to names/dialects.csv changes nothing here.
const REGISTRY = [{ tag: 'frr-x-a' }, { tag: 'frr-x-b' }, { tag: 'frr-x-c' }];

const GENERIC_TAIL = ['name:frr', 'name:nds', 'name:de', 'name:latin', 'name'];

describe('labelChain', () => {
  it('puts the dialect itself first, then frasch:local, then every other dialect in registry order, then the generic tail', () => {
    expect(labelChain('frr-x-b', REGISTRY)).toEqual([
      'name:frr-x-b',
      'frasch:local',
      'name:frr-x-a',
      'name:frr-x-c',
      ...GENERIC_TAIL,
    ]);
  });

  it('the local view is only frasch:local, then the local majority language, never name:frr, and German only last', () => {
    const chain = labelChain(LOCAL_TAG, REGISTRY);
    expect(chain).toEqual(['frasch:local', 'name:nds', 'name:latin', 'name', 'name:de']);
    expect(chain).not.toContain('name:frr');
  });
});
