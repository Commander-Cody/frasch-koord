# names/ — the North Frisian name list

**`names/places.csv` is the single source of truth** for every Frisian label on
the map. It is a plain CSV you edit by hand (any text editor, VS Code's CSV
extensions, or LibreOffice — just save as UTF-8 CSV again). Everything else in
this directory either helps fill it in or is generated from it.

```
names/places.csv         THE name list (hand-edited, in git)
names/curation.csv       per-OSM-object map tuning (hand-edited, in git)
        |
        |  match.py          fills empty `osm` cells, marks them status=auto
        |  <- work/candidates.jsonl <- build_candidates.py <- tiles/data/*.osm.pbf
        v
names/REPORT.md          generated worklist: what is still unmatched
names/work/matches.csv   generated details of the last match run (git-ignored)
        |
        |  export_search_index.py  ->  web/public/data/names.json
        |  tiles/inject_names.py   ->  tags in the OSM extract  ->  tiles
```

`names/bootstrap/` holds the one-time import from the original Google Sheet
(September 2026). The sheet is history; do not edit it expecting the map to
change.

## `places.csv` columns

| column | meaning |
|---|---|
| `kind` | `settlement`, `koog`, `harde`, `island`, `hallig`, `sand`, `warft`, `landscape`, `water`, `road`, `country`, `helgoland`, or `not_a_place` (dictionary-only rows such as *Håli*, *bütenlönj*). Decides which OSM objects count as a match and becomes the tile attribute `frasch:kind`. |
| `mooring` | the Mooring name(s). **The first one is the map label.** |
| `older` | older Mooring name(s) from the sheet's *Oudere noome* column. The label when `mooring` is empty. |
| `other` | name(s) in another North Frisian dialect (Sölring, Halunder, Öömrang, Hålifrasch), e.g. `Fuan (Sölring)`. Never put on the map — a dialect gets its own column when it gets its own map. |
| `de` | German name(s). What the matcher searches for in OSM. |
| `hint` | where the feature is, for matching: `Langeness`, `Ockholm`, `bei Leck`. Binding — a hint that matches nothing sends the row to review. |
| `da` | Danish name(s). Used for matching when there is no German name. |
| `osm` | the OSM object(s) that carry the label: `node/123`, `way/123`, `relation/123`. Several separated by `;` when OSM splits a river or dyke into pieces: `way/1; way/2`. |
| `wikidata` | Wikidata item. The injector also tags every OSM object with this `wikidata` tag; for the countries, which have no `osm`, it is the only key. |
| `status` | `auto` — `match.py` filled `osm`/`wikidata` and will recompute them next run. `ok` — a human checked the row. `skip` — never put on the map. Empty — nothing decided yet (or, with `osm` filled by hand, simply yours). |
| `note` | free text for you. `match.py` never writes here. The import put `uncertain` here for names the sheet marked with `?`. |

The sheet's other columns (inhabitant adjectives, Low German, South Jutish,
old names, sources) were deliberately not imported: the map does not use them.
They are still in `bootstrap/sheet-export.csv`.

Conventions that apply to every name cell:

* several variants are separated by `;` — the first one is the primary name
* `(…)` after a variant is a remark about it (a local variety such as
  `(wisinge)`, a dialect, a source) and is never part of the name
* no `?` inside names — say `uncertain` in `note`

The rows are in the order of the original sheet (by section, then the owner's
geographic order); new rows can go anywhere.

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

**Build**:

```bash
$PY names/export_search_index.py   # -> web/public/data/names.json (needs a match.py run)
tiles/build.sh schleswig-holstein  # injects places.csv + curation.csv, runs Planetiler
```

Dry-run the injection alone:

```bash
$PY tiles/inject_names.py tiles/data/schleswig-holstein-latest.osm.pbf /dev/null --dry-run
```

It lists ids that are not in the extract, rows that claim the same object
twice (the first row in file order wins), QIDs it could not find, and the
synthetic polygons it would add.

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
* Rows with only an `other`-dialect name are matched too (the id will be
  useful once that dialect has a column) but never injected.
* **Countries** are keyed by Wikidata QID only (via `wbsearchentities` +
  `wbgetentities`, filtered to country / sovereign-state classes);
  `inject_names.py` tags whatever object carries that QID.

## `curation.csv` — per-feature map tuning

The name list says *what a place is called*. `curation.csv` says *how the map
should treat one particular OSM object* — and it works for objects that have no
Frisian name at all (the village Tilli, the sand Japsand), so it is deliberately
a separate file with its own identity: the OSM reference, nothing else.

| column | meaning |
|---|---|
| `osm` | `node/123`, `way/123`, `relation/123`; several separated by `;`, as in `places.csv` |
| `name` | free-text label so a human can read the row — **not** written to the data |
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
  label carrier: `place=island` feeds nothing but the place layer.

`frasch:kind` comes from the name list (`places.csv`'s `kind` column) for every
injected row; `set_tags` is how an object the list does not mention gets one.

`tiles/build.sh` passes the file to `inject_names.py` automatically;
`--no-curation` ignores it, `--curation OTHER.csv` swaps it.

## Files

| file | what |
|---|---|
| `places.csv` | the name list — edit this |
| `curation.csv` | per-object map tuning — edit this |
| `placelist.py` | reads/writes/validates `places.csv`; shared by the scripts below |
| `build_candidates.py` | OSM extract(s) → `work/candidates.jsonl` |
| `match.py` | fills `osm`/`wikidata` in `places.csv`; writes `work/matches.csv` and `REPORT.md` |
| `export_search_index.py` | `places.csv` + `work/matches.csv` → `web/public/data/names.json` |
| `REPORT.md` | generated worklist |
| `work/` | git-ignored caches (candidates, matches, Wikidata lookups) |
| `bootstrap/` | the original sheet export and its one-time importer |
