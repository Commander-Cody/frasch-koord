import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import { FakeMap, FakeMarker } from '../../testing/fakeMap';
import CuratePanel from './CuratePanel';
import type { PatchEntry } from './patch';
import type { CurateCandidate, CurateRow, CurateWorklist } from './worklist';

vi.mock('maplibre-gl', async (actual) => ({
  ...(await actual<typeof import('maplibre-gl')>()),
  Marker: FakeMarker,
}));

/** A candidate 1 km out, without a position. */
function candidate(
  ref: string,
  name: string,
  placeClass: string,
  wikidata?: string,
): CurateCandidate {
  const tagged = wikidata ? { wikidata } : {};
  return {
    ref,
    name,
    class: placeClass,
    km: 1,
    lon: null,
    lat: null,
    tags: '',
    in_sh: false,
    ...tagged,
  };
}

function curateRow(id: string, name: string, de: string): CurateRow {
  return {
    id,
    line: 2,
    kind: 'settlement',
    result: 'ambiguous',
    name,
    names: {},
    name_de: de,
    name_da: '',
    slug_suggestion: '',
    de,
    da: '',
    hint: '',
    note: '',
    why: '',
    hint_point: null,
    candidates: [candidate(`node/${id.length}`, de, 'village')],
  };
}

const WORKLIST: CurateWorklist = {
  bbox: [8, 54, 9, 55],
  kind_order: ['settlement', 'warft'],
  name_columns: ['mooring', 'local', 'fering'],
  polygon_kinds: ['koog'],
  class_keys: ['place', 'boundary'],
  settlement_places: ['village', 'town'],
  results: ['ambiguous', 'not_found'],
  rows: [
    curateRow('naibel', 'Naibel', 'Niebüll'),
    curateRow('rischsbel', 'Rischsbel', 'Risum'),
    curateRow('deesbel', 'Deesbel', 'Dagebüll'),
    {
      ...curateRow('taning', 'Taning', 'Tönning'),
      candidates: [candidate('node/7', 'Tönning', 'town', 'Q1717813;Q20729612')],
    },
    {
      ...curateRow('hoosem', 'Hoosem', 'Husum'),
      candidates: [
        candidate('node/9', 'Husum', 'town', 'Q21159'),
        candidate('way/10', 'Husum', 'boundary', 'Q21159;Q20729612'),
      ],
    },
  ],
  places: [{ id: 'naibel', kind: 'settlement', names: { mooring: 'Naibel', de: 'Niebüll' } }],
};

/** The worklist the dev server hands out; a test may put another in its place. */
let worklist: CurateWorklist;
/** The patch the dev server hands out; a test may put entries into it. */
let patchEntries: PatchEntry[];

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
  // The panel writes `?row=` and opens what it finds there: without this, a
  // test would start on the row the previous one ended on.
  window.history.replaceState(null, '', '/');
  // jsdom lays nothing out; CurateList keeps the selected row in view.
  Element.prototype.scrollIntoView = () => {};
  worklist = WORKLIST;
  patchEntries = [];
  // the hit test of a label click asks whether the pointer is a finger
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  posts = [];
  lookups = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string, init?: RequestInit) => {
      if (input === '/__curate/worklist') return Promise.resolve(json(worklist));
      if (input === '/__curate/patch' && init?.method === 'POST') {
        const reply = deferred();
        posts.push({ entry: JSON.parse(String(init.body)) as PatchEntry, reply });
        return reply.promise;
      }
      if (input === '/__curate/patch') return Promise.resolve(json({ entries: patchEntries }));
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
  render(<CuratePanel map={new FakeMap().map} />);
  await screen.findByText('Naibel');
}

/** Runs an Overpass lookup that finds one object, `osmRef`, with `tags`. */
async function findOverpassObject(osmRef: string, tags: Record<string, string>) {
  const [type, id] = osmRef.split('/');
  fireEvent.click(screen.getByRole('button', { name: 'Overpass' }));
  const { reply } = lookups[lookups.length - 1];
  await act(async () => {
    reply.resolve(
      json({ elements: [{ type, id: Number(id), center: { lat: 54.8, lon: 8.8 }, tags }] }),
    );
    await reply.promise;
  });
}

/** The colour of the number a candidate or lookup result is listed with. */
async function listedColor(osmRef: string): Promise<string> {
  const item = await listedItem(osmRef);
  return (item.querySelector('.curate-num') as HTMLElement).style.background;
}

/** The lookup result or candidate listed with `osmRef`. */
async function listedItem(osmRef: string): Promise<HTMLElement> {
  return (await screen.findByText(osmRef)).closest('li') as HTMLElement;
}

/** Types `text` into the form for an OSM reference by hand; -> its button. */
function typeReference(text: string): HTMLButtonElement {
  fireEvent.change(screen.getByLabelText('osm reference'), { target: { value: text } });
  return screen.getByRole<HTMLButtonElement>('button', { name: 'Pick reference' });
}

function selectedHeading(): string {
  return screen.getByRole('heading', { level: 2, name: /places\.csv line/ }).textContent ?? '';
}

describe('CuratePanel', () => {
  it('lists a row under its primary German name, not the cell with its variants', async () => {
    const row = { ...curateRow('naibel', 'Naibel', 'Niebüll; Nibüll (alt)'), name_de: 'Niebüll' };
    worklist = { ...WORKLIST, rows: [row] };

    await renderPanel();

    expect(document.querySelector('.curate-item-de')?.textContent).toBe('Niebüll');
  });

  it('lists the rows of a worklist exported again once reloaded', async () => {
    await renderPanel();
    worklist = { ...WORKLIST, rows: [...WORKLIST.rows, curateRow('ripen', 'Ripen', 'Ribe')] };
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    expect(await screen.findByText('Ripen')).toBeDefined();
  });

  it('selects no row once an export left none', async () => {
    await renderPanel();
    await openRow('Naibel');
    worklist = { ...WORKLIST, rows: [] };
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    await screen.findByText('nothing matches the filter');
    expect(new URLSearchParams(window.location.search).get('row')).toBeNull();
  });

  it('keeps the row the keys moved to in view', async () => {
    const scrolled: string[] = [];
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this.textContent ?? '');
    };
    await renderPanel();
    await openRow('Naibel');
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(scrolled.at(-1)).toMatch(/^Rischsbel/);
  });

  it('lists a row without a German name under its primary Danish one', async () => {
    const row = { ...curateRow('ripen', 'Ripen', ''), da: 'Ribe?', name_da: 'Ribe' };
    worklist = { ...WORKLIST, rows: [row] };

    render(<CuratePanel map={new FakeMap().map} />);
    await screen.findByText('Ripen');

    expect(document.querySelector('.curate-item-de')?.textContent).toBe('Ribe');
  });

  it('saves a decision with the primary German name of its row', async () => {
    const row = { ...curateRow('naibel', 'Naibel', 'Niebüll; Nibüll (alt)'), name_de: 'Niebüll' };
    worklist = { ...WORKLIST, rows: [row] };
    await renderPanel();
    await openRow('Naibel');

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));

    expect(posts[0].entry.de).toBe('Niebüll');
  });

  it('starts the slug of a local reference with the suggestion of the worklist', async () => {
    const row = { ...curateRow('naibel', 'Naibel', 'Niebüll'), slug_suggestion: 'niebull' };
    worklist = { ...WORKLIST, rows: [row] };
    await renderPanel();

    await openRow('Naibel');

    expect(screen.getByLabelText<HTMLInputElement>('slug').value).toBe('niebull');
  });

  it('saves the references typed by hand, a pasted OSM URL among them, as one cell', async () => {
    await renderPanel();
    await openRow('Naibel');

    fireEvent.click(typeReference('https://www.openstreetmap.org/way/177387348, Node/123'));

    expect(posts[0].entry.osm).toBe('way/177387348; node/123');
  });

  it('saves none of the references typed by hand when one names no OSM object', async () => {
    await renderPanel();
    await openRow('Naibel');

    expect(typeReference('way/177387348; local/naibel').disabled).toBe(true);
  });

  it('saves no reference typed by hand before there is one', async () => {
    await renderPanel();
    await openRow('Naibel');

    expect(typeReference('  ').disabled).toBe(true);
  });

  it('offers the area of a local reference for a kind the worklist says can be a polygon', async () => {
    worklist = { ...WORKLIST, polygon_kinds: ['settlement'] };
    await renderPanel();

    await openRow('Naibel');

    expect(screen.queryByLabelText('polygon_km2')).not.toBeNull();
  });

  it('sums a lookup result up by the class tags of the worklist, in their order', async () => {
    worklist = { ...WORKLIST, class_keys: ['historic', 'place'] };
    await renderPanel();
    await openRow('Naibel');

    await findOverpassObject('node/501', {
      name: 'Niebüll',
      place: 'hamlet',
      amenity: 'pub',
      historic: 'yes',
    });

    const item = await listedItem('node/501');
    expect(item.querySelector('.curate-candidate-meta')?.textContent).toBe(
      'historic=yes place=hamlet',
    );
  });

  it('sums a Nominatim hit without a category up by its display name', async () => {
    await renderPanel();
    await openRow('Naibel');

    fireEvent.click(screen.getByRole('button', { name: 'Nominatim' }));
    const hit = { osm_type: 'node', osm_id: 502, display_name: 'Niebüll, Nordfriesland' };
    await act(async () => {
      lookups[0].reply.resolve(json([{ ...hit, lat: '54.8', lon: '8.8' }]));
      await lookups[0].reply.promise;
    });

    const item = await listedItem('node/502');
    expect(item.querySelector('.curate-candidate-meta')?.textContent).toBe(
      'Niebüll, Nordfriesland',
    );
  });

  it("opens the openstreetmap.org search in the middle of the worklist's bbox", async () => {
    worklist = { ...WORKLIST, bbox: [8, 54, 9, 55] };
    await renderPanel();
    await openRow('Naibel');

    const link = screen.getByRole('link', { name: 'openstreetmap.org' });
    expect(link.getAttribute('href')).toMatch(/#map=10\/54\.5\/8\.5$/);
  });

  it('colours a candidate as a settlement when the worklist says its class is one', async () => {
    const row = {
      ...curateRow('naibel', 'Naibel', 'Niebüll'),
      candidates: [
        candidate('node/1', 'Niebüll', 'polder'),
        candidate('node/2', 'Niebüll', 'bus_stop'),
      ],
    };
    worklist = { ...WORKLIST, settlement_places: ['polder'], rows: [row] };
    await renderPanel();

    await openRow('Naibel');

    expect(await listedColor('node/1')).not.toBe(await listedColor('node/2'));
  });

  it('offers no area of a local reference for any other kind', async () => {
    await renderPanel();

    await openRow('Naibel');

    expect(screen.queryByLabelText('polygon_km2')).toBeNull();
  });

  it('offers the results the worklist names in the filter', async () => {
    worklist = { ...WORKLIST, results: ['not_found'] };

    await renderPanel();

    const options = within(screen.getByLabelText('result')).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual(['all results', 'not found']);
  });

  it('names no distance for a candidate without one', async () => {
    const row = curateRow('naibel', 'Naibel', 'Niebüll');
    row.candidates = [{ ...candidate('way/5', 'Niebüll', 'residential'), km: null }];
    worklist = { ...WORKLIST, rows: [row] };
    await renderPanel();

    await openRow('Naibel');

    expect((await listedItem('way/5')).textContent).not.toContain('km');
  });

  it('saves a double-clicked pick once', async () => {
    await renderPanel();
    await openRow('Naibel');

    const pick = screen.getByRole('button', { name: 'Pick' });
    fireEvent.click(pick);
    fireEvent.click(pick);

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
    await screen.findByText('could not save: /__curate/patch: disk full');

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
});

/* ------------------------------------------------------------ new places */

const KEY = 'new:3f9c0a';

/** The `create` of the place KEY, as the patch holds it. */
const HOORNE: PatchEntry = {
  id: KEY,
  action: 'create',
  kind: 'warft',
  names: { mooring: 'Hoorne', de: 'Horne' },
};

/** Fills the form of a new place: `fields` by their label. */
function fillPlace(fields: Record<string, string>) {
  for (const [label, value] of Object.entries(fields)) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
}

function savePlaceButton(): HTMLButtonElement {
  return screen.getByRole<HTMLButtonElement>('button', { name: 'Save place' });
}

/** The list of the created places. */
function newPlacesList(): HTMLElement {
  return screen.getByRole('list', { name: /^New places/ });
}

/** Renders the panel on `map`, with a created place in the patch already. */
async function renderWithHoorne(map = new FakeMap()) {
  patchEntries = [HOORNE];
  render(<CuratePanel map={map.map} />);
  await screen.findByText('Hoorne');
}

const AT = { lng: 8.8, lat: 54.8 };
/** Niebüll's label, which the name list does not have: tile feature id node/240042766. */
const NIEBUELL_LABEL = { id: 2400427661, properties: { 'name:de': 'Niebüll', 'name:da': 'Nibøl' } };

describe('CuratePanel, new places', () => {
  it('saves a new place under a provisional key', async () => {
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));
    fillPlace({
      'new place kind': 'warft',
      'new place mooring': 'Hoorne',
      'new place de': 'Horne',
    });

    fireEvent.click(savePlaceButton());

    expect(posts[0].entry).toMatchObject({
      id: expect.stringMatching(/^new:[0-9a-f]+$/),
      action: 'create',
      kind: 'warft',
      names: { mooring: 'Hoorne', de: 'Horne' },
    });
  });

  it('saves no new place without a kind', async () => {
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));
    fillPlace({ 'new place de': 'Horne' });

    expect(savePlaceButton().disabled).toBe(true);
  });

  it('saves no new place without a name', async () => {
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));
    fillPlace({ 'new place kind': 'warft', 'new place note': 'from the 1920 map' });

    expect(savePlaceButton().disabled).toBe(true);
  });

  it('offers every kind of the worklist for a new place', async () => {
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));

    const options = within(screen.getByLabelText('new place kind')).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual(['kind…', 'settlement', 'warft']);
  });

  it('warns of a row of the list that has a name typed for a new place', async () => {
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));

    fillPlace({ 'new place fering': 'Niebüll' });

    within(screen.getByRole('list', { name: 'already in the list' })).getByText(/naibel/);
  });

  it('lists a new place as soon as it is saved, marked new', async () => {
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));
    fillPlace({ 'new place kind': 'warft', 'new place mooring': 'Hoorne' });
    fireEvent.click(savePlaceButton());

    await answerPost(0);

    within(newPlacesList()).getByText('new');
  });

  it('lists the places the patch created', async () => {
    await renderWithHoorne();

    within(newPlacesList()).getByText('Hoorne');
  });

  it('lists a created place that is decided, though done rows are hidden', async () => {
    patchEntries = [HOORNE, { id: KEY, action: 'skip' }];
    render(<CuratePanel map={new FakeMap().map} />);

    expect(
      await within(await screen.findByRole('list', { name: /^New places/ })).findByText('Hoorne'),
    ).toBeDefined();
  });

  it('opens a created place by the key the address names', async () => {
    window.history.replaceState(null, '', `/?curate&row=${KEY}`);

    await renderWithHoorne();

    expect((await screen.findByRole('heading', { level: 2 })).textContent).toContain('Hoorne');
  });

  it('saves the decision of a created place under its key', async () => {
    await renderWithHoorne();
    fireEvent.click(within(newPlacesList()).getByText('Hoorne'));

    fireEvent.click(await screen.findByRole('button', { name: 'Skip' }));

    expect(posts[0].entry).toMatchObject({ id: KEY, action: 'skip' });
  });

  it('saves an edited place under the key it had', async () => {
    await renderWithHoorne();
    fireEvent.click(within(newPlacesList()).getByText('Hoorne'));
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    fillPlace({ 'new place de': 'Hoorn' });

    fireEvent.click(savePlaceButton());

    expect(posts[0].entry).toMatchObject({ id: KEY, action: 'create', names: { de: 'Hoorn' } });
  });

  it('discards a created place', async () => {
    await renderWithHoorne();
    fireEvent.click(within(newPlacesList()).getByText('Hoorne'));

    fireEvent.click(await screen.findByRole('button', { name: 'Discard' }));

    expect(posts[0].entry).toEqual({ id: KEY, action: 'discard' });
  });

  it("starts a new place from a clicked label with the label's German and Danish names", async () => {
    const map = new FakeMap();
    render(<CuratePanel map={map.map} />);
    await screen.findByText('Naibel');
    act(() => map.click(AT, NIEBUELL_LABEL));

    fireEvent.click(screen.getByRole('button', { name: 'New place from this' }));

    expect([
      screen.getByLabelText<HTMLInputElement>('new place de').value,
      screen.getByLabelText<HTMLInputElement>('new place da').value,
    ]).toEqual(['Niebüll', 'Nibøl']);
  });

  it("starts the German name with OSM's name for a label with neither", async () => {
    const map = new FakeMap();
    render(<CuratePanel map={map.map} />);
    await screen.findByText('Naibel');
    act(() => map.click(AT, { id: 2400427661, properties: { name: 'Niebüll' } }));

    fireEvent.click(screen.getByRole('button', { name: 'New place from this' }));

    expect(screen.getByLabelText<HTMLInputElement>('new place de').value).toBe('Niebüll');
  });

  it('saves the object of the clicked label as the decision of the new place', async () => {
    const map = new FakeMap();
    render(<CuratePanel map={map.map} />);
    await screen.findByText('Naibel');
    act(() => map.click(AT, NIEBUELL_LABEL));
    fireEvent.click(screen.getByRole('button', { name: 'New place from this' }));
    fillPlace({ 'new place kind': 'settlement' });
    fireEvent.click(savePlaceButton());

    await answerPost(0);

    expect(posts[1].entry).toMatchObject({
      id: posts[0].entry.id,
      action: 'osm',
      osm: 'node/240042766',
    });
  });

  it('closes the form of a new place when a row is opened from the list', async () => {
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));

    await openRow('Naibel');

    expect(screen.queryByLabelText('new place kind')).toBeNull();
  });

  it('takes the offer of a clicked label back once a place is started from it', async () => {
    const map = new FakeMap();
    render(<CuratePanel map={map.map} />);
    await screen.findByText('Naibel');
    act(() => map.click(AT, NIEBUELL_LABEL));

    fireEvent.click(screen.getByRole('button', { name: 'New place from this' }));

    expect(screen.queryByRole('button', { name: 'New place from this' })).toBeNull();
  });

  it('says why a discard could not be saved', async () => {
    await renderWithHoorne();
    fireEvent.click(within(newPlacesList()).getByText('Hoorne'));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard' }));

    await act(async () => {
      posts[0].reply.resolve(
        new Response(JSON.stringify({ ok: false, error: 'disk full' }), { status: 500 }),
      );
      await posts[0].reply.promise;
    });

    await screen.findByText('could not save: /__curate/patch: disk full');
  });

  it('offers a new place for a clicked label once the form took over from an armed row', async () => {
    const map = new FakeMap();
    render(<CuratePanel map={map.map} />);
    await screen.findByText('Naibel');
    await openRow('Naibel');
    fireEvent.click(screen.getByRole('button', { name: 'set position on map' }));
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));

    act(() => map.click(AT, NIEBUELL_LABEL));

    expect(screen.queryByRole('button', { name: 'New place from this' })).not.toBeNull();
  });

  it('warns of another created place that has a name typed for a new place', async () => {
    await renderWithHoorne();
    fireEvent.click(screen.getByRole('button', { name: 'New place' }));

    fillPlace({ 'new place de': 'Horne' });

    within(screen.getByRole('list', { name: 'already in the list' })).getByText(new RegExp(KEY));
  });

  it('does not warn of the created place being edited itself', async () => {
    await renderWithHoorne();
    fireEvent.click(within(newPlacesList()).getByText('Hoorne'));

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));

    expect(screen.queryByRole('list', { name: 'already in the list' })).toBeNull();
  });

  it('lists no created place the kind filter leaves out', async () => {
    await renderWithHoorne();

    fireEvent.change(screen.getByLabelText('kind'), { target: { value: 'settlement' } });

    expect(screen.queryByRole('list', { name: /^New places/ })).toBeNull();
  });

  it('lists no created place the text filter leaves out', async () => {
    await renderWithHoorne();

    fireEvent.change(screen.getByPlaceholderText('filter: Frisian, German, hint'), {
      target: { value: 'Niebüll' },
    });

    expect(screen.queryByRole('list', { name: /^New places/ })).toBeNull();
  });

  it('offers no new place for the label of a row of the list', async () => {
    const map = new FakeMap();
    render(<CuratePanel map={map.map} />);
    await screen.findByText('Naibel');

    act(() => map.click(AT, { id: 2400427661, properties: { 'frasch:ref': 'naibel' } }));

    expect(screen.queryByRole('button', { name: 'New place from this' })).toBeNull();
  });

  it('sets the position, offering no new place, for a click while that is armed', async () => {
    const map = new FakeMap();
    render(<CuratePanel map={map.map} />);
    await screen.findByText('Naibel');
    await openRow('Naibel');
    fireEvent.click(screen.getByRole('button', { name: 'set position on map' }));

    act(() => map.click(AT, NIEBUELL_LABEL));

    expect(screen.queryByRole('button', { name: 'New place from this' })).toBeNull();
  });
});
