// The browser's side of the curation patch (names/work/curate-patch.jsonl):
// what one decision looks like, and which rows are decided.

/** One line of `names/work/curate-patch.jsonl`. */
export interface PatchEntry {
  /** The places.csv row's `id` — what names/curate.py apply finds the row by. */
  id: string;
  /** Its line in places.csv when the worklist was exported; for messages only. */
  line: number;
  kind: string;
  name: string;
  de: string;
  action: 'osm' | 'local' | 'skip' | 'clear';
  osm?: string;
  wikidata?: string;
  slug?: string;
  lat?: number;
  lon?: number;
  polygon_km2?: number;
  note?: string;
  at?: string;
}

/**
 * The decided rows: the last entry per row id, as names/curate.py apply reads
 * the patch. A `clear` entry withdraws the row's decision.
 */
export function decidedRows(entries: PatchEntry[]): Map<string, PatchEntry> {
  const last = new Map<string, PatchEntry>();
  for (const entry of entries) last.set(entry.id, entry);
  for (const [id, entry] of last) {
    if (entry.action === 'clear') last.delete(id);
  }
  return last;
}
