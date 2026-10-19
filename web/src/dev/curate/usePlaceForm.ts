// The form of a place the curation view creates (#113), as the panel holds
// it: opened for a fresh key, from a clicked label or for a created place;
// saved as a `create` under its key; a created place discarded.

import { useState } from 'react';

import { errorMessage } from '../shell/fetchJson';
import type { ClickedLabel } from './labelClicks';
import { createEntry, listedPlace, newPlaceKey, type PlaceDraft } from './newPlaces';
import { storeEntry, type Decision, type NewPlace, type UpdateLoaded } from './patch';
import type { ListedPlace } from './worklist';

/** The form of a new place, open: for which key, starting with what. */
export interface OpenForm {
  key: string;
  title: string;
  initial: PlaceDraft;
  /** Saved after the place: the object of the label it was started from. */
  decision?: Decision;
}

const EMPTY_DRAFT: PlaceDraft = { kind: '', names: {}, note: '' };

export function newPlaceForm(): OpenForm {
  return { key: newPlaceKey(), title: 'New place', initial: EMPTY_DRAFT };
}

/** The form of a new place from a clicked label: its names, and its object as the decision. */
export function labelForm(label: ClickedLabel): OpenForm {
  return {
    key: newPlaceKey(),
    title: `New place from ${label.ref ?? label.name}`,
    initial: { ...EMPTY_DRAFT, names: { de: label.de, da: label.da } },
    ...(label.ref && { decision: { action: 'osm', osm: label.ref } }),
  };
}

/** The form of a created place, to edit it under its key. */
export function editForm(place: NewPlace): OpenForm {
  return {
    key: place.key,
    title: 'Edit new place',
    initial: { kind: place.kind, names: place.names, note: place.note },
  };
}

/**
 * What the duplicate warning of the place `key` compares its names with:
 * every row of the list (`listed`) and every other created place.
 */
export function comparedPlaces(
  listed: readonly ListedPlace[],
  created: readonly NewPlace[],
  key: string,
): ListedPlace[] {
  return [...listed, ...created.filter((place) => place.key !== key).map(listedPlace)];
}

/**
 * The open form and what it does: a saved place is selected (`select`), a
 * failed write says why in `error`. One write at a time: a double click
 * must not append two lines.
 */
export function usePlaceForm(update: UpdateLoaded, select: (key: string) => void) {
  const [form, setForm] = useState<OpenForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = (next: OpenForm) => {
    setForm(next);
    setError(null);
  };
  const close = () => setForm(null);
  const run = async (write: () => Promise<void>) => {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await write();
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };
  const save = (draft: PlaceDraft, nameColumns: readonly string[]) => {
    if (!form) return;
    const { key, decision } = form;
    void run(async () => {
      await storeEntry(update, createEntry(key, draft, nameColumns));
      if (decision) await storeEntry(update, { id: key, ...decision });
      setForm(null);
      select(key);
    });
  };
  const discard = (key: string) => {
    void run(() => storeEntry(update, { id: key, action: 'discard' }));
  };
  return { form, saving, error, open, close, save, discard };
}
