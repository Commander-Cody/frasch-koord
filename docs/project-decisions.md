# frasch-maps: Decisions & Open Questions

Handoff document summarizing the planning discussion (2026-09-14) and the state after the first build day (2026-09-15). Code: `names/` (pipeline), `tiles/` (build), `web/` (frontend).

## Goal

A Google-Maps-like web map with all labels and UI in **North Frisian**, based on the **OpenMapTiles** vector tile schema.

## Decided

### Language & dialects
- **Initial dialect: Mooring** ("frasch").
- Other dialects (Fering, Öömrang, Sölring, …) will be added later → **everything must be dialect-aware from day one**:
  per-dialect name fields in tiles and data (e.g. `name:frr-x-mooring`, `name:frr-x-fering`), and per-dialect UI translation files.
- Language tags: ISO 639-3 `frr` plus a private-use subtag per dialect (`frr-x-mooring`), since no registered BCP 47 dialect subtags exist.
- Label fallback order (to be finalized in the style): dialect name → other frr name → `name:de` → `name`.

### Map area
- **Phase 1:** North Frisia.
- **Later:** country names and larger cities worldwide; detailed (low-level) Frisian names only for **Germany, Denmark and the Netherlands**.
- Name coverage and tile extent are independent: tiles may cover more area than the name list, falling back to German/local names.

### Name data
- **Source of truth: a name list kept in git**, merged into the tiles at **build time** (option "A").
- Rejected as the primary strategy: upstreaming to OSM `name:frr`. OSM has only a single `frr` field with no dialect distinction, so a custom mechanism is needed anyway. (Contributing names to OSM can still happen separately; that requires OSM import-guideline discussion and an ODbL-compatible license.)
- Rejected: swapping labels in the browser. Big lookup expressions are slow, and OSM IDs aren't reliably present in OpenMapTiles output.
- Editing workflow: CSV/pull requests in git for now; a contributor-friendly editing UI may come later.

### Tech stack
| Layer | Decision | Notes |
|---|---|---|
| Tiles | **Vector tiles, OpenMapTiles schema** | Vector allows switching dialect in the browser without separate tile sets. Schema keeps compatibility with existing OMT styles. |
| Tile hosting | **PMTiles** (single static file on object storage/CDN) | Low lock-in: `pmtiles convert` converts between PMTiles and MBTiles, and `martin` can serve either. Keep the tile URL in config, since it's the only place the frontend depends on it. |
| Map renderer | **MapLibre GL JS** | Smooth zoom and rotation like Google Maps; native OMT styles. |
| Frontend | **React + Vite** (TypeScript) | Candidate: `react-map-gl` (supports MapLibre); `pmtiles` protocol plugin. |
| Search (v1) | **In-browser index** (e.g. MiniSearch/FlexSearch over a JSON file of names) | No backend. Move to Photon or Pelias when the area grows or address search is needed. |
| Routing | **Postponed until v1 is running** | Candidates: Valhalla (good ferry handling, relevant for islands/Halligen), OSRM, GraphHopper. Each needs North Frisian instruction translations. |
| UI i18n | i18n library (e.g. `i18next`), one file per dialect | |

## Decided 2026-09-15 (after the first working build)

### Tile build tool: Planetiler (verified)
- Stock Planetiler jar, **no fork**. The Mooring names are merged by a pre-processing step (`tiles/inject_names.py`, pyosmium) that adds `name:frr-x-mooring` tags to the OSM extract; Planetiler is then run with `--languages=de,da,nds,frr,frr-x-mooring`. Verified: the hyphenated tag appears in the output tiles on nodes and relations (Niebüll → Naibel, Föhr → Fäär, Flensburg → Flansborj).
- Because the merge happens in the PBF, the name list is independent of the tile tool (would also work with imposm/PostGIS).
- Timings on the dev machine (12 cores, 3 GB heap): Schleswig-Holstein 2.5 min (plus ~5 min one-time download of Natural Earth/water polygons, 1.4 GB); output 129 MB PMTiles.
- Finding: OSM already has ~510 objects with `name:frr` in Schleswig-Holstein, but they mix dialects (Sölring "Kairem", Mooring "Doogebel-Huuwen", even Kiel → "Kil"). This confirms: dialect tag first, `name:frr` only as fallback.
- Build entry point: `tiles/build.sh <region>`.

### Worldwide tiles: one planet build
Requirement: **the map must never be blank anywhere**. Therefore: one full planet build (OpenMapTiles schema, ~100 GB PMTiles) as the single style source. Not the "world to z7 + detail region" split (the map would be blank outside the detail region past z7, or show duplicate labels). The planet does not fit on the dev machine (WSL has 8 GB of 16 GB RAM) → build once on a rented VM (≥64 GB RAM, ~1 TB SSD, a few hours, a few euros), upload to object storage. Phase-1 development uses the Schleswig-Holstein extract (and Denmark for name matching).

### Name data
- The list is the owner's own work. It was bootstrapped from a Google Sheet (export + one-time importer kept in `names/bootstrap/`), but **`names/places.csv` is the single source of truth** since 2026-09-15: a slim hand-edited CSV (kind, mooring, older, other, de, hint, da, osm, wikidata, status, note — `other` dissolved into per-dialect columns on 2026-09-16, see below; the sheet's inhabitant/nds/source columns were dropped on purpose). The sheet is not consulted any more. License for the published list: still to be chosen by the owner; ODbL suggested (compatible with tiles and with contributing to OSM).
- The sheet was richer than assumed: columns Mooring, older Mooring names, inhabitant adjectives, German, Low German, Danish, South Jutlandic, old names, source; 10 sections (towns, Köge, Harden, islands/Halligen, Warften, landscapes, waters, roads, older designations, countries, Helgoland). Only the map-relevant columns were imported into `places.csv`; the rest stays in the archived export. The pipeline lives in `names/` (see `names/README.md`).

### Smaller points
- Base style: **OSM Bright**, labels rewritten to `coalesce(name:<dialect>, name:frr, name:de, name)`.
- Fonts: Mooring only needs Latin with diacritics → standard Noto Sans glyphs, self-hosted under `web/public/fonts`.
- Hosting (proposed): Cloudflare R2 for the PMTiles (range requests, no egress fees) + static site on Cloudflare Pages or GitHub Pages.
- Code license (proposed): MIT.
- Frontend: plain `maplibre-gl` (no react-map-gl), `pmtiles` protocol, MiniSearch, i18next. UI strings: German placeholders; Mooring strings pending (not to be invented by tooling).

### Map curation mechanism (2026-09-15, verified)
Three levels of map changes, all without forking Planetiler:
1. **Tag fixes before the build** (`names/curation.csv`, applied by `tiles/inject_names.py`): per OSM id, `set_tags` such as `place=island` change how OpenMapTiles classifies a feature. Needed because OMT drops `place=islet` polygons entirely (Habel, Norderoog, Südfall had no label at any zoom) and Nordstrand has no island polygon in OSM.
2. **Own tile attributes**: Planetiler's `--extra_name_tags=frasch:kind,frasch:minzoom,frasch:maxzoom` copies arbitrary tags into the tiles. The injector writes `frasch:kind` (the sheet's own classification: island / hallig / sand / warft / koog / …) and `frasch:minzoom` (per-feature curation, e.g. Tilli and Tammensiel not before Dagebüll at z10; Süderoogsand together with Norderoogsand at z9). The style enforces `frasch:minzoom` with a zoom filter and styles/prioritises labels by `frasch:kind`.
3. **Style** (`web/src/style/frasch-bright.json`, forked from OSM Bright): label layers per kind (`place-island`, `place-hallig`, `place-sand` from z10, `place-warft` from z13, …). Priority islands > Halligen > towns/villages > sands > hamlets > Warften. Important MapLibre detail: label collision is resolved in reverse layer order (the LAST symbol layer in the style wins), `symbol-sort-key` only orders within one layer — so the priority is expressed by the physical layer order, low-priority layers first.

Resolved with this mechanism (2026-09-15): Habel/Norderoog/Südfall labelled (islet → island); Nordstrand styled and timed like Pellworm (municipality relation gets `place=island`, village node held to z12; revised 2026-09-16: the relation's label sat 2 km from the village and stayed on next to the village label, so the injector now adds a synthetic 50 km² `place=island` square centred on the village node via curation's `polygon_km2`; it carries the island label from z8 at the village's position and `frasch:maxzoom=11` hands over to the village label at z12 — see `names/README.md`); Süderoogsand and Norderoogsand both from z10 as sands; Tilli/Tammensiel not before Dagebüll (z10) and never over the island name. Second round: sands labelled whenever there is room (their OSM class is `island`, the filter had excluded it); smallest Halligen (OMT rank 6, e.g. Habel) wait until z12 by style rule; Hamburger Hallig via its admin_level=10 relation (z12); all Warften share one layer from z13 — Hallig Warften are `place=hamlet` in OSM and are recognised by name (*warf*, *weerw*, *wäärw*).

Language chain in labels: `name:frr-x-mooring` → `name:frr` → `name:nds` → `name:de` → `name:latin` → `name` (revised 2026-09-16, see below: `frasch:local` now comes second, and the local view has a chain of its own). Planned: outside Germany drop `name:de` and use `name:en` (two symbol layers with a `within`-Germany filter).

## Decided 2026-09-16: multi-dialect model and the local-dialect view

North Frisian is a dozen varieties, and the sheet's `other` column already held
Sölring, Öömrang, Halunder and Hålifrasch names. They are now first-class.

1. **One row per place, one column per dialect** in `names/places.csv`. The
   catch-all `other` column is dissolved (one-off
   `names/bootstrap/migrate_dialect_columns.py`; what it could not sort sits in
   `note` as `unsorted other-dialect name: …`).
2. **A `local` column** holds the form the people of the place itself use where
   it differs from the dialect of the area around it (sub-dialects such as
   Fahretoft). Empty = same as the area's dialect. Its bracket remark names the
   variety: `Brouersweerw (Foortuftinge)`.
3. **`names/dialects.csv` is the dialect registry** — the single list. The
   place-list columns, the injected `name:*` tags, Planetiler's `--languages`,
   the search index and the frontend's selector all derive from it. Adding a
   dialect is one line plus a column, no code change. Language tags stay
   `frr-x-<subtag>` (BCP 47 private use, at most 8 characters per subtag).
4. **Dialect areas**: `names/dialect_areas.csv` names the OSM municipalities and
   island polygons of each dialect; `names/build_dialect_areas.py` turns them
   into the committed `names/dialect_areas.geojson`. Injector and search
   exporter do point-in-polygon against it, **smallest area wins** (Hamburger
   Hallig lies inside Reußenköge). Positions come from id-filtered pre-passes,
   not from a location cache — the dev machine has 5 GB.
5. **Tile attributes** per matched object: `name:<tag>` for every dialect with a
   name, `frasch:kind` (unchanged), `frasch:dialect` (the area's dialect),
   `frasch:local` (the local name), `frasch:variety` (the variety's name).
6. **Label chains** (Phase 1 = Schleswig-Holstein tiles, so Low Saxon is always
   the local majority language; a northern-Germany `within` polygon comes with
   the planet build):
   - dialect view for tag T: `coalesce(name:T, frasch:local, name:frr, name:nds, name:de, name:latin, name)`
   - local view (`frr-x-local`): `coalesce(frasch:local, name:nds, name:latin, name)` — deliberately **no** `name:frr` and **no** `name:de`: where the Frisian name is unknown the honest local label is the Low Saxon one, not a Hochdeutsch one or another dialect's name.
7. **UI**: one dropdown. Every option carries a UI language; only registry
   entries with `view=yes` are selectable (today only Mooring — a dialect
   becomes selectable when its UI translation exists). The local view uses
   Mooring for the UI, configurable in one place
   (`LOCAL_VIEW_UI_LANGUAGE` in `web/src/config.ts`).
8. Owner's decisions on the data behind this: **Low Saxon** counts as the local
   majority language in northern Germany; **Südergoesharde** is extinct (1981)
   but its historic names still label the local view; **Nordstrand, Pellworm and
   Eiderstedt** get no Frisian area (Low Saxon there); the sheet's
   `(Gooshiirdinge)` names were sorted into the Goesharde the place lies in
   (`GOESHARDE_BY_DE` in the migration script). **The `older` column is
   gone** (owner's decision, `names/bootstrap/drop_older_column.py`): island
   and Hallig names went to their dialect's column, mainland names to the
   Harde's column where OSM's `name:frr` confirms the form, the rest became
   the Mooring name (when `mooring` was empty) or was dropped as an
   alternative Mooring spelling. Wallsbüll's and Lundenberg's Goesharder
   names are now Mooring/Südergoesharder cells with their remark kept.
9. **Mainland areas are a researched draft.** The 81 municipality rows in
   `names/dialect_areas.csv` were assigned to the six Harden from German
   Wikipedia on 2026-09-16 (historic Harde membership; Bohmstedt, Drelsdorf and
   Ahrenshöft follow the documented Mittelgoesharder dialect instead). Rows
   whose `note` says `medium` or `low` (29) need the owner's check, above all
   the Gotteskoog border villages Holm, Uphusum, Lexgaard, Braderup, Galmsbüll
   and the Stedesand/Klixbüll/Bosbüll assignment to the Karrharde.

## Decided 2026-09-17: places OSM does not have get their own point

A row of `places.csv` may carry `lat` / `lon` instead of an `osm` id. The
injector then adds a node at those coordinates to the extract (tags as for any
other row, plus `name` and the `place=` value of its `kind`:
`settlement` → `hamlet`, `warft` → `isolated_dwelling`, `island`/`hallig` →
`island`), the search index takes its position from the row, and `match.py`
leaves the row alone. The node ids continue above the highest node id of the
extract; nothing is written back to OSM.

This answers the first half of open question 3 of the first match run (*Harden
/ Köge without OSM objects: add to OSM or carry as an overlay?*) for the cases
where a **point** is enough. Areas (a Harde, a Koog) still need either an OSM
polygon, a `curation.csv` `polygon_km2` square around a point, or an overlay.
First use: *Waasterhias* (Westerheide near Nebel on Amrum), which OSM does not
have.

Also this day: the search index no longer trusts the line numbers in
`work/matches.csv` — it looks a row's position up by its OSM reference, and
falls back to the line only when the row on that line is still the same place.
Deleting one row used to shift every row below it and hand them their
neighbour's coordinates.

Revised 2026-09-18: the `lat`/`lon` columns went back out of `places.csv`; see
below.

## Decided 2026-09-18: places OSM does not have are local references, positioned in curation.csv

Yesterday's `lat`/`lon` columns in `places.csv` are reverted (columns and the
one-off `bootstrap/add_point_columns.py` removed again). A place OSM does not
have now gets a **local reference** in `places.csv`'s `osm` column instead:
`local/<slug>` alone in the cell (lowercase ascii letters, digits, hyphens,
e.g. `local/westerheide-amrum`), never mixed with a real reference, `wikidata`
left empty; `match.py` leaves such a row alone (`own point` in `REPORT.md`).

The position moves to `curation.csv`, which gains `lat`/`lon` columns
(mandatory on a row keyed by a local reference, empty on a row keyed by a real
`osm` reference — the same local reference is the key in both files). The
injector (`tiles/inject_names.py`) then either adds a **new node** at
`lat`/`lon` (tags as before: `name:<dialect>`/`frasch:*`, `name` from
German/Danish/any Frisian name, a `place=` default from `kind` — the warft
default changed from `isolated_dwelling` to `hamlet`, since OMT gives
`isolated_dwelling` z14 but `hamlet` z11 and OSM's own Hallig Warften are
`hamlet` already — then the curation row's `set_tags`/`minzoom`/`maxzoom`
applied last), or, when the curation row carries `polygon_km2`, only the
synthetic square of that area centred on `lat`/`lon` and no node at all —
the route for an area-like place (a Koog) that needs a lower label zoom than
a node gets. The loader stops the build on a local reference with no curation
row, a curation local row without `lat`/`lon`, or a local reference used
twice in `curation.csv`; a curation local row no `places.csv` row uses is
reported and ignored. The search index takes a local row's position from
`curation.csv` and uses the local reference itself as the entry's `id`.
Nothing is uploaded to OSM. First use unchanged: *Waasterhias* (Westerheide
near Nebel on Amrum). See `names/README.md` for the mechanism in full.

**Why**: coordinates living in the name list could not be addressed by
`curation.csv`, which is keyed by OSM reference — a hand-placed node only gets
its id at inject time, and that id changes with every extract. So a
hand-placed place could get no `set_tags`, no zoom window and no
`polygon_km2` — exactly what the backlog needs (60 Köge and 8 Harden are
areas; OpenMapTiles emits hamlet nodes from z11, isolated_dwelling from z14,
and `frasch:minzoom` can only push a label later, never earlier). A
coordinate-based pseudo key would have written the position twice. A local
reference in the identity column both files already share keeps one row = one
place in the name list, needs no new column in `places.csv`, and gives the
search index a stable id. Cost: a hand-placed place now needs two rows, one
per file.

## Remaining open questions
1. License of the published name list (owner's choice; ODbL suggested).
2. Hosting provider (R2 + Pages proposed, nothing set up yet).
3. When to do the planet build (needs the VM; only after the North Frisia build looks right).
4. Whether to also push confirmed names to OSM `name:frr` (separate track; import guidelines).

## Name-mapping pipeline (built 2026-09-15)

Scripts in `names/` (see `names/README.md` for the workflow): `placelist.py` (reads/validates `places.csv`, shared); `build_candidates.py` (one pyosmium pass over the SH + DK extracts, ~8.5 min, 182k candidates); `match.py` (exact match after normalisation, no fuzzy matching; fills empty `osm`/`wikidata` cells of `places.csv` and marks them `status=auto`; writes `names/work/matches.csv` with the details and `names/REPORT.md` as the hand-review worklist); `tiles/inject_names.py` (tags the PBF). Keys: OSM reference `type/id` (several allowed for split rivers/dykes) plus the Wikidata QID where the object has one; countries via Wikidata only.

First run: 825 place rows → **437 matched, 41 ambiguous, 340 not found**, 7 not places. Settlements 225/334 matched; Köge 25/87; Warften 117/276; waters 24/45; islands 26/41; Harden 0/8; countries 12/12. 447 objects tagged in the SH extract (Denmark rows resolve once a DK-covering build exists). 34 matches spot-checked by hand, all correct; all 59 location-hinted matches verified geometrically.

Data-quality findings:
- Harden do not exist in OSM at all; most Köge only as street/Sielzug names or not at all (Gotteskoog has no polder object). These need either OSM edits or a separate overlay layer.
- Warften are `place=isolated_dwelling|hamlet` nodes or `landuse=residential|farmyard` ways; ~100 exist only as building/street names.
- Vanished Halligen (Bohnen-, Hasen-, Pohns-, Schweine-, Großhallig, Christianshallig) are not in OSM.
- 16 rows carry a name in another dialect (Sölring, Halunder, Öömrang); they were flagged `name_source=other_dialect` and **not injected** as Mooring. *Superseded 2026-09-16: every dialect has its own column and its own `name:*` tag, and a row is matched and injected whichever column its name is in.*
- 10 rows land on the same OSM object twice (Mooring + older spelling); the first row wins, the injector warns, REPORT.md lists them — the owner should `skip` one of each pair.

Manual review workflow: edit `names/places.csv` — write the `osm` reference (`node/123`), optionally `status=ok`, or `status=skip`; `match.py` only rewrites rows with `status=auto` or with empty `osm`+`wikidata`, so hand-filled rows are never touched and `git diff` after a run shows exactly what it proposed.

Open questions for the list owner (from the first run):
1. Other-dialect rows: inject as Mooring, or hold for their own dialect column?
2. Duplicate pairs: which spelling goes on the map?
3. Harden / Köge without OSM objects: add to OSM or carry as an overlay?
4. `Hesbüll Feld???`, `Jacobswarft (wo?)`, `FInland` typo, `Garding, Kirchspiel` vs `Garding`.
5. Rows whose location hint contradicts the only OSM candidate (e.g. `Morsum (Nordstrand)` vs Morsum on Sylt).
6. 5 rows with a German name but no Frisian name.

## Legal requirements
- Show "© OpenStreetMap contributors" and "© OpenMapTiles" on the map.
- ODbL applies to published databases derived from OSM.

## Development environment notes (WSL2)
- **JDK 21** (Temurin) installed user-locally at `~/.local/opt/jdk-21*` (no sudo in this shell); `tiles/build.sh` finds it automatically.
- **Python**: `uv` at `~/.local/bin/uv`; project venv `.venv` (Python 3.12) with pyosmium, shapely, mapbox-vector-tile. System Python 3.14 has no pip/venv.
- **pmtiles CLI** at `~/.local/bin/pmtiles` for inspecting archives.
- Docker is not needed with Planetiler.
- **Node v24.21.0 (LTS, npm 11.19.0)** installed in WSL via nvm 0.40.7 and set as the default (`lts/*`). Pin the version in `.nvmrc` once `web/` is scaffolded. Note: a Windows Node install exists at `/mnt/d/Program Files/nodejs/`; make sure WSL shells use the nvm one.
- **Docker is not available in WSL**; enable Docker Desktop WSL integration or install Docker Engine.
- Planetiler requires Java 21+.

## Next steps
1. Hand-review the *ambiguous* / *not found* rows in `names/REPORT.md`; write `osm` references (and `ok`/`skip`) into `names/places.csv`.
2. Run `tiles/build.sh schleswig-holstein`, open the web app, check labels.
3. Translate the UI strings in `web/src/locales/frr-x-mooring.json`.
4. Choose name-list license and hosting; first deployment of the SH build.
5. Extend name matching to Denmark tiles (Rudbøl, Rømø, Tønder …) and country names via Wikidata.
6. Planet build on a rented VM.
