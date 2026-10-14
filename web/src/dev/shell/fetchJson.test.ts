import { afterEach, describe, expect, it, vi } from 'vitest';

import { errorMessage, fetchJson } from './fetchJson';

function answer(status: number, body: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(body, { status }))),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchJson', () => {
  it('gives the body of an answer', async () => {
    answer(200, '{"rows":[1,2]}');
    await expect(fetchJson('/__curate/worklist')).resolves.toEqual({ rows: [1, 2] });
  });

  it('fails with the error the endpoint names', async () => {
    answer(404, '{"error":"names/work/curate.json not found"}');
    await expect(fetchJson('/__curate/worklist')).rejects.toThrow(
      'names/work/curate.json not found',
    );
  });

  it('fails with the status of an answer that names no error', async () => {
    answer(502, 'Bad Gateway');
    await expect(fetchJson('/__areas/parts')).rejects.toThrow('HTTP 502');
  });
});

describe('errorMessage', () => {
  it('says what was thrown even when it is no Error', () => {
    expect(errorMessage('offline')).toBe('offline');
  });
});
