// A stand-in for the MapLibre map the dev views draw on. jsdom has no WebGL,
// so a test hands a panel this instead: it keeps the sources and layers a
// panel adds, and neither moves nor answers clicks.

import type { Map as MapLibreMap } from 'maplibre-gl';

interface FakeLayer {
  id: string;
  source?: string;
  filter?: unknown;
}

export class FakeMap {
  private readonly sources = new Map<string, { data: unknown; setData: (data: unknown) => void }>();
  private layers: FakeLayer[] = [];
  private readonly canvas = document.createElement('canvas');

  /** As the typed map a panel takes. */
  get map(): MapLibreMap {
    return this as unknown as MapLibreMap;
  }

  /** The ids of the layers, bottom first. */
  layerIds(): string[] {
    return this.layers.map((layer) => layer.id);
  }

  filterOf(id: string): unknown {
    return this.getLayer(id)?.filter ?? null;
  }

  sourceData(id: string): unknown {
    return this.sources.get(id)?.data;
  }

  /* ------------------------------------------------- what the panels call */

  addSource(id: string, spec: { data: unknown }): void {
    if (this.sources.has(id)) throw new Error(`source ${id} already exists`);
    const source = {
      data: spec.data,
      setData: (data: unknown) => {
        source.data = data;
      },
    };
    this.sources.set(id, source);
  }

  getSource(id: string) {
    return this.sources.get(id);
  }

  removeSource(id: string): void {
    if (this.layers.some((layer) => layer.source === id)) throw new Error(`source ${id} in use`);
    this.sources.delete(id);
  }

  addLayer(spec: FakeLayer, before?: string): void {
    if (this.getLayer(spec.id)) throw new Error(`layer ${spec.id} already exists`);
    if (spec.source && !this.sources.has(spec.source)) throw new Error(`no source ${spec.source}`);
    const at = before === undefined ? -1 : this.layers.findIndex((layer) => layer.id === before);
    const layer = { ...spec };
    if (at < 0) this.layers.push(layer);
    else this.layers.splice(at, 0, layer);
  }

  getLayer(id: string): FakeLayer | undefined {
    return this.layers.find((layer) => layer.id === id);
  }

  removeLayer(id: string): void {
    this.layers = this.layers.filter((layer) => layer.id !== id);
  }

  setFilter(id: string, filter: unknown): void {
    const layer = this.getLayer(id);
    if (!layer) throw new Error(`no layer ${id}`);
    layer.filter = filter ?? undefined;
  }

  on(): this {
    return this;
  }

  off(): this {
    return this;
  }

  getCanvas(): HTMLCanvasElement {
    return this.canvas;
  }

  fitBounds(): this {
    return this;
  }

  flyTo(): this {
    return this;
  }
}

/**
 * A stand-in for MapLibre's Marker, which needs the camera of a real map:
 * `vi.mock('maplibre-gl', …)` puts it in the real one's place. It keeps where
 * it stands, and shows its element in the document as long as it is on a map.
 */
export class FakeMarker {
  private readonly element: HTMLElement;
  private at: [number, number] = [0, 0];

  constructor(options: { element?: HTMLElement } = {}) {
    this.element = options.element ?? document.createElement('div');
  }

  getElement(): HTMLElement {
    return this.element;
  }

  setLngLat(at: [number, number]): this {
    this.at = at;
    return this;
  }

  getLngLat(): { lng: number; lat: number } {
    return { lng: this.at[0], lat: this.at[1] };
  }

  addTo(): this {
    document.body.append(this.element);
    return this;
  }

  remove(): this {
    this.element.remove();
    return this;
  }

  on(): this {
    return this;
  }
}
