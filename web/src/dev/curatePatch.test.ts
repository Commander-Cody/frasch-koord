import { describe, expect, it } from 'vitest';

import { decidedRows, type PatchEntry } from './curatePatch';

function decision(id: string, line: number, action: PatchEntry['action'], osm?: string): PatchEntry {
  return { id, line, kind: 'warft', name: 'Schörkewärw', de: 'Kirchwarft', action, osm };
}

describe('decidedRows', () => {
  it("is each row's last decision", () => {
    const done = decidedRows([decision('schorkewarw', 5, 'skip'), decision('schorkewarw', 5, 'osm', 'node/1')]);
    expect(done.get('schorkewarw')?.osm).toBe('node/1');
  });

  it('keeps rows that share name and German name apart by id', () => {
    const done = decidedRows([decision('schorkewarw', 5, 'osm', 'node/1'), decision('schorkewarw-2', 6, 'osm', 'node/2')]);
    expect([...done.keys()]).toEqual(['schorkewarw', 'schorkewarw-2']);
  });

  it('forgets a withdrawn decision, whatever line either was sent with', () => {
    // a row was added above between the two: the same row, another line
    const done = decidedRows([decision('schorkewarw', 11, 'osm', 'node/1'), decision('schorkewarw', 12, 'clear')]);
    expect(done.has('schorkewarw')).toBe(false);
  });
});
