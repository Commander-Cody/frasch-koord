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
    {
      ...curateRow('taning', 'Taning', 'Tönning'),
      candidates: [
        { ref: 'node/7', name: 'Tönning', class: 'town', km: 1, wikidata: 'Q1717813;Q20729612' },
      ],
    },
    {
      ...curateRow('hoosem', 'Hoosem', 'Husum'),
      candidates: [
        { ref: 'node/9', name: 'Husum', class: 'town', km: 1, wikidata: 'Q21159' },
        { ref: 'way/10', name: 'Husum', class: 'boundary', km: 1, wikidata: 'Q21159;Q20729612' },
      ],
    },
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
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** The dev server's patch endpoint as a stub: every POST waits until the test answers it. */
let posts: { entry: PatchEntry; reply: ReturnType<typeof deferred> }[];
/** Every request to an OSM service, with its init; each waits until the test answers it. */
let lookups: { url: string; init?: RequestInit; reply: ReturnType<typeof deferred> }[];

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
      const reply = deferred();
      lookups.push({ url: input, init, reply });
      return reply.promise;
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

/** Runs an Overpass lookup that finds one way, `way/<id>`, tagged with `wikidata`. */
async function findOverpassResult(osmRef: string, wikidata: string) {
  const [type, id] = osmRef.split('/');
  fireEvent.click(screen.getByRole('button', { name: 'Overpass' }));
  const { reply } = lookups[lookups.length - 1];
  await act(async () => {
    reply.resolve(
      json({
        elements: [
          {
            type,
            id: Number(id),
            center: { lat: 54.8, lon: 8.8 },
            tags: { name: 'Niebüll', wikidata },
          },
        ],
      }),
    );
    await reply.promise;
  });
}

/** The lookup result or candidate listed with `osmRef`. */
async function listedItem(osmRef: string): Promise<HTMLElement> {
  return (await screen.findByText(osmRef)).closest('li') as HTMLElement;
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
      posts[0].reply.resolve(
        new Response(JSON.stringify({ ok: false, error: 'disk full' }), { status: 500 }),
      );
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

  it('saves a candidate whose wikidata tag names several ids without one', async () => {
    await renderPanel();
    await openRow('Taning');

    fireEvent.click(screen.getByRole('button', { name: 'Pick' }));

    expect(posts[0].entry).toMatchObject({ action: 'osm', osm: 'node/7' });
    expect(posts[0].entry).not.toHaveProperty('wikidata');
  });

  it('saves an Overpass result whose wikidata tag names several ids without one', async () => {
    await renderPanel();
    await openRow('Naibel');
    await findOverpassResult('way/8', 'Q1;Q2');

    fireEvent.click(within(await listedItem('way/8')).getByRole('button', { name: 'Pick' }));

    expect(posts[0].entry).toMatchObject({ action: 'osm', osm: 'way/8' });
    expect(posts[0].entry).not.toHaveProperty('wikidata');
  });

  it('saves the one well-formed id of a multi-pick, leaving out a tag with several', async () => {
    await renderPanel();
    await openRow('Hoosem');
    fireEvent.click(screen.getByLabelText('select node/9'));
    fireEvent.click(screen.getByLabelText('select way/10'));

    fireEvent.click(screen.getByRole('button', { name: 'Pick 2 selected' }));

    expect(posts[0].entry).toMatchObject({
      action: 'osm',
      osm: 'node/9; way/10',
      wikidata: 'Q21159',
    });
  });

  it('says on a candidate that its wikidata tag with several ids is not saved', async () => {
    await renderPanel();
    await openRow('Taning');

    within(await listedItem('node/7')).getByText(
      'wikidata Q1717813;Q20729612: not one id, not saved',
    );
  });

  it('says on an Overpass result that its wikidata tag with several ids is not saved', async () => {
    await renderPanel();
    await openRow('Naibel');

    await findOverpassResult('way/8', 'Q1;Q2');

    within(await listedItem('way/8')).getByText('wikidata Q1;Q2: not one id, not saved');
  });
});
