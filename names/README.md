# names/ — the North Frisian name list

**`names/places.csv` is the single source of truth** for every Frisian label on
the map. It is a plain CSV you edit by hand (any text editor, VS Code's CSV
extensions, or LibreOffice — just save as UTF-8 CSV again). Everything else in
this directory either helps fill it in or is generated from it.

```
names/places.csv         THE name list (hand-edited, in git)
names/dialects.csv       THE dialect registry (hand-edited, in git)
names/dialect_areas.csv  which OSM municipalities/islands speak which dialect
names/curation.csv       per-OSM-object map tuning (hand-edited, in git)
        |
        |  match.py          fills empty `osm` cells, marks them status=auto
        |  <- work/candidates.jsonl <- build_candidates.py <- tiles/data/*.osm.pbf
        |
        |  build_dialect_areas.py  ->  names/dialect_areas.geojson (in git)
        v
names/REPORT.md          generated worklist: what is still unmatched
names/work/matches.csv   generated details of the last match run (git-ignored)
        |
        |  export_search_index.py  ->  web/public/data/names.json
        |                          ->  web/src/generated/dialects.json
        |  tiles/inject_names.py   ->  tags in the OSM extract  ->  tiles
```

`names/bootstrap/` holds the one-time import from the original Google Sheet
(September 2026). The sheet is history; do not edit it expecting the map to
change.

## `places.csv` columns

| column | meaning |
|---|---|
| `kind` | `settlement`, `koog`, `harde`, `island`, `hallig`, `sand`, `warft`, `landscape`, `water`, `road`, `country`, `helgoland`, or `not_a_place` (dictionary-only rows such as *Håli*, *bütenlönj*). Decides which OSM objects count as a match and becomes the tile attribute `frasch:kind`. |
| `mooring` | the Mooring name(s). **The first one is the map label** in the Mooring view. |
| `local` | the form the people of the place **itself** use where it differs from the dialect of the area around it (sub-dialects such as Fahretoft's *Foortuftinge*). Empty means "same as the area's dialect". The bracket remark names the variety and becomes the tile attribute `frasch:variety`: `Brouersweerw (Foortuftinge)`. |
| one column per dialect | `wieding`, `karrhard`, `nordgoes`, `midgoes`, `suedgoes`, `fering`, `oomrang`, `solring`, `hallig`, `halunder` — the names in that dialect. **The column list comes from `dialects.csv`**, see below; the old catch-all `other` column is gone (see *Migration*). |
| `de` | German name(s). What the matcher searches for in OSM. |
| `hint` | where the feature is, for matching: `Langeness`, `Ockholm`, `bei Leck`. Binding — a hint that matches nothing sends the row to review. |
| `da` | Danish name(s). Used for matching when there is no German name. |
| `osm` | the OSM object(s) that carry the label: `node/123`, `way/123`, `relation/123`. Several separated by `;` when OSM splits a river or dyke into pieces: `way/1; way/2`. A place **OSM does not have** carries a local reference instead: `local/<slug>` (lowercase ascii letters, digits, hyphens) alone in the cell, e.g. `local/westerheide-amrum` — never mixed with a real reference, never split by `;`. See *Places OSM does not have*. |
| `wikidata` | Wikidata item. The injector also tags every OSM object with this `wikidata` tag; for the countries, which have no `osm`, it is the only key. Empty for a `local/` row. |
| `status` | `auto` — `match.py` filled `osm`/`wikidata` and will recompute them next run. `ok` — a human checked the row. `skip` — never put on the map. Empty — nothing decided yet (or, with `osm` filled by hand, simply yours). |
| `note` | free text for you. `match.py` never writes here. The import put `uncertain` here for names the sheet marked with `?`. |

The sheet's other columns (inhabitant adjectives, Low German, South Jutish,
old names, sources) were deliberately not imported: the map does not use them.
They are still in `bootstrap/sheet-export.csv`.

Conventions that apply to every name cell:

* several variants are separated by `;` — the first one is the primary name
  (a `;` inside a remark does not split anything: `Huađer; Huuger (Sölring;
  Wisinge)` is two names)
* `(…)` after a variant is a remark about it (a local variety such as
  `(Foortuftinge)`, a source) and is never part of the name. A remark that
  only repeats the column's own dialect is noise — the column says it already
* no `?` inside names — say `uncertain` in `note`

The rows are in the order of the original sheet (by section, then the owner's
geographic order); new rows can go anywhere.

## `dialects.csv` — the dialect registry

One line per dialect, and the **only** place the project lists them. The
columns of `places.csv`, the `name:*` tags the injector writes, Planetiler's
`--languages`, the search index and the frontend's language selector all
derive from it, so adding a dialect is one line here plus a column in
`places.csv` — no code change.

| column | meaning |
|---|---|
| `tag` | the BCP 47 language tag, always `frr-x-<subtag>` (no registered subtags for North Frisian dialects exist; a private-use subtag is at most 8 characters) |
| `column` | the `places.csv` column holding this dialect's names |
| `label` | how the dialect is written in the UI |
| `status` | `living` or `extinct` — Südergoesharde died in 1981, its names still label the local view |
| `view` | `yes` = selectable as a map language in the frontend. Today only Mooring: a dialect becomes selectable when its UI translation exists |
| `note` | free text: which area speaks it |

```bash
$PY names/dialects.py            # print the registry
$PY names/dialects.py --tags     # frr-x-mooring,frr-x-wieding,...  (tiles/build.sh)
```

The shared name logic lives in `dialects.py` next to the reader, because
injector, exporter and frontend must agree on it:

* **the name of a place in dialect T** = its column, else — if T is the
  dialect of the area the place lies in — `local`
* **the local name** = `local`, else the name in the dialect of the area
* **the variety** = the bracket remark on the primary `local` variant

## Dialect areas — `dialect_areas.csv` → `dialect_areas.geojson`

Which dialect is spoken *where* is a question about areas, not about single
places: a Warft on Hallig Hooge is Halligfriesisch even when nobody wrote that
down, and without it the map cannot know that *Hansweerf* is the local name
and *Hanswärw* the foreign one.

`dialect_areas.csv` is the hand-edited answer: one line per OSM object that
belongs to a dialect.

| column | meaning |
|---|---|
| `dialect` | a `tag` from `dialects.csv` |
| `osm` | `relation/123` (a municipality) or `way/123` (an island polygon where the municipality is the wrong unit); several separated by `;`, as in `places.csv` |
| `name` | free-text label so a human can read the row |
| `note` | why this object |

The island rows are certain. The mainland rows (81 municipalities of Kreis
Nordfriesland, assigned to the six Harden by historic membership from German
Wikipedia, 2026-09-16) are a **draft**: the `note` column carries `high`,
`medium` or `low` with the reason, and every `medium`/`low` row deserves a
look — particularly the Gotteskoog border villages (Holm, Uphusum, Lexgaard,
Braderup, Galmsbüll). Move a municipality by changing its `dialect` cell and
re-running the build script below. Nordstrand, Pellworm, Eiderstedt, Husum and
Friedrichstadt deliberately have no row: no living or historic Frisian dialect
is assigned there, so the local view shows Low Saxon.

**The smallest area containing a point wins**, so a small exception inside a
larger area is simply another row: the Hamburger Hallig (Halligfriesisch) lies
inside the municipality Reußenköge, Nordstrandischmoor inside a Nordstrand
that has no Frisian area at all.

```bash
$PY names/build_dialect_areas.py tiles/data/schleswig-holstein-latest.osm.pbf
```

assembles the polygons (three id-filtered passes, ~2 s, no location cache),
unions them per dialect, simplifies to ~50 m and writes
`names/dialect_areas.geojson` — **committed**, because every build and the
search export need it and a planet build must not re-extract boundaries.
Re-run it when `dialect_areas.csv` changes or when a boundary in OSM moved;
a Schleswig-Holstein extract covers every Frisian area there is. The report
lists every area with its polygon count and size, and every referenced object
that is not in the extract.

The same run also writes `names/dialect_areas_parts.geojson` (`--parts-out`):
one Feature per *municipality* rather than per dialect, carrying the row's
`name` and research `note`, plus every Kreis Nordfriesland municipality that no
row claims, marked `assigned: false`. It exists for the review overlay in the
web app (`?areas`, see `web/README.md`) and is simplified finer, to 0.0001°
(~11 m), because neighbours are simplified independently and at 50 m the cracks
between two municipalities that actually touch become visible. Committed, for
the same reason as the dissolved file. `--no-unassigned` skips the extra
relation scan.

**No Python consumer may read the parts file.** Its unit is the municipality,
not the dialect, so handing it to `dialects.AreaIndex` would silently change
every dialect lookup. The unassigned features deliberately carry no `dialect`
property, which makes `AreaIndex.from_geojson` refuse the file outright rather
than load it by accident.

## Migration from the old `other` and `older` columns

Until 2026-09-16 every non-Mooring name lived in one `other` column with its
dialect as a bracket remark (`Fuan (Sölring)`), and `older` ("older Mooring
spellings" from the sheet's *Oudere noome* column) held Karrharder and
Wiedingharder names with remarks, and, without any remark, the island
dialects' own names — Sölring forms with đ and ā for Sylt, Fering for Föhr,
Halunder for Helgoland. Two one-off scripts, kept as history next to
`import_sheet.py`, dissolved both columns:

`bootstrap/migrate_dialect_columns.py` sorted the remarked variants into the
new columns (safe to re-run: a no-op on a migrated file). Two tables inside it
hold the decisions that the data could not answer:

* `GOESHARDE_BY_DE` — a `(Gooshiirdinge)` remark does not say *which* of the
  three Goesharden; the table says where the place lies.
* `OTHER_OVERRIDES` — variants that had no remark at all. Anything unsorted
  went into `note` as `unsorted other-dialect name: …` rather than being
  dropped; `git grep "unsorted other-dialect" names/places.csv` lists what is
  still waiting for a decision.

`bootstrap/drop_older_column.py` then removed `older` altogether (owner's
decision): a name in an island or Hallig area went into that dialect's column;
a name in another mainland Harde went into that Harde's column when OSM's
`name:frr` for the object uses the same form (evidence that locals write it);
everything else counted as an alternative Mooring spelling — it became the
Mooring name where `mooring` was empty and was dropped where `mooring` was
already filled (144 spellings; `bootstrap/sheet-export.csv` still has them).
Its report lists every cell.

That step also revealed a loss: before the first commit the owner's clean-up
had stripped bracket remarks, so `Ualöön (Hålifrasch)` had become plain
`Ualöön` and was dropped as a Mooring spelling. A comparison of the sheet
export with the committed and the current list (2026-09-17) produced
`bootstrap/restore_proposal.csv` — every Frisian name the sheet has and the
list no longer has, with a suggested column, confidence and reason — and
`bootstrap/restore_review.csv`, an independent linguistic second opinion.
`bootstrap/restore_deleted_names.py` applies the proposal (edit the CSV first
if you disagree; `--dry-run`, `--min-confidence`, `--only-agreed`), appending
each name as a further variant of the target column. Rows the owner deleted
altogether are never re-created.

## Workflow

**Add or fix a name**: edit `places.csv`, save. Fill `osm` yourself if you
know the object (open it on openstreetmap.org and read the URL:
`openstreetmap.org/way/177387348` → `way/177387348`), otherwise leave it empty
and let the matcher try.

**Let the matcher fill the blanks**:

```bash
cd /home/thore/Repos/frasch-maps
PY=.venv/bin/python

# once per OSM extract (~6 min for SH + DK, ~250 MB, git-ignored)
$PY names/build_candidates.py tiles/data/schleswig-holstein-latest.osm.pbf \
                             tiles/data/denmark-latest.osm.pbf

$PY names/match.py            # --offline skips the Wikidata API (countries)
git diff names/places.csv     # review what it filled in
```

`match.py` only ever rewrites the `osm`, `wikidata` and `status` cells of rows
it owns: rows whose `osm` and `wikidata` are both empty, and rows it filled
earlier (`status=auto`). A row you filled in, marked `ok` or `skip`, or a
`not_a_place` row is never touched, so re-running is always safe. Undo a
single row with `git checkout -p`.

**Review**: `names/REPORT.md` lists the *ambiguous* rows with their candidates
and the *not found* rows with near misses. Resolve a row by writing the right
`osm` reference into `places.csv` (and `ok` into `status` if you like), or
`skip` if it should never appear.

**Review on the map** — the same worklist as pins, which is usually faster
than looking every candidate up on openstreetmap.org:

```bash
$PY names/curate.py export     # -> work/curate.json (needs a match.py run)
cd web && npm run dev          # then open /?curate -- dev server only
$PY names/curate.py apply --dry-run
$PY names/curate.py apply
```

`export` writes every ambiguous and not-found row the matcher still owns, with
its candidates' positions and its location hint, to `work/curate.json`; rows
whose line has moved since the match run are dropped with a note (re-run
`match.py`). In the browser you pick a candidate, drop a point of your own, or
`skip` the row; every decision is appended as one line to
`work/curate-patch.jsonl`, so you can stop and resume. `apply` reads that file
back — the last entry per row wins — and writes `osm`, `wikidata` and
`status` (`ok`, or `skip`) into `places.csv`, plus one `curation.csv` row per
place OSM does not have. It touches only the rows `match.py` owns and refuses
the rest, then renames the patch file (`--keep` leaves it). Re-run `match.py`
afterwards and export again.

**Build**:

```bash
# only when dialect_areas.csv changed (result is committed)
$PY names/build_dialect_areas.py tiles/data/schleswig-holstein-latest.osm.pbf

$PY names/export_search_index.py   # -> web/public/data/names.json (needs a match.py run)
                                   # -> web/src/generated/dialects.json
tiles/build.sh schleswig-holstein  # injects places.csv + areas + curation.csv, runs Planetiler
```

Dry-run the injection alone:

```bash
$PY tiles/inject_names.py tiles/data/schleswig-holstein-latest.osm.pbf /dev/null --dry-run
```

It lists how many names it writes per dialect, how many objects fall into each
dialect area, ids that are not in the extract, rows that claim the same object
twice (the first row in file order wins, per tag), QIDs it could not find, and
the synthetic polygons it would add.

## Matching rules (v1)

* **Exact** comparison after normalisation only — case, whitespace,
  hyphen↔space, `ß`↔`ss`, `ä`↔`ae`/`ö`↔`oe`/`ü`↔`ue`, `å`↔`aa`, `ø`/`æ`.
  No fuzzy matching: a wrong Frisian label is worse than a missing one.
* Compared against `name`, `name:de`, `name:da`, `short_name`,
  `official_name`, `alt_name`, `old_name` (and the parts of multilingual
  `A / B / C` name values).
* A hit on the OSM `name` outranks one on `name:de`, which outranks
  `short_name`/`official_name`, which outrank `alt_name`/`old_name` —
  otherwise the Danish village *Holme* (`name:de=Holm`) would beat the North
  Frisian village *Holm*.
  OSM's own annotations are indexed as lower-ranked variants:
  `Kampen (Sylt)` also answers to *Kampen*, `Kreis Dithmarschen` to
  *Dithmarschen*, `Wyk auf Föhr` to *Wyk*. Compound splitting is **not**
  done: `Gotteskoogsee` does not match OSM's `Gotteskoog See`.
* Candidates are filtered by **kind compatibility**, reduced to the canonical
  object where OSM has one (the `type=waterway` relation of a river, the
  `place=island` polygon of a Hallig, the place node rather than a dyke or a
  street of the same name), then clustered: 3 km for point features, 30 km for
  the pieces of a river, and two settlement nodes more than 1 km apart are
  never the same village.
* A row is matched when there is one cluster, when the row's `hint` picks
  exactly one cluster, or when exactly one cluster lies inside North Frisia
  and every rival is more than 30 km away. A hint is **binding**: if the list
  says *Morsum* with hint *Nordstrand* and OSM's only Morsum is on Sylt, the
  row goes to review instead of matching.
* A Koog/Warft/Hallig/street matched outside North Frisia, or a far-away
  hamlet/isolated dwelling, is left for review even when it is the only
  candidate.
* For settlements the **place node** wins over the boundary relation (that is
  what OpenMapTiles labels); the relation's `wikidata` is still recorded.
* A row is matched as soon as **any** dialect column (or `local`) has a name;
  which dialect it is does not matter for matching.
* **Countries** are keyed by Wikidata QID only (via `wbsearchentities` +
  `wbgetentities`, filtered to country / sovereign-state classes);
  `inject_names.py` tags whatever object carries that QID.

## Places OSM does not have

Most of the list is matched to an OSM object. Some places have none — a Harde,
most Köge, a vanished Hallig, a Warft or a hamlet nobody has mapped
(*Waasterhias* near Nebel on Amrum was the first). Such a row gets a **local
reference** instead of an OSM id: `local/<slug>` alone in the `osm` cell
(e.g. `local/westerheide-amrum`), `wikidata` left empty.

The position lives in `curation.csv`, not in `places.csv`: a curation row
keyed by the same local reference carries `lat`/`lon` (decimal degrees, from
OSM or any map) — mandatory for a local reference, and empty for every row
with a real `osm` reference. One local reference, one row per file.

* **Without `polygon_km2`**, `tiles/inject_names.py` adds a **new node** at
  `lat`/`lon` to the extract it writes (id above the extract's highest node
  id, written before the first way — like the synthetic polygon nodes),
  tagged with the row's `name:<dialect>` / `frasch:*` tags, `name` = the
  German name (else Danish, else any Frisian name — OpenMapTiles drops a
  nameless place node), and a default `place=` value from `kind`
  (`POINT_TAGS` in that file: `settlement`/`warft` → `hamlet`, `island` /
  `hallig` → `island`; a `kind` with no default needs `place=` in the
  curation row's `set_tags`, or the build stops). The curation row's
  `set_tags`/`minzoom`/`maxzoom` are applied last, so `set_tags` can override
  `place=` or `frasch:kind`. (The warft default is `hamlet`, not
  `isolated_dwelling`: OpenMapTiles gives `isolated_dwelling` nodes z14 but
  `hamlet` nodes z11, the style's Warft layer starts at z13, and OSM's own
  Hallig Warften are `place=hamlet` already.)
* **With `polygon_km2`**, no labelled node is written at all — only the
  synthetic square of that area centred on `lat`/`lon` (as for an OSM node's
  square, see *`curation.csv`* below), carrying the name / `frasch:*` tags
  plus the row's `set_tags`/`minzoom`/`maxzoom`. This is the route for an
  area-like place (a Koog) that should be labelled from a lower zoom than a
  node would get.

So a local reference is either a point label (node) or an area label
(square), decided by whether its curation row carries `polygon_km2`. The
square carries the row's `frasch:kind` and must end up with `place=island`
(the `island`/`hallig` default, or `place=island` in `set_tags` for a Koog):
OpenMapTiles takes hamlets and villages from *points* only, so any other
`place=` on a polygon would label nothing — the loader stops the build
instead.

`export_search_index.py` takes the position of a local-reference row from
`curation.csv` (`--curation`, default `names/curation.csv`) and uses the
local reference itself, e.g. `local/westerheide-amrum`, as the entry's stable
`id`.

`match.py` leaves a row with a local reference alone (`own point` in
`REPORT.md`).

The loader stops the build if: a local reference used by a `places.csv` row
the injector puts on the map (not `skip`, not `not_a_place`, with a Frisian
name) has no curation row; a curation row with a local reference lacks
`lat`/`lon`; the same local reference appears twice in `curation.csv`; the
node has no `place=` (a `kind` without a default and no `place=` in
`set_tags`); a square would not be `place=island`.
A curation local row that no `places.csv` row uses is reported and ignored —
no nameless node is written for it.

Nothing is uploaded to OSM; the node or square exists only in the tiles this
repo builds. If OSM later gains the object, write its id into `places.csv`'s
`osm` and delete or re-key the curation row.

First use: Westerheide on Amrum (Öömrang *Waasterhias*, near Nebel) —
`places.csv`: `osm = local/westerheide-amrum`; `curation.csv`:
`local/westerheide-amrum,Westerheide (Amrum),54.65097,8.34019,,,,,nicht in
OSM (Waasterhias bei Nebel); Lage von Hand gesetzt`.

## `curation.csv` — per-feature map tuning

The name list says *what a place is called*. `curation.csv` says *how the map
should treat one particular OSM object* — and it works for objects that have no
Frisian name at all (the village Tilli, the sand Japsand), so it is deliberately
a separate file with its own identity: the OSM reference, nothing else. A row
keyed by a local reference (`local/<slug>`, the same one in `places.csv`'s
`osm` column) instead *creates* the object it tunes — a node or, with
`polygon_km2`, a square — at the row's `lat`/`lon`; see *Places OSM does not
have* above.

| column | meaning |
|---|---|
| `osm` | `node/123`, `way/123`, `relation/123`; several separated by `;`, as in `places.csv` — or a local reference `local/<slug>` matching a `places.csv` row |
| `name` | free-text label so a human can read the row — **not** written to the data |
| `lat`, `lon` | decimal degrees — mandatory for a local reference (the position of the node/square it creates), empty for a real OSM reference |
| `set_tags` | `k=v` pairs separated by `;`, e.g. `place=island;frasch:kind=island` |
| `minzoom` | integer, or empty |
| `maxzoom` | integer, or empty — the last zoom (inclusive) the label is shown at |
| `polygon_km2` | number, or empty — add a synthetic label polygon of this area around the node in `osm` (see below) |
| `note` | why the row exists |

### The two columns do very different things

* **`set_tags` runs BEFORE Planetiler.** `inject_names.py` writes these tags
  into the OSM extract, so they change how the stock OpenMapTiles profile
  *classifies* the feature. That is the only lever for things the profile
  decides itself: OMT emits island labels for `place=island` polygons and drops
  `place=islet` polygons entirely, so the Halligen Habel, Norderoog and Südfall
  — which OSM tags `place=islet` — get no label at all until `set_tags` promotes
  them to `place=island`. `set_tags` is applied **verbatim and last**, after the
  name list, so it can override `frasch:kind` or any other tag.
* **`minzoom` only becomes a tile attribute.** It is written as the tag
  `frasch:minzoom` (a string, like every OSM tag) and rides through Planetiler
  via `--extra_name_tags`. Planetiler still places the feature at whatever zoom
  the OMT profile chose — **the style has to enforce it**, e.g. by hiding a
  label whose `frasch:minzoom` is greater than the current zoom. Use it to push
  a label *later*, not to make one appear earlier: a label the profile never
  emitted at z8 cannot be conjured up by an attribute.
* **`maxzoom`** is the mirror image: it becomes `frasch:maxzoom`, the last zoom
  at which the style shows the label.
* **`polygon_km2`** adds a **synthetic polygon** to the extract instead of
  changing the node: a square of that area centred on the node, carrying the
  node's `name` / `name:*` tags (after the node's own curation) plus the row's
  `set_tags`, `minzoom` and `maxzoom`. The node itself is untouched, so it can
  have its own row. Why: OpenMapTiles labels `place=island` *nodes* only from
  z12, but *polygons* from z8–10 depending on their area, and Planetiler puts a
  polygon's label at its interior point — for a square, its centre. So this is
  the lever for a landform that has no polygon in OSM but should be labelled
  at a chosen point from a low zoom. Nordstrand is the case: it is a peninsula
  now, so no island polygon exists; using the municipality boundary instead
  put the label 2 km from the village. Now a 50 km² square (about the real
  area, which is what sets OMT's rank and first zoom) sits on the village node,
  carries "e Strönj" as an island through z11 (`maxzoom=11`), and the village
  node, held to z12, takes over at the same spot. The square is only ever a
  label carrier: `place=island` feeds nothing but the place layer. For a local
  reference — no OSM node to centre on — the square is centred on the curation
  row's own `lat`/`lon` instead, and no node is written at all; see *Places
  OSM does not have*.

`frasch:kind` comes from the name list (`places.csv`'s `kind` column) for every
injected row; `set_tags` is how an object the list does not mention gets one.

`tiles/build.sh` passes the file to `inject_names.py` automatically;
`--no-curation` ignores it, `--curation OTHER.csv` swaps it.

## License

The name list, **"Frasche stääsnoome"** (`places.csv`, `dialects.csv`, `dialect_areas.csv`,
`dialect_areas.geojson`, `curation.csv`) is published under the **Open
Database License (ODbL) 1.0**, see `names/LICENSE` (decided 2026-09-19).
Attribution: "Frasche stääsnoome, Thore Andresen, ODbL 1.0". Share-alike: an
extended or merged version of the list must be published under ODbL too; a
map drawn from it only needs the attribution. The tiles are ODbL in any case
(derived from OpenStreetMap). ODbL data can go into OpenStreetMap without a
waiver; Wikidata (CC0) cannot take it from third parties, but the author can
contribute names there directly.

Keep OSM-derived data out of `places.csv` beyond the `osm`/`wikidata`
references: coordinates and tag fixes belong in `curation.csv` and the build.

## Files

| file | what |
|---|---|
| `places.csv` | the name list — edit this |
| `dialects.csv` | the dialect registry — edit this |
| `dialect_areas.csv` | which OSM object belongs to which dialect — edit this |
| `curation.csv` | per-object map tuning, and the position for places OSM does not have — edit this |
| `placelist.py` | reads/writes/validates `places.csv`; shared by the scripts below |
| `dialects.py` | the registry, the dialect name logic and the area lookup; shared by injector, exporter and matcher |
| `build_candidates.py` | OSM extract(s) → `work/candidates.jsonl` |
| `match.py` | fills `osm`/`wikidata` in `places.csv`; writes `work/matches.csv` and `REPORT.md` |
| `build_dialect_areas.py` | `dialect_areas.csv` + OSM extract → `dialect_areas.geojson` + `dialect_areas_parts.geojson` |
| `dialect_areas.geojson` | generated, **committed**: one polygon set per dialect — the lookup file |
| `dialect_areas_parts.geojson` | generated, **committed**: one polygon per municipality with its `note`, plus the unassigned ones; for the `?areas` review view only, never read by Python |
| `curate.py` | the review worklist as pins on the map: `export` → `work/curate.json`, `apply` writes the browser's decisions back into `places.csv` / `curation.csv` |
| `export_search_index.py` | `places.csv` + `work/matches.csv` → `web/public/data/names.json` (every dialect name, the local form, German, Danish, the QID; keyed by `placelist.entry_id`, the same string the tiles carry as `frasch:ref`) and `web/src/generated/dialects.json` |
| `REPORT.md` | generated worklist |
| `work/` | git-ignored caches (candidates, matches, Wikidata lookups) and the curation view's `curate.json` / `curate-patch.jsonl` |
| `bootstrap/` | the original sheet export, its one-time importer and the one-time `other` → dialect-column migration |
