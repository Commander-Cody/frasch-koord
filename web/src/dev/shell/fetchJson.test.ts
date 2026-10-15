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

  it('fails with the error the endpoint names, and which endpoint it was', async () => {
    answer(404, '{"error":"run frasch curate export"}');
    await expect(fetchJson('/__curate/worklist')).rejects.toThrow(
      '/__curate/worklist: run frasch curate export',
    );
  });

  it('fails with the status of an answer that names no error', async () => {
    answer(502, 'Bad Gateway');
    await expect(fetchJson('/__areas/parts')).rejects.toThrow('/__areas/parts: HTTP 502');
  });

  it('names the endpoint whose answer is no JSON', async () => {
    answer(200, '{"entries": [');
    await expect(fetchJson('/__curate/patch')).rejects.toThrow(/^\/__curate\/patch: /);
  });

  it('names the endpoint it could not reach', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );
    await expect(fetchJson('/__curate/patch')).rejects.toThrow('/__curate/patch: Failed to fetch');
  });
});

describe('errorMessage', () => {
  it('says what was thrown even when it is no Error', () => {
    expect(errorMessage('offline')).toBe('offline');
  });
});
