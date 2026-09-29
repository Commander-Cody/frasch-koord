import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import CuratePanel from './CuratePanel';
import type { PatchEntry } from './curatePatch';
import type { CurateRow, CurateWorklist } from './curateWorklist';

function curateRow(id: string, name: string, de: string): CurateRow {
  return {
    id,
    line: 2,
    kind: 'settlement',
    result: 'ambiguous',
    name,
    names: {},
    de,
    da: '',
    hint: '',
    note: '',
    why: '',
    hint_point: null,
    candidates: [{ ref: `node/${id.length}`, name: de, class: 'village', km: 1 }],
  };
}

const WORKLIST: CurateWorklist = {
  generated: '2026-09-30',
  bbox: [8, 54, 9, 55],
  kind_order: ['settlement'],
  rows: [
    curateRow('naibel', 'Naibel', 'Niebüll'),
    curateRow('rischsbel', 'Rischsbel', 'Risum'),
    curateRow('deesbel', 'Deesbel', 'Dagebüll'),
  ],
};

/** A reply the test settles by hand. */
function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

/** The dev server's patch endpoint as a stub: every POST waits until the test answers it. */
let posts: { entry: PatchEntry; reply: ReturnType<typeof deferred> }[];
/** Every request to an OSM service, with its init. */
let lookups: { url: string; init?: RequestInit }[];

function answerPost(i: number) {
  const { entry, reply } = posts[i];
  return act(async () => {
    reply.resolve(json({ ok: true, entry }));
    await reply.promise;
  });
}

beforeEach(() => {
  // jsdom lays nothing out; CurateList keeps the selected row in view.
  Element.prototype.scrollIntoView = () => {};
  posts = [];
  lookups = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string, init?: RequestInit) => {
      if (input === '/__curate/worklist') return Promise.resolve(json(WORKLIST));
      if (input === '/__curate/patch' && init?.method === 'POST') {
        const reply = deferred();
        posts.push({ entry: JSON.parse(String(init.body)) as PatchEntry, reply });
        return reply.promise;
      }
      if (input === '/__curate/patch') return Promise.resolve(json({ entries: [] }));
      lookups.push({ url: input, init });
      return new Promise<Response>(() => {});
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openRow(name: string) {
  const list = document.querySelector('.curate-list') as HTMLElement;
  fireEvent.click(within(list).getByText(name));
  await screen.findByRole('heading', { level: 2, name: new RegExp(name) });
}

async function renderPanel() {
  render(<CuratePanel mapRef={{ current: null }} />);
  await screen.findByText('Naibel');
}

function selectedHeading(): string {
  return screen.getByRole('heading', { level: 2, name: /places\.csv line/ }).textContent ?? '';
}

describe('CuratePanel', () => {
  it('saves a double-clicked pick once', async () => {
    await renderPanel();
    await openRow('Naibel');

    const pick = screen.getByRole('button', { name: 'Pick' });
    fireEvent.click(pick);
    fireEvent.click(pick);

    expect(posts).toHaveLength(1);
  });

  it('saves a double-clicked skip once', async () => {
    await renderPanel();
    await openRow('Naibel');

    const skip = screen.getByRole('button', { name: 'Skip' });
    fireEvent.click(skip);
    fireEvent.click(skip);

    expect(posts).toHaveLength(1);
  });

  it('lets the user try again after a save failed', async () => {
    await renderPanel();
    await openRow('Naibel');
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    await act(async () => {
      posts[0].reply.resolve(new Response(JSON.stringify({ ok: false, error: 'disk full' }), { status: 500 }));
      await posts[0].reply.promise;
    });
    await screen.findByText('could not save: disk full');

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));

    expect(posts).toHaveLength(2);
  });

  it('moves on to the next open row after a save', async () => {
    await renderPanel();
    await openRow('Naibel');

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    await answerPost(0);

    expect(selectedHeading()).toContain('Rischsbel');
  });

  it('stays on the row the user went to while a save was on its way', async () => {
    await renderPanel();
    await openRow('Naibel');
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));

    await openRow('Deesbel');
    await answerPost(0);

    expect(selectedHeading()).toContain('Deesbel');
  });

  it('aborts a lookup still on its way when the user goes to another row', async () => {
    await renderPanel();
    await openRow('Naibel');
    fireEvent.click(screen.getByRole('button', { name: 'Nominatim' }));
    expect(lookups).toHaveLength(1);

    await openRow('Rischsbel');

    expect(lookups[0].init?.signal?.aborted).toBe(true);
  });

  it('keeps a quote in the name inside the Overpass query', async () => {
    await renderPanel();
    await openRow('Naibel');
    fireEvent.change(screen.getByLabelText('lookup query'), { target: { value: 'Söl "Ring"' } });

    fireEvent.click(screen.getByRole('button', { name: 'Overpass' }));

    expect(String(lookups[0].init?.body)).toContain('nwr["name"~"Söl \\"Ring\\"",i]');
  });
});
