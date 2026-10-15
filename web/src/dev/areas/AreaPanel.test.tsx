import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { FakeMap } from '../../testing/fakeMap';
import AreaPanel from './AreaPanel';
import type { AreaCollection, AreaFeature } from './areas';

/** A municipality the row on `line` assigns to Mooring. */
function municipality(name: string, osm: string, line: number): AreaFeature {
  return {
    type: 'Feature',
    properties: { assigned: true, dialect: 'frr-x-mooring', name, note: '', osm, line, km2: 1 },
    geometry: { type: 'Polygon', coordinates: [] },
  };
}

function parts(...features: AreaFeature[]): AreaCollection {
  return { type: 'FeatureCollection', features };
}

/** What the dev server answers with, until a test rebuilds it. */
let built: AreaCollection;

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
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    await screen.findByText('nothing matches that filter');
    expect(new URLSearchParams(window.location.search).get('area')).toBeNull();
  });
});
