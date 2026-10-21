// The form of a place the curation view creates (#113), as the panel holds
// it: opened for a fresh key, from a clicked label or for a created place;
// saved as a `create` under its key; a created place discarded.

import { useRef, useState } from 'react';

import { errorMessage } from '../shell/fetchJson';
import type { Selection } from '../shell/useSelection';
import { labelKind, type ClickedLabel } from './labelClicks';
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

/**
 * The form of a new place from a clicked label: its kind as far as its class
 * tells (`settlementPlaces` are the worklist's), its names, and its object as
 * the decision.
 */
export function labelForm(label: ClickedLabel, settlementPlaces: readonly string[]): OpenForm {
  return {
    key: newPlaceKey(),
    title: `New place from ${label.ref ?? label.name}`,
    initial: {
      ...EMPTY_DRAFT,
      kind: labelKind(label, settlementPlaces),
      names: { de: label.de, da: label.da },
    },
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

/** A write that failed, and the key of the form or the created place it was for. */
interface Failure {
  message: string;
  key: string;
}

/**
 * The open form and what it does: a saved place is selected, a failed
 * write says why in `error` — but only while the user is still where the
 * write was made, the form of that place or (a discard) the place itself:
 * they may have opened another form or row meanwhile. One write at a time:
 * a double click must not append two lines.
 */
export function usePlaceForm(
  update: UpdateLoaded,
  { selected, select }: Pick<Selection, 'selected' | 'select'>,
) {
  const [form, setForm] = useState<OpenForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  // For a save that resolves later: is its form still the open one?
  const formNow = useRef<string | null>(null);

  const open = (next: OpenForm) => {
    formNow.current = next.key;
    setForm(next);
    setFailure(null);
  };
  // what went wrong with the form goes with it
  const close = () => {
    formNow.current = null;
    setForm(null);
    setFailure(null);
  };
  const run = async (key: string, write: () => Promise<void>) => {
    if (saving) return;
    setSaving(true);
    setFailure(null);
    try {
      await write();
    } catch (err: unknown) {
      setFailure({ message: errorMessage(err), key });
    } finally {
      setSaving(false);
    }
  };
  const save = (draft: PlaceDraft, frisianColumns: readonly string[]) => {
    if (!form) return;
    const { key, decision } = form;
    void run(key, async () => {
      await storeEntry(update, createEntry(key, draft, frisianColumns));
      if (decision) await storeEntry(update, { id: key, ...decision });
      if (formNow.current !== key) return;
      close();
      select(key);
    });
  };
  const discard = (key: string) => {
    void run(key, () => storeEntry(update, { id: key, action: 'discard' }));
  };
  const here = form ? form.key : selected;
  const error = failure && failure.key === here ? failure.message : null;
  return { form, saving, error, open, close, save, discard };
}
