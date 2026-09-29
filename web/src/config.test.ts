import { expect, it } from 'vitest';

import { DIALECTS } from './config';

// DialectEntry types `status` and `view` as unions, but the registry arrives
// as JSON; frasch/registry.py allows exactly these values.
it('reads only the status and view values the registry allows', () => {
  for (const dialect of DIALECTS) {
    expect(['living', 'extinct']).toContain(dialect.status);
    expect(['yes', 'no']).toContain(dialect.view);
  }
});
