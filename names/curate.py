#!/usr/bin/env python3
"""Put the review worklist of names/match.py on the map, and write the answers
back into the name list.

`match.py` leaves two kinds of row for a human: `ambiguous` (several plausible
OSM objects) and `not_found` (no object, or only near misses).  Deciding them
from REPORT.md means looking every candidate up on openstreetmap.org; on a map
the answer is usually obvious at a glance.  So:

    curate.py export  ->  names/work/curate.json   (the worklist, with the
                          candidates' coordinates and the row's location hint)
       the browser (web/, `?curate`, Vite dev server only) shows them as pins
       and appends one decision per line to names/work/curate-patch.jsonl
    curate.py apply   <-  names/work/curate-patch.jsonl

What gets written where
  names/work/curate.json   export: the worklist.  Git-ignored, throw it away
                           and re-export whenever match.py ran again.
  names/places.csv         apply: only `osm`, `wikidata` and `status` of the
                           rows the matcher owns -- the same cells match.py
                           writes, and never a row a human has already decided
                           (status ok/skip, a hand-filled reference, a local
                           reference, `not_a_place`).  Review with `git diff`.
  names/curation.csv       apply: one appended row per `local` decision (a
                           place OSM does not have -- it needs a position).
  names/work/curate-patch.jsonl
                           apply: renamed to `<stamp>.applied.jsonl` before
                           it is read, so that a decision the browser makes
                           meanwhile starts a fresh patch (`--keep` leaves it
                           alone); an entry apply refused is appended back so
                           it is not lost.  If apply fails, the patch is put
                           back.

Apply checks everything first and then writes curation.csv and places.csv, each
in one step and only if it did not change on disk meanwhile; when the second
write fails, the first is undone, so a failed apply changes neither file.
names/work/.lock keeps it from running at the same time as match.py.

The export never builds match.py's full candidate index (180k records, most of
a gigabyte): it streams names/work/candidates.jsonl once and keeps only the
records the worklist actually mentions.

Run:  .venv/bin/python names/curate.py            # = export
      .venv/bin/python names/curate.py apply --dry-run
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import placelist  # noqa: E402
import match  # noqa: E402

CAND_PATH = os.path.join(HERE, "work", "candidates.jsonl")
MATCH_PATH = os.path.join(HERE, "work", "matches.csv")
WORKLIST_PATH = os.path.join(HERE, "work", "curate.json")
PATCH_PATH = os.path.join(HERE, "work", "curate-patch.jsonl")

# The order the browser walks the worklist in: the kinds a human can decide
# quickly first (a village is either there or it is not), the vague ones last.
KIND_ORDER = ["settlement", "island", "hallig", "helgoland", "sand",
              "landscape", "water", "harde", "road", "country", "koog",
              "warft", "not_a_place"]

# The extract (build_candidates.py `src`) the tiles are built from: only its
# objects can carry an injected name, so it is what "in Schleswig-Holstein"
# means for the curation view.  An object near the border can come from both.
SH_SRC = "schleswig-holstein"

RESULTS = ("ambiguous", "not_found")
ACTIONS = ("osm", "local", "skip", "clear")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# The kinds tiles/inject_names.py has a default `place=` for (its POINT_TAGS).
# Kept as a copy rather than imported: that module pulls in osmium, and this
# one only needs to warn that a curation row of any other kind has to carry
# `place=` in `set_tags` before a build.
POINT_KINDS = {"settlement", "warft", "island", "hallig"}

CURATION_COLUMNS = ["osm", "name", "lat", "lon", "set_tags", "minzoom",
                    "maxzoom", "polygon_km2", "note"]


# ------------------------------------------------------------- candidates ---
def parse_candidates(cell: str) -> list[dict]:
    """The `candidates` column of work/matches.csv -> one dict per candidate.

    `match.fmt_cand` writes `type/id:name:class:km` joined by `;` and escapes
    nothing, so a name with a colon in it is only readable from the ends: the
    reference stops at the first colon, class and km are the last two fields.
    (A name with a `;` would still split wrongly -- fmt_cand truncates names to
    40 characters, so that stays a theoretical loss.)
    """
    out = []
    for part in (cell or "").split(";"):
        part = part.strip()
        if not part:
            continue
        head, _, km = part.rpartition(":")
        head, _, cls = head.rpartition(":")
        ref, _, name = head.partition(":")
        t, _, ident = ref.partition("/")
        if t not in placelist.TYPE_NAME or not ident.isdigit():
            print(f"  ignoring unreadable candidate {part!r}", file=sys.stderr)
            continue
        out.append({"key": (t, int(ident)),
                    "ref": f"{placelist.TYPE_NAME[t]}/{ident}",
                    "name": name, "class": cls,
                    "km": int(km) if km.isdigit() else None})
    return out


class _Index:
    """The handful of candidate records the worklist needs, in the shape
    `match.HintResolver` expects (`lookup` is all it calls).  Building it from
    a filtered set of records instead of the whole file is the point: the real
    `match.Index` keeps every name of every candidate in memory."""

    def __init__(self, recs):
        self.recs = list(recs)
        self.by_name = collections.defaultdict(dict)
        self.by_key = {}
        for i, rec in enumerate(self.recs):
            self.by_key[(rec["t"], rec["id"])] = rec
            for k, rank in match.NAME_FIELD_RANK.items():
                v = rec["tags"].get(k)
                if not v:
                    continue
                for part, penalty in match.split_name_values(v):
                    n = match.norm(part)
                    if n and rank + penalty < self.by_name[n].get(i, 99):
                        self.by_name[n][i] = rank + penalty

    def lookup(self, name):
        n = match.norm(name)
        return [(self.recs[i], r) for i, r in self.by_name.get(n, {}).items()] if n else []


def stream_records(path, keys, hint_norms):
    """One pass over work/candidates.jsonl, keeping the records the worklist
    refers to (by id) and those a location hint could name (by normalised
    name) -- roughly a thousand of 180 000."""
    kept = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if (rec["t"], rec["id"]) in keys:
                kept.append(rec)
                continue
            if not hint_norms:
                continue
            for field in match.NAME_FIELDS:
                v = rec["tags"].get(field)
                if v and any(match.norm(p) in hint_norms
                             for p, _pen in match.split_name_values(v)):
                    kept.append(rec)
                    break
    return kept


# ----------------------------------------------------------------- export ---
def cmd_export(args):
    rows, _fields = placelist.read(args.names)
    by_line = {r["_line"]: r for r in rows}
    if not os.path.exists(args.matches):
        raise SystemExit(f"{args.matches} not found -- run names/match.py first")

    work, stale, unowned = [], 0, 0
    with open(args.matches, encoding="utf-8", newline="") as fh:
        for m in csv.DictReader(fh):
            if m["result"] not in RESULTS:
                continue
            row = by_line.get(int(m["line"]))
            # matches.csv is keyed by physical line; a row added or deleted in
            # places.csv since the last match.py run shifts every line below it
            if (row is None or row["kind"] != m["kind"]
                    or placelist.any_name(row) != m["name"]
                    or placelist.primary(row["de"]) != m["de"]):
                stale += 1
                continue
            if not match.owned_by_matcher(row):
                unowned += 1            # decided by hand since the last run
                continue
            work.append((row, m))

    keys, hint_norms = set(), set()
    for row, m in work:
        for c in parse_candidates(m["candidates"]):
            keys.add(c["key"])
        key = match.norm(row["hint"].split(";")[0].strip())
        if key and key not in match.HINT_FALLBACK:
            hint_norms.add(key)

    t0 = time.time()
    index = _Index(stream_records(args.candidates, keys, hint_norms))
    print(f"read {args.candidates}: kept {len(index.recs):,} records "
          f"({len(keys):,} candidates, {len(hint_norms)} hint names, "
          f"{time.time()-t0:.0f}s)")
    hints = match.HintResolver(index)
    srcs = collections.defaultdict(set)
    for rec in index.recs:
        srcs[(rec["t"], rec["id"])].add(rec.get("src"))

    out, n_pos, n_hint = [], 0, 0
    for row, m in work:
        cands = []
        for c in parse_candidates(m["candidates"]):
            key = c.pop("key")
            rec = index.by_key.get(key)
            if rec is not None:
                c.update(lon=rec["lon"], lat=rec["lat"],
                         tags=match.decisive_tags(rec),
                         in_sh=SH_SRC in srcs[key])
                if rec["tags"].get("wikidata"):
                    c["wikidata"] = rec["tags"]["wikidata"]
                if rec["lon"] is not None:
                    n_pos += 1
            else:                       # candidates.jsonl rebuilt since the run
                c.update(lon=None, lat=None, tags="", in_sh=False)
            cands.append(c)
        hint_pt = hints.resolve(row["hint"].split(";")[0].strip())
        if hint_pt:
            n_hint += 1
        out.append({
            "line": row["_line"],
            "kind": row["kind"],
            "result": m["result"],
            "name": placelist.any_name(row),
            "names": {c: row[c] for c in placelist.NAME_COLUMNS if row[c]},
            "de": row["de"], "da": row["da"], "hint": row["hint"],
            "note": row["note"], "why": m["note"],
            "hint_point": list(hint_pt) if hint_pt else None,
            "candidates": cands,
        })
    order = {k: i for i, k in enumerate(KIND_ORDER)}
    out.sort(key=lambda r: (order.get(r["kind"], len(order)), r["line"]))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "bbox": list(match.NF_BBOX),
                   "kind_order": KIND_ORDER,
                   "rows": out}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    cnt = collections.Counter(r["result"] for r in out)
    print(f"wrote {len(out)} rows to {args.out} "
          f"({os.path.getsize(args.out)/1e3:.0f} kB): "
          f"{cnt['ambiguous']} ambiguous, {cnt['not_found']} not found; "
          f"{n_pos} candidates with a position, {n_hint} rows with a hint point")
    if unowned:
        print(f"note: {unowned} row(s) have been decided by hand since "
              f"{os.path.relpath(args.matches, HERE)} was written -- not exported")
    if stale:
        print(f"note: {stale} row(s) no longer match their line in "
              f"{os.path.relpath(args.matches, HERE)} (stale, re-run match.py)")
    return 0


# ------------------------------------------------------------------ apply ---
def patch_key(entry):
    """What makes two patch entries decisions about the same row."""
    return (entry.get("line"), entry.get("kind"), entry.get("name"), entry.get("de"))


def read_patch(path):
    """-> the last entry per row, in line order.  The browser appends, never
    rewrites, so a row decided twice simply has two lines; `clear` withdraws."""
    last = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError as exc:
                print(f"{path}:{n}: not JSON ({exc}) -- ignored", file=sys.stderr)
                continue
            e["_patch_line"] = n
            last[patch_key(e)] = e
    return sorted(last.values(), key=lambda e: (e.get("line") or 0, e["_patch_line"]))


def find_row(entry, rows, by_line):
    """The places.csv row an entry means, or None.

    The `line` is the fast path; it moves as soon as a row is added above, so
    the row's identity (kind + Frisian name + German name) decides.  The
    worklist carries the raw `de` cell, the report and matches.csv its primary
    variant -- either identifies the row."""
    def same(r):
        return (r["kind"] == entry.get("kind")
                and placelist.any_name(r) == entry.get("name")
                and entry.get("de") in (r["de"], placelist.primary(r["de"])))

    row = by_line.get(entry.get("line"))
    if row is not None and same(row):
        return row
    hits = [r for r in rows if same(r)]
    return hits[0] if len(hits) == 1 else None


def curation_name(row):
    """The free-text label of the appended curation row -- German, else Danish,
    else Frisian, plus the hint, so the file stays readable by a human."""
    name = (placelist.primary(row["de"]) or placelist.primary(row["da"])
            or placelist.any_name(row))
    return f"{name} ({row['hint']})" if row["hint"] else name


def fmt_deg(v):
    return f"{v:.6f}".rstrip("0").rstrip(".")


def cmd_apply(args):
    with placelist.lock(args.names):
        return _apply(args)


def _apply(args):
    # Everything that can refuse the whole run is checked before the patch is
    # touched: the name list, and curation.csv (read once, kept as bytes, so
    # the rows appended to it land after exactly what was checked).
    rows, fields = placelist.read(args.names)
    by_line = {r["_line"]: r for r in rows}
    used_slugs = set(placelist.local_points(args.curation))
    cur_data, cur_fields = read_curation(args.curation)
    cur_digest = placelist.digest(cur_data) if cur_data is not None else placelist.MISSING
    for r in rows:
        slug = placelist.local_ref(r["osm"])
        if slug:
            used_slugs.add(slug)

    if not os.path.exists(args.patch):
        raise SystemExit(f"{args.patch} not found -- decide some rows in the "
                         f"browser first (web/, `?curate`)")
    snapshot = None
    if args.dry_run or args.keep:
        source = args.patch
    else:
        # Take the patch out of the browser's way first, then read it: the dev
        # server appends with O_APPEND, so a decision made from now on starts
        # a fresh patch file instead of landing in one that is being archived.
        stamp = time.strftime("%Y%m%d-%H%M%S")
        root, ext = os.path.splitext(args.patch)
        snapshot = source = f"{root}.{stamp}.applied{ext}"
        os.rename(args.patch, snapshot)

    cur_written = None                   # digest of the curation.csv apply wrote
    try:
        entries = read_patch(source)
        applied, refused, new_curation = 0, 0, []
        kept_back = []                   # refused entries survive the archiving

        def refuse(entry, why):
            nonlocal refused
            refused += 1
            kept_back.append(entry)
            print(f"  refused patch line {entry['_patch_line']} "
                  f"({entry.get('name')} / {entry.get('de')}): {why}")

        for e in entries:
            action = e.get("action")
            if action == "clear":
                continue                     # withdrawn in the browser
            if action not in ACTIONS:
                refuse(e, f"unknown action {action!r}")
                continue
            row = find_row(e, rows, by_line)
            if row is None:
                refuse(e, f"no row at line {e.get('line')} with this kind/name/de "
                          f"(re-run names/curate.py export)")
                continue
            where = f"{args.names}:{row['_line']}"
            if not match.owned_by_matcher(row):
                refuse(e, f"{where} is not the matcher's to fill "
                          f"(status={row['status'] or 'empty'}, osm={row['osm'] or '-'})")
                continue

            if action == "skip":
                print(f"  {where} {placelist.describe(row)}: status = skip")
                row["status"] = "skip"
            elif action == "osm":
                try:
                    refs = placelist.parse_osm(e.get("osm"), where)
                except SystemExit as exc:
                    refuse(e, str(exc))
                    continue
                if not refs:
                    refuse(e, "action=osm without an `osm` reference")
                    continue
                if any(t == placelist.LOCAL_TYPE for t, _ in refs):
                    refuse(e, "a local reference is action=local, not action=osm")
                    continue
                qid = (e.get("wikidata") or "").strip()
                if qid and not re.fullmatch(r"Q\d+", qid):
                    refuse(e, f"bad wikidata id {qid!r}")
                    continue
                row["osm"] = placelist.format_osm(refs)
                if qid:
                    row["wikidata"] = qid
                row["status"] = "ok"
                print(f"  {where} {placelist.describe(row)}: osm = {row['osm']}"
                      + (f", wikidata = {qid}" if qid else "") + ", status = ok")
            else:                            # local: a place OSM does not have
                slug = (e.get("slug") or "").strip()
                if not SLUG.fullmatch(slug):
                    refuse(e, f"bad slug {slug!r} (lowercase letters, digits, hyphens)")
                    continue
                if slug in used_slugs:
                    refuse(e, f"local/{slug} is already taken")
                    continue
                try:
                    pos = placelist.parse_point(str(e.get("lat", "")),
                                                str(e.get("lon", "")),
                                                f"patch line {e['_patch_line']}")
                except SystemExit as exc:
                    refuse(e, str(exc))
                    continue
                if pos is None:
                    refuse(e, "action=local needs `lat` and `lon`")
                    continue
                km2 = e.get("polygon_km2")
                if km2 is not None:
                    try:
                        km2 = float(km2)
                    except (TypeError, ValueError):
                        refuse(e, f"polygon_km2 {km2!r} is not a number")
                        continue
                    if km2 <= 0:
                        refuse(e, f"polygon_km2 {km2} must be positive")
                        continue
                lon, lat = pos
                row["osm"] = f"local/{slug}"
                row["wikidata"] = ""
                row["status"] = "ok"
                used_slugs.add(slug)
                cur = {c: "" for c in CURATION_COLUMNS}
                cur.update(osm=row["osm"], name=curation_name(row),
                           lat=fmt_deg(lat), lon=fmt_deg(lon),
                           note=(e.get("note") or "").strip())
                if km2 is not None:
                    # the README's Koog route: no labelled node, only a square of
                    # that area -- and OpenMapTiles labels a polygon only as island
                    cur.update(polygon_km2=f"{km2:g}", set_tags="place=island")
                new_curation.append(cur)
                print(f"  {where} {placelist.describe(row)}: osm = {row['osm']}, "
                      f"status = ok; {args.curation} += {cur['lat']}/{cur['lon']}"
                      + (f", polygon_km2 = {cur['polygon_km2']}" if km2 is not None else ""))
                if km2 is None and row["kind"] not in POINT_KINDS:
                    print(f"    warning: kind={row['kind']} has no default `place=` "
                          f"in tiles/inject_names.py -- put one into the curation "
                          f"row's `set_tags` before the next build")
            applied += 1

        if args.dry_run:
            print(f"dry run: {applied} row(s) would change, "
                  f"{len(new_curation)} curation row(s) would be appended, "
                  f"{refused} refused -- nothing written")
            return 1 if refused else 0

        if applied:
            # curation.csv first, places.csv last: when the places.csv write
            # fails (a spreadsheet saved it meanwhile, say), the curation rows
            # come out again, so a `local/<slug>` row never lands without its
            # position and a failed apply leaves both files as they were
            if new_curation:
                cur_text = curation_text(cur_data, cur_fields, new_curation)
                placelist.atomic_write(args.curation, cur_text, expect=cur_digest)
                cur_written = placelist.digest(cur_text)
            placelist.write(rows, args.names, fields)
    except BaseException:
        if cur_written:
            unwrite_curation(args.curation, cur_data, cur_written,
                             [c["osm"] for c in new_curation])
        if snapshot:
            restore_patch(snapshot, args.patch)
            print(f"nothing applied -- {args.patch} restored", file=sys.stderr)
        raise

    if snapshot:
        print(f"patch applied, moved to {snapshot}")
        if kept_back:
            # a refused decision is not lost: it goes back into the patch (and
            # so stays "done" in the browser) until fixed or cleared
            n = append_back(args.patch, kept_back)
            print(f"{n} refused entr{'y' if n == 1 else 'ies'} kept in {args.patch}"
                  + (f" ({len(kept_back) - n} decided again in the browser meanwhile)"
                     if n < len(kept_back) else ""))
    print(f"{applied} row(s) written to {args.names}, "
          f"{len(new_curation)} appended to {args.curation}, {refused} refused")
    return 1 if refused else 0


def append_back(path, entries):
    """Append refused entries to the live patch -- appending, never
    rewriting, because the dev server may be appending to it too.  An entry
    whose row has been decided again since then is dropped: the newer
    decision wins, as it would in `read_patch`.  -> how many were appended."""
    newer = set()
    ends_nl = True
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        ends_nl = not text or text.endswith("\n")
        for line in text.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict):
                newer.add(patch_key(e))
    lines = [json.dumps({k: v for k, v in e.items() if k != "_patch_line"},
                        ensure_ascii=False) + "\n"
             for e in entries if patch_key(e) not in newer]
    if lines:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(("" if ends_nl else "\n") + "".join(lines))
    return len(lines)


def restore_patch(snapshot, path):
    """Undo taking the snapshot after a failed apply: the snapshot becomes the
    patch again, followed by whatever the browser appended in the meantime."""
    while True:
        try:
            os.link(snapshot, path)          # unlike rename, never overwrites
            os.unlink(snapshot)
            return
        except FileExistsError:
            pass
        # the browser started a new patch: move it aside (the next pick starts
        # yet another, hence the loop) and put its entries after the old ones
        newer = f"{snapshot}.newer"
        os.rename(path, newer)
        with open(newer, "rb") as fh:
            text = fh.read()
        with open(snapshot, "rb") as fh:
            old = fh.read()
        with open(snapshot, "ab") as fh:
            fh.write((b"" if not old or old.endswith(b"\n") else b"\n") + text)
        os.unlink(newer)


def read_curation(path):
    """-> (the file's bytes or None when it does not exist, its columns).  The
    columns are the file's own (it is hand-edited, so it may have gained one);
    the ones apply writes must be among them."""
    if not os.path.exists(path):
        return None, CURATION_COLUMNS
    with open(path, "rb") as fh:
        data = fh.read()
    fields = next(csv.reader(io.StringIO(data.decode("utf-8"), newline="")), None)
    fields = fields or CURATION_COLUMNS
    missing = [c for c in CURATION_COLUMNS if c not in fields]
    if missing:
        raise SystemExit(f"{path}: missing column(s) {missing}")
    return data, fields


def curation_text(data, fields, new_rows):
    """The whole new curation.csv: the old bytes untouched, the rows for the
    places OSM does not have appended in the file's column order."""
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n",
                       extrasaction="ignore")
    if data is None:
        w.writeheader()
        data = b""
    elif data and not data.endswith(b"\n"):
        data += b"\n"
    for r in new_rows:
        w.writerow({k: r.get(k, "") for k in fields})
    return data + buf.getvalue().encode("utf-8")


def unwrite_curation(path, old, written, refs):
    """Undo apply's curation.csv write after the places.csv write failed: put
    back `old` (its bytes before; None = there was no file), unless someone
    changed the file after apply wrote it (`written`, its digest) -- then say
    which rows to take out by hand."""
    try:
        if old is not None:
            placelist.atomic_write(path, old, expect=written)
        elif placelist.fingerprint(path) == written:
            os.unlink(path)
        else:
            raise placelist.Conflict(f"{path} changed on disk meanwhile")
    except (OSError, SystemExit) as exc:
        print(f"error: could not take the new rows out of {path} again ({exc}) "
              f"-- delete the rows for {', '.join(refs)} by hand before the next "
              f"apply", file=sys.stderr)
    else:
        print(f"{path} put back as it was", file=sys.stderr)


# ------------------------------------------------------------------- main ---
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in ("export", "apply", "-h", "--help")):
        argv.insert(0, "export")         # export is what one runs every time
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="write the worklist for the browser")
    ex.add_argument("--names", default=placelist.DEFAULT_PATH)
    ex.add_argument("--matches", default=MATCH_PATH)
    ex.add_argument("--candidates", default=CAND_PATH)
    ex.add_argument("--out", default=WORKLIST_PATH)
    ex.set_defaults(func=cmd_export)

    ap_ = sub.add_parser("apply", help="write the browser's decisions back")
    ap_.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap_.add_argument("--curation", default=placelist.CURATION_PATH)
    ap_.add_argument("--patch", default=PATCH_PATH)
    ap_.add_argument("--dry-run", action="store_true",
                     help="print what would change and write nothing")
    ap_.add_argument("--keep", action="store_true",
                     help="do not rename the patch file after applying it")
    ap_.set_defaults(func=cmd_apply)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
