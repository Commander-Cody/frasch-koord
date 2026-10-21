import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { FakeMap } from '../../testing/fakeMap';
import { queryParamWhenShown } from '../../testing/queryParamWhenShown';
import AreaPanel from './AreaPanel';
import type { AreaCollection, AreaFeature } from './areas';

/** A municipality the row on `line` assigns to Mooring, with the row's research `note`. */
function municipality(name: string, osm: string, line: number, note = ''): AreaFeature {
  return {
    type: 'Feature',
    properties: { assigned: true, dialect: 'frr-x-mooring', name, note, osm, line, km2: 1 },
    geometry: { type: 'Polygon', coordinates: [] },
  };
}

/** A municipality no row claims. */
function unclaimed(name: string, osm: string): AreaFeature {
  return {
    type: 'Feature',
    properties: { assigned: false, name, osm, km2: 1 },
    geometry: { type: 'Polygon', coordinates: [] },
  };
}

function parts(...features: AreaFeature[]): AreaCollection {
  return { type: 'FeatureCollection', features };
}

/** What the dev server answers with, until a test rebuilds it. */
let built: AreaCollection;

/** The names of the municipalities the list shows, in its order. */
function listedNames(): string[] {
  const names = document.querySelectorAll('.dev-panel-rowbutton > span:first-child');
  return [...names].map((name) => name.textContent ?? '');
}

/** Renders the panel and waits for the municipalities to be listed. */
async function renderLoaded() {
  render(<AreaPanel map={new FakeMap().map} />);
  await screen.findByRole('button', { name: /Bargum/ });
}

beforeEach(() => {
  window.history.replaceState(null, '', '/?areas');
  Element.prototype.scrollIntoView = () => {};
  built = parts(municipality('Bargum', 'relation/1', 2), municipality('Risum', 'relation/2', 3));
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(built), { status: 200 }))),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('AreaPanel', () => {
  it('keeps the municipality selected across a rebuild that moved it', async () => {
    render(<AreaPanel map={new FakeMap().map} />);
    fireEvent.click(await screen.findByRole('button', { name: /Risum/ }));
    built = parts(
      municipality('Ackerum', 'relation/3', 2),
      municipality('Bargum', 'relation/1', 3),
      municipality('Risum', 'relation/2', 4),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    await screen.findByRole('button', { name: /Ackerum/ });
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('Risum');
  });

  it('selects nothing once a rebuild left no municipality', async () => {
    render(<AreaPanel map={new FakeMap().map} />);
    fireEvent.click(await screen.findByRole('button', { name: /Risum/ }));
    built = parts();
    const area = queryParamWhenShown('area', 'nothing matches that filter');
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    expect(await area).toBeUndefined();
  });

  it('lists only the municipalities the text filter lets through', async () => {
    await renderLoaded();

    fireEvent.change(screen.getByLabelText('filter by name, OSM reference or note'), {
      target: { value: 'bar' },
    });

    expect(listedNames()).toEqual(['Bargum']);
  });

  it('lists only the group picked in the legend', async () => {
    built = parts(municipality('Bargum', 'relation/1', 2), unclaimed('Nordstrand', 'relation/9'));
    await renderLoaded();

    fireEvent.click(screen.getByRole('button', { name: /^no row – Low Saxon by default/ }));

    expect(listedNames()).toEqual(['Nordstrand']);
  });

  it('lists every group again on a second click in the legend', async () => {
    built = parts(municipality('Bargum', 'relation/1', 2), unclaimed('Nordstrand', 'relation/9'));
    await renderLoaded();
    const legendItem = screen.getByRole('button', { name: /^no row – Low Saxon by default/ });

    fireEvent.click(legendItem);
    fireEvent.click(legendItem);

    expect(listedNames()).toEqual(['Bargum', 'Nordstrand']);
  });

  it("shows the research note of the selected municipality's row", async () => {
    built = parts(municipality('Bargum', 'relation/1', 2, 'Bökingharde, per the parish'));
    await renderLoaded();

    fireEvent.click(screen.getByRole('button', { name: /Bargum/ }));

    expect(screen.getByText('Bökingharde, per the parish')).toBeDefined();
  });

  it('offers to copy the reference of a selected municipality no row claims', async () => {
    built = parts(municipality('Bargum', 'relation/1', 2), unclaimed('Nordstrand', 'relation/9'));
    await renderLoaded();

    fireEvent.click(screen.getByRole('button', { name: /Nordstrand/ }));

    expect(screen.getByRole('button', { name: 'copy relation/9' })).toBeDefined();
  });
});
