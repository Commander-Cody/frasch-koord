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
- Timings on the dev machine (12 cores, 3 GB heap): Schleswig-Holstein 2.5 min (plus ~5 min one-time download of Natural Earth/water polygons, 1.4 GB; pinned since issue #28); output 129 MB PMTiles.
- Finding: OSM already has ~510 objects with `name:frr` in Schleswig-Holstein, but they mix dialects (Sölring "Kairem", Mooring "Doogebel-Huuwen", even Kiel → "Kil"). This confirms: dialect tag first, `name:frr` only as fallback.
- Build entry point: `tiles/build.sh <region>`.

### Worldwide tiles: one planet build
Requirement: **the map must never be blank anywhere**. Therefore: one full planet build (OpenMapTiles schema, ~100 GB PMTiles) as the single style source. Not the "world to z7 + detail region" split (the map would be blank outside the detail region past z7, or show duplicate labels). The planet does not fit on the dev machine (WSL has 8 GB of 16 GB RAM) → build once on a rented VM (≥64 GB RAM, ~1 TB SSD, a few hours, a few euros), upload to object storage. Phase-1 development uses the Schleswig-Holstein extract (and Denmark for name matching).

### Name data
- The list is the owner's own work. It was bootstrapped from a Google Sheet (export kept in `names/bootstrap/`; the one-time importer was removed on 2026-09-25 and is in git history), but **`names/places.csv` is the single source of truth** since 2026-09-15: a slim hand-edited CSV (kind, mooring, older, other, de, hint, da, osm, wikidata, status, note — `other` dissolved into per-dialect columns on 2026-09-16, see below; the sheet's inhabitant/nds/source columns were dropped on purpose). The sheet is not consulted any more. The published list is under ODbL 1.0 (decided 2026-09-19, see below).
- The sheet was richer than assumed: columns Mooring, older Mooring names, inhabitant adjectives, German, Low German, Danish, South Jutlandic, old names, source; 10 sections (towns, Köge, Harden, islands/Halligen, Warften, landscapes, waters, roads, older designations, countries, Helgoland). Only the map-relevant columns were imported into `places.csv`; the rest stays in the archived export. The pipeline lives in `names/` (see `names/README.md`).

### Smaller points
- Base style: **OSM Bright**, labels rewritten to `coalesce(name:<dialect>, name:frr, name:de, name)`.
- Fonts: Mooring only needs Latin with diacritics → standard Noto Sans glyphs, self-hosted under `web/public/fonts`.
- Hosting (proposed): Cloudflare R2 for the PMTiles (range requests, no egress fees) + static site on Cloudflare Pages or GitHub Pages.
- Code license: MIT (decided 2026-09-26, see below).
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
   `names/bootstrap/migrate_dialect_columns.py`, since removed; what it could not sort sits in
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
   (Since 2026-10-01 also `name:de` from the list's `de`, see below.)
6. **Label chains** (Phase 1 = Schleswig-Holstein tiles, so Low Saxon is always
   the local majority language; a northern-Germany `within` polygon comes with
   the planet build):
   - dialect view for tag T: `coalesce(name:T, frasch:local, name:frr, name:nds, name:de, name:latin, name)`
   - local view (`frr-x-local`): `coalesce(frasch:local, name:nds, name:latin, name, name:de)` — deliberately **no** `name:frr` and `name:de` only as the very last resort: where the Frisian name is unknown the honest local label is the Low Saxon one, not a Hochdeutsch one or another dialect's name. (Revised 2026-10-01, #32: `name:de` was not in the chain at all, which left a feature with only a German name unlabelled. It now comes after OSM's own `name`, so it only matters where a feature has no `name`. The card and search take the generic `name` from OSM too, as `name_osm` in names.json, and no longer treat it as German. North of the border it is Danish. Since 2026-10-03, #81: inside a dialect
     area the injector writes OSM's `name:frr` into `frasch:local` where the
     list gives no local name, see below. The chain itself is unchanged.)
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
   gone** (owner's decision, one-off `names/bootstrap/drop_older_column.py`, since removed): island
   and Hallig names went to their dialect's column, mainland names to the
   Harde's column where OSM's `name:frr` confirms the form, the rest became
   the Mooring name (when `mooring` was empty) or was dropped as an
   alternative Mooring spelling. Wallsbüll's and Lundenberg's Goesharder
   names are now Mooring/Südergoesharder cells with their remark kept.
9. **Mainland areas are a researched draft.** The mainland rows of
   `names/dialect_areas.csv` were assigned to the six Harden from German
   Wikipedia on 2026-09-16 (historic Harde membership; Bohmstedt, Drelsdorf and
   Ahrenshöft follow the documented Mittelgoesharder dialect instead). Rows
   whose `note` says `medium` or `low` need the owner's check, above all the
   Gotteskoog border villages Holm, Uphusum, Galmsbüll and
   the Stedesand/Klixbüll/Bosbüll assignment to the Karrharde.
   *(Corrected 2026-09-30: the file has 64 rows — 39 mainland, 25
   island/Hallig. It had 83 until the owner removed 20 mainland rows and
   added Husum on 2026-09-20; the geojson follows it, see the 2026-09-20
   entry below.)*

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

## Decided 2026-09-19: name list under ODbL 1.0

The published name list, named **"Frasche stääsnoome"** (`names/places.csv` and the other hand-edited files in
`names/`) is licensed under the **Open Database License 1.0**, contents under
DbCL 1.0; full text in `names/LICENSE`. Attribution string: "Frasche
stääsnoome, Thore Andresen, ODbL 1.0".

**Why**: the tiles are ODbL anyway (derived from OSM), so nothing else was
gained by a more permissive choice; ODbL lets anyone push names into OSM
without a waiver, and share-alike guarantees that an extended or merged list
(another dialect, another region) comes back to the public. Cost accepted:
third parties cannot carry the names into Wikidata (CC0); the author can do so
personally as the rights holder. CC BY-SA was ruled out because OSM cannot
import it. Preconditions checked: the sheet's sources are many cited
publications (Hoekstra 2015, Nordfriisk Instituut, Löfstedt 1931, literary
texts), not a bulk extraction from one database; `places.csv` holds only OSM
*references*, not OSM names or coordinates (those live in `curation.csv` and
the build). Still to confirm by the owner: that no one else contributed rows to
the original sheet (co-authors would have to agree to the license).

The code is MIT (root `LICENSE`, 2026-09-26, #22). The style fork keeps OSM
Bright's BSD / CC BY notice in `web/src/style/LICENSE-osm-bright.md`. The map's attribution
control shows "© OpenStreetMap contributors" and the OpenMapTiles credit, as a
fixed licence notice in every UI language (`web/src/style/localize.ts`).

## Decided 2026-09-19: review the matcher's leftovers on the map (issue #1)

375 rows of `places.csv` had no OSM object after the first match run (325
*not found*, 38 *ambiguous*). Deciding them from `REPORT.md` meant looking
every candidate up on openstreetmap.org and editing the CSV by hand, so the
web app gained a **dev-only curation view** (`http://localhost:5173/?curate`,
Vite dev server only) and `names/` a companion script `curate.py`:

- `curate.py export` turns `work/matches.csv` + `work/candidates.jsonl` into
  `work/curate.json`: the open rows in priority order (settlements, islands,
  Halligen first; Köge and Warften last), each with its candidates' positions
  and the resolved location hint.
- The browser shows the rows as a list and the candidates as pins; Nominatim
  and Overpass lookups (public instances, called from the browser) help with
  the *not found* rows. Every decision — an OSM reference, a `local/<slug>`
  with a position clicked on the map, or `skip` — is appended by a Vite dev
  middleware to `work/curate-patch.jsonl`. The browser never touches
  `places.csv`; done rows are read back from the patch, so a session resumes.
- `curate.py apply` writes the patch into `places.csv` (`status=ok`/`skip`,
  the same three cells `match.py` owns and only rows it still owns) and, for a
  local reference, appends the position row to `curation.csv`. Review with
  `git diff`, as after a match run.

**Why a patch file and a script instead of editing the CSV from the browser**:
`places.csv` stays the single hand-edited source of truth, the ownership rule
of `match.py` (never a row with `status=ok`/`skip` or a hand-filled `osm`)
is enforced in one place, and a decision made against a stale line number
(rows shift when one is added) is refused rather than silently misapplied —
rows are identified by kind + Frisian name + German name, the line is only the
fast path.

## Decided 2026-09-20: review the dialect areas on the map (issue #2)

The mainland dialect assignments are a researched draft nobody has eyeballed,
and a wrong one is invisible: a place is joined to a dialect area by
point-in-polygon at build time, never by name, so a bad row only shows up as a
wrong label. `names/dialect_areas.geojson` cannot show them — it is dissolved
per dialect, one Feature each, and carries neither the municipality name nor
the research `note`.

So `build_dialect_areas.py` gained a **second output**,
`names/dialect_areas_parts.geojson`: one Feature per municipality
(`fid`, `assigned`, `dialect`, `label`, `name`, `note`, `osm`, `line`, `km2`),
written from the same in-memory geometry in the same run, so the two files
cannot disagree. It also carries the Kreis Nordfriesland municipalities that
**no row claims**, marked `assigned: false` — a hole in the coverage is a bug
you have to be able to see. Those are found by scanning `admin_level=8`
relations for a `de:regionalschluessel` starting `01054`, not by a bounding
box: a box would also catch the neighbouring Kreise, which are not part of the
dialect map at all. 135 features, 284 kB, **committed** for the same reason as
the dissolved file — regenerating it needs the gitignored 158 MB extract.

Simplified to 0.0001° (~11 m) rather than the dissolved file's 0.0005°.
Neighbours are simplified independently, so a shared boundary drifts by up to
the tolerance in *each* of them; at 50 m that is a visible crack between two
municipalities that actually touch, at exactly the zoom the review happens at.

Nothing in the Python pipeline may read the parts file: its unit is the
municipality, not the dialect, so feeding it to `AreaIndex` would silently
change every dialect lookup. The unassigned features carry no `dialect`
property at all, which makes `AreaIndex.from_geojson` refuse the file outright
instead of quietly loading it.

The web app gained a dev-only review view, `http://localhost:5173/?areas`
(`web/src/dev/AreaPanel.tsx`), a sibling of `?curate`: the parts file as
a coloured fill inserted before `waterway-name` so it sits under every label,
one colour per dialect, and a near-opaque outline **in the same hue** so
municipality boundaries stay visible *inside* one dialect's block — which is
the point, since what is being checked is a per-municipality assignment.
Clicking a polygon or a list row shows the name, the dialect and the `note`
verbatim; `?areas&area=<line>` reopens a row (since 2026-09-27
`?areas&area=relation/<id>`, see below). `web/vite-plugins/areas.ts`
serves the file in dev only, so the research prose ("best guess only", "no
direct source found") about unconfirmed assignments does not ship to the public
site.

The eleven dialect colours (`web/src/dev/areaLayers.ts`) were not picked
by eye. The hues come from the data-viz reference palette and the *assignment*
was solved against the adjacency computed from the geometry itself — which
turned up Sölring/Wiedingharder as a touching pair, out in the Wattenmeer.
Every touching pair, and every pair within ~6 km, clears the colour-vision
gates with ~1.5x margin. Eleven categories cannot all be pairwise
colourblind-safe — no assignment of any eleven hues can — so colour is never
the only channel: the legend pairs each swatch with its name, the list is
grouped by dialect, the detail block spells the dialect out, and clicking a
legend row draws that dialect alone.

**Confidence is deliberately not modelled**: no `confidence` column, no parsing
of the `note`, no hatching or dimming. Colour is the dialect and nothing else;
the raw note on selection is the whole story. **The view is read-only**, unlike
`?curate`: `dialect_areas.csv` is 64 hand-edited lines and the build takes
seconds, so a patch file would only add a second way to change the data.

The checklist is `docs/dialect-area-review.md`, keyed by name rather than line
(rows shift). Five notes had been truncated mid-word at ~180 characters by the
research run (Galmsbüll, Holm, Stedesand, Ahrenshöft, Süderhöft) and were
trimmed to their last complete clause — no re-research, nothing added.

*(Resolved 2026-09-30: the review first found 23 municipalities in the
committed geojson that no CSV row claimed any more. The owner had removed
those rows on purpose; the geojson was rebuilt from the CSV on 2026-09-27, and
`just check-outputs` now fails when the two disagree.)*

## Decided 2026-09-27: every `places.csv` row has a stable id (issue #23)

`places.csv` gained an `id` column (last): a slug of the row's Frisian name
(German, then Danish, when it has none), `-2`, `-3` on repeats, e.g. `naibel`,
`schorkewarw-2`. `names/check.py --fix` gives a new row one (its first run was
the migration); `placelist.read` refuses a row without a unique one. An id is
never changed afterwards, even when the name is.

Everything that used to name a row by its line or by kind + Frisian name +
German name now uses the id: `work/matches.csv` and `REPORT.md` (which also
show the line), the curation worklist, patch and `apply`, the curation view's
done state and `?curate&row=`, the search index's entry `id` and the tiles'
`frasch:ref`. A `?place=` link therefore survives edits to the list and OSM id
changes; old `?place=node/…` links, old `ref#line` links and tiles built
before the switch still resolve through the entry's `osm` field (web
`entryLookup`). `dialect_areas.csv` rows are keyed by their OSM reference,
which may now appear on one row only (`?areas&area=relation/…`). Line numbers
remain only in messages meant for a human.

**Why**: inserting a row renumbered every row below it — `?place=` links to a
second row on an object (`way/28330569#678`) broke, curation decisions were
refused after hand edits (11 of ~100 on 2026-09-20), four *Schörkewärw* /
Kirchwarft rows could not be told apart at all, and a withdrawn decision sent
with another line number still applied (review finding M2). This supersedes
the 2026-09-19 note above that rows are identified by kind + names with the
line as a fast path, and the 2026-09-18 note that a local reference is the
search-index id.

## Decided 2026-09-27: one pipeline for positions, provenance and drift checks (issue #24)

**Positions are worked out once.** `names/locate.py` finds every OSM object of
the name list in the extracts (SH + DK) and writes the committed
`names/osm_objects.json`: a point inside the object's polygon (else its label
member or first vertex), the outline point as a second try for the dialect,
the `admin_level` of an administrative boundary and OSM's `name:nds`. The
injector and the search export both read it and both call
`locate.dialect_at`, so a label and its search entry cannot disagree. The
search index no longer reads `work/matches.csv` at all.
- Every object gets the dialect where it lies (owner's choice: per object,
  not per row); a search entry takes the first object of its row's `osm`
  cell. An administrative area above municipality level (Kreis, Amt) gets
  none.
- A row on the map whose object the file does not know stops both the
  export and the injector, instead of silently dropping out of search.

**Orchestration: `just`** (owner's choice over a Makefile — `make` is not on
the dev machine), installed as a dev dependency (`rust-just`) so `uv run just`
works everywhere. Recipes: `extracts`, `candidates`, `match`, `objects`,
`areas`, `index`, `dialects`, `tiles`, `check`, `check-full`, `check-tiles`.

**Provenance.** `names.json` became `{"built_from", "places"}`; the tiles
carry the same `built_from` (git blob hashes of `places.csv`,
`dialects.csv`, `curation.csv`, `dialect_areas.geojson`, `osm_objects.json`
plus the objects' extracts) in the PMTiles `description`. The frontend warns
in the console when they differ. The dialect areas record the hashes of
`dialect_areas.csv` and `dialects.csv` and their extract.

**Drift check.** `just check-outputs` runs in CI: it regenerates `names.json`
and `dialects.json` and diffs them, and checks the stamps of the extract-derived
files (CI has no extract; `-latest` changes daily anyway). `just check-full`
rebuilds those from local extracts too; `just check-tiles` compares a built
archive with `names.json`, label by label.

**Hardening.** `candidates.jsonl` names its extracts and is written
atomically, and `match.py` warns when the extract set changes;
`match.py --dry-run` writes nothing tracked; `build_dialect_areas.py` stops on
a missing area (`--allow-missing`); `build.sh` pins Planetiler 0.10.2 by
sha256, verifies Geofabrik downloads by their `.md5`, builds to temp files.

**Why**: the two chains used to locate places separately, days apart, and
disagreed on Sylt, Amrum, Oland, Stiardebel and more; nine rows were missing
from search; the committed `names.json` had been built from an uncommitted
`places.csv`; and a fresh clone could not rebuild it. This supersedes the
2026-09-16 note that positions come from the injector's own pre-passes and
the 2026-09-17 note on how the search index looks positions up.

## Decided 2026-09-28: the Python code is one package (issue #25)

All Python of `names/` and `tiles/` moved into the package `frasch/` at the
repo root, installed editable by uv; the scripts stay where they were as
launchers, so the justfile, `tiles/build.sh` and the docs keep their paths.
*Superseded 2026-10-06 (#91): the launchers are gone, see the entry of that date.*
Library code raises (`ValidationError` with every problem found, not only the
first); only a command's `main()` exits. Each concept exists once: the dialect
registry reader (passed in, not read at import), the curation file
(`curationlist`), the North Frisia box (`geo`, the matcher's box with
Helgoland, so `build_candidates.py` now keeps Helgoland's roads too), the PBF
passes and ring assembly (`osmscan`, `osmgeom`), the name index. The curation
patch has a JSON Schema (`names/curate-patch.schema.json`) that `curate.py
apply` (with the `jsonschema` package) and the web side both take from. See
`names/README.md#code`.

## Decided 2026-09-30: the website is built from published tiles (issue #28)

**Tiles are published, not built, for the website.** Each finished archive
becomes the asset of its own GitHub release of this repository
(`tiles-<yyyymmdd>-<sha8>`, owner's choice over R2, which has not been set up yet), and `web/tiles.lock`
pins the one the site uses (URL + sha256). `uv run just publish-tiles`
uploads a build and rewrites the lock. `npm run fetch-assets` fetches the
glyphs and that archive, so a fresh clone builds a working site with no Java,
Python or OSM downloads. CI does the same and runs `npm run smoke` on the result.

**A build ships the pinned archive or none** (owner's choice).
`public/tiles/` is only for the dev server: the fetch links it to the cached
archive (`web/.cache/tiles/<sha256>.pmtiles`) unless a tile builder has linked
their own build there. `vite-plugins/tiles.ts` drops whatever Vite copied from
it, and puts the verified pinned archive into `dist/`, or none with
`VITE_TILES_URL`. It also stops the build at its start when the glyphs or the
archive are missing (owner's choice over a warning).

**Planetiler's own inputs are pinned.** `build.sh` no longer uses
`--download`. Natural Earth 5.1.2 and the water polygons (2026-09-14) have no
versioned URL upstream, so they are mirrored as assets of the
`tile-sources-2026-09-30` release (owner's choice over pinning the upstream
URLs by hash, which would break with every upstream update). The lake
centerlines are the `v12` release Planetiler itself pins. All three are
verified by sha256. `SNAPSHOT=yymmdd` builds from Geofabrik's dated extract of
that day; the name pipeline stays on `-latest`.

**Why**: a frontend contributor or CI could not get a map without running the
whole tile pipeline, and two builds from the same commit could differ in their
inputs. A build also shipped whichever archive happened to be linked, with no
record of which one.

## Decided 2026-09-30: one command after an edit, `just update` (issue #57)

Adding a place meant knowing which of `check.py --fix`, `curate.py apply`,
`just candidates`, `match.py`, `just objects`, `just areas`, `just index`
(with `just dialects`), `curate.py export` and `just check-outputs` to run, and
in which order. `uv run just update`
(`frasch/update.py`) now runs all of them in that order and ends with the
files it changed and the rows left to curate. Owner's choices:

- **A Python command behind a `just` recipe**, not a recipe chaining the
  others: just has no timestamps, so a pure recipe would rescan the extracts
  (~8 min) on every run, and it could not be tested.
- **Slow steps are skipped when their inputs did not change**: the candidate
  scan when `candidates.jsonl`'s header names the current extracts,
  `locate.py` when `osm_objects.json` holds exactly the references of the
  rows on the map and comes from the current extracts, the dialect areas when
  their stamp names the current area list, registry and extract. The rest
  runs every time; it takes seconds.
- **No tiles**: they need Java and minutes of Planetiler, and are not
  committed. The summary points to `just tiles`.

A failing step stops the run. The exception is a decision that `curate.py
apply` refuses: it stays in the patch as before, and the rest of the run
goes on (the command exits 1). Otherwise one stale decision in the browser
would block every update. Nothing is committed automatically.

## Decided 2026-10-01: the list's German name is the tiles' `name:de` (issue #61)

The injector writes the first variant of a row's `de` as `name:de` on every
object the row tags, in place of OSM's own. Where the list has no German name,
OSM's `name:de` stays. `check_tiles.py` holds the tiles to it like the
dialect and the local name.

**Why**: the label chain's `name:de` step read two different things. The map
took OSM's `name:de` from the tile, while the place card and the search
results took the list's `de` from names.json. With today's data no listed
place reaches that step: a row is on the map only with a Frisian name, and
the dialect chain tries every dialect first. The local view reaches it only
for an object without an OSM `name`. But it would have split as soon as one
did. Writing the list's name into the tiles makes the two sides agree by
construction, and the map's German fallback follows the curated list rather
than OSM. The other option was to carry OSM's `name:de` in names.json beside
the list's (as `name_osm` does for `name`, #32). That would have kept OSM's
German names on the map. It changes 5 objects today, e.g. *Norddorf auf
Amrum* → *Norddorf* and *Glücksburg (Ostsee)* → *Glücksburg*.

## Decided 2026-10-02: one command per routine task (issue #74)

The root `justfile` is the one entry point, `uv run just` (owner's choice
over a global `just`, which would no longer be pinned by `uv.lock`). Its
recipes are grouped: **everyday** (`setup`, `dev`, `check`, `check-python`,
`format`, `build`, `smoke`), **name pipeline** (`update`, `check-outputs`,
which was `check` before), **tiles**, and **pipeline steps**, the single steps
`update` runs, kept for running one by hand (owner's choice over hiding or
removing them). Commands that take arguments (`check.py --fix`, `curate.py`,
`match.py --dry-run`) stay as they are.

- **`check` runs every check and lists the failed ones at the end** (owner's
  choice over stopping at the first), through `scripts/run-all.sh`. One
  runner serves both sides; `web/` calls it as `../scripts/run-all.sh`.
- **`web/` still needs no Python** (#28): `npm run check`, `npm run build` and
  `npm run smoke` hold the web side's steps, and the `just` recipes only call
  them.
- **Every build is checked**: `npm run build` ends with `check-build.mjs`
  (owner's choice), and `npm run smoke` builds first.
- **CI calls the composite commands** (`just check-python`, `npm run check`,
  `npm run smoke`), so CI and a local run cannot drift. The price is one CI
  step per side instead of one per check: a failure is found in the log
  (`run-all:` marks each command and lists the failed ones), not by the
  step's name. In CI `check-python` writes pytest's and `names/check.py`'s
  overviews to the run's summary page, as the separate steps did.

**Why**: checking before a push took 11 commands, building and smoke-testing
three more, and CI listed each again. The same tool was called three ways
(`.venv/bin/…`, `uv run just …`, `npm run …`), and `just --list` put the
routine recipes and the pipeline's internals side by side.

## Decided 2026-10-02: ship only the glyph ranges the labels need (issue #29)

`dist/fonts/` held all 256 ranges of each of the three Noto Sans stacks,
102 MB, almost all of it scripts no label of the map uses. Now it holds the
10 ranges `web/fonts.lock` lists, ~2.6 MB.

- **A committed list, checked by the build** (owner's choice over deriving
  the ranges from the archive at every build): what `dist/` ships is
  reviewed in git, and the build stops when a label of the pinned archive
  needs a range the list lacks.
- **The list is the Latin blocks and punctuation plus what a survey of the
  archive found** (owner's choice over the survey alone): 0–1023, Latin
  Extended Additional, General Punctuation, and the survey's Number Forms,
  Miscellaneous Symbols, CJK punctuation and variation selectors. Mooring
  ä ö ü å and Sölring đ ā are in the first two (owner's requirement).
- **Every code point counts** (owner's choice over mirroring MapLibre): MapLibre
  draws CJK punctuation and multi-code-point clusters itself and does not
  request their range, but that is its internals; the check requires a range
  for every character a label has.
- **`fetch-fonts.sh` keeps only the listed ranges** (owner's choice over
  trimming them in the build): the dev server serves what production
  serves. The list lives in `web/fonts.lock` with the zip's URL and sha256
  (owner's choice over a separate ranges file).
- **With `VITE_TILES_URL`** the fetched archive is checked if there is one,
  else the build warns (owner's choice over requiring the archive).

**Why**: every deploy uploaded 102 MB of glyphs, and a range that is missing
shows: MapLibre then draws the glyph locally in another font, and the smoke
check reports the 404.

## Decided 2026-10-03: inside a dialect area OSM's `name:frr` is the local name (issue #81)

The local view labelled a place inside a dialect area in German when the name
list did not have it, although OSM names it in Frisian: the Fahretoft warft
*Kirchwarft* has `name:frr=Schörkeweerw`. `name:frr` is left out of the local
chain on purpose, because outside the areas it is a Frisian exonym (Pinneberg
→ *Pinebärj*). Inside an area the reasoning is reversed: there it is almost
always the local form. Owner's choices:

- **The injector writes it into `frasch:local`**, the label chain stays as it
  is (owner's choice over a `within` branch in the style's `text-field`,
  which would have needed the dialect areas in the browser and the click
  position on the card).
- **Every object**, not only places: streets, stations and offices with a
  `name:frr` inside an area get the Frisian label too. One rule, no class
  list to maintain.
- **Listed objects too**: a row's own local name wins, but where the list
  gives none, OSM's `name:frr` is it. Otherwise adding a place to
  `places.csv` with only a Mooring name would take its Frisian label away.
  `osm_objects.json` records `name_frr` for this, and `names.json`'s `local`
  follows the same rule (`dialects.osm_local_name`), so map, card and search
  agree. 18 search entries gained a `local` this way, e.g. Husum → *Hüsem*.
- **The objects without a row are located by a pre-pass of the injector**
  over the extract it is tagging (owner's choice over recording them in
  `osm_objects.json`): a new `name:frr` in OSM is on the map with the next
  tile build, and the committed file stays "the objects of the name list".
  This is no return to the injector's own positions for *listed* objects
  (2026-09-27): those still come from the file, because the search index
  needs the same answer. An object without a row has no search entry to
  disagree with.

Consequence: in a dialect view the chain is `name:<dialect>` → `frasch:local`
→ the other dialects → `name:frr`. A listed place without a name in the
selected dialect and without a local name from the list used to show another
dialect's list name; inside an area it now shows OSM's `name:frr` first.

In the Schleswig-Holstein extract of 2026-09-22, 532 objects carry
`name:frr`; 397 of them lie in a dialect area. The injector gives 167 objects
no row claims their local name from it (mostly town signs, which no tile
layer labels, then streets, stations, Warften mapped as `landuse`, places,
boundaries and waters) and 21 objects the list claims. 20 of those are
referenced by a row itself (19 rows), which is what `osm_objects.json`
shows; an entry stands for the first object of its row, hence the 18 search
entries above.

The place card follows: for a clicked feature its own `frasch:local` now
wins over the entry's `local` and brings its `frasch:dialect` along
(`cardEntry` in `web/src/names.ts`). An entry
lies where the first object of its row lies, so its local name may be that
object's OSM name, while a second object of the row lies in another area and
has a list name there (Nordwarft: the way on the Hallig, the node in the
Nordergoesharde).

## Decided 2026-10-03: a dangling link in `public/tiles/` stops the build with a hint (issue #53)

A tile builder's link in `web/public/tiles/` to an archive that is not built
yet failed `npm run build` inside Vite's copy of `public/`, with a bare
`ENOENT`, although the build ships the pinned archive anyway.
`vite-plugins/tiles.ts` now names every such link at the build's start, with
the two ways out: build the tiles, or remove the link and run
`npm run fetch-tiles` (owner's choice over a plugin that takes over Vite's
copy of `public/` and builds anyway). It does so with `VITE_TILES_URL` too.
`npm run fetch-tiles` keeps a link that is not its own even when it dangles,
but warns instead of saying the dev server serves it (owner's choice over
replacing it: the link may have been set ahead of the first tile build).

## Decided 2026-10-06: one `frasch` command, no launchers (issue #91)

This supersedes the 2026-09-28 decision to keep `names/*.py` and
`tiles/*.py` as thin launchers (issue #25). The 13 launchers are deleted; the
package `frasch/` is run as one installed command, `uv run frasch <command>`
(`frasch <command>` inside the venv): `[project.scripts]` in `pyproject.toml`
points at the command table in `frasch/__main__.py`. The justfile, `tiles/build.sh`,
the docs and the web app's hints name the command instead of a script path.
Earlier entries of this log keep the script names they were written with:

| was | is |
|---|---|
| `names/check.py` | `frasch check-inputs` (and a new `just check-inputs`) |
| `names/check_built.py` | `frasch check-outputs` |
| `names/build_candidates.py` | `frasch candidates` |
| `names/match.py` | `frasch match` |
| `names/locate.py` | `frasch objects` |
| `names/build_dialect_areas.py` | `frasch areas` |
| `names/dialects.py` | `frasch dialects` |
| `names/export_search_index.py` | `frasch index` |
| `names/provenance.py` | `frasch provenance` |
| `names/update.py` | `frasch update` |
| `names/curate.py` | `frasch curate` (`export` / `apply`) |
| `tiles/inject_names.py` | `frasch inject` |
| `tiles/check_tiles.py` | `frasch check-tiles` |

- **The file layout is one object**: `frasch.paths.Workspace`, a dataclass with
  one attribute per file of the pipeline; `Workspace.default()` is the
  repository's layout. A command takes the paths from it, whatever the
  working directory.
- **One flag vocabulary**: a flag names the same file in every command
  (`--names`, `--dialects`, `--curation`, `--area-list`, `--areas`, `--parts`,
  `--objects`, `--index`, `--registry-json`, `--report`, ..., and `--work` for
  the scratch directory). Renamed to make that true: `--registry` is
  `--dialects`; the area list is `--area-list` and `--areas` is the geojson
  (it was the csv in `check.py` and `build_dialect_areas.py`); `--parts-out`
  is `--parts`. `--out` is gone: an output is named by its file's flag
  (`frasch objects --objects`, `frasch index --index`). `dialects --export`
  is a switch that writes the file `--registry-json` names. `tiles/build.sh`
  passes `NAMES`, `DIALECTS`, `AREAS`, `OBJECTS` and `CURATION` on only when
  the environment variable is set; otherwise the command's own default holds.
  A command takes only the flags of the files it works on
  (`cli.add_workspace_options`), so a path it would ignore is an error.
  Two options made way for the vocabulary: `frasch candidates --index`
  (pyosmium's node index) is `--location-index`, and `--parts-out ''` is
  `frasch areas --no-parts`.
- **Typed functions under every command**: a command's `main()` parses and
  calls a function that takes the `Workspace` and the `Registry`
  (`locate.build`, `match.run`, `curate.apply`, ...); `update` and
  `check-outputs` call those functions instead of other commands' `main()`
  with argument lists. `update` reads the registry once -- its first step,
  the input check, hands it to the later ones --, so `update --dialects X`
  uses X in every step. The parsers take no abbreviated options
  (`cli.parser`): the old `--registry` must not pass for `--registry-json`.
- **The tests have a dialect registry of their own** (`names/tests/conftest.py`)
  and work on a `Workspace` in a temp directory through the typed functions;
  each command keeps one test through `frasch.__main__.main`. No test reads
  `names/dialects.csv`.
- **The dialect registry is always passed explicitly**: `registry.default()`
  (a default registry, read on first use) is removed; every command
  reads it from `--dialects` and hands it down.
- **Modules**: `check` is `check_inputs` and `check_built` is `check_outputs`;
  `export_search_index` is merged into `searchindex`, `print_provenance` into
  `provenance` and `export_dialects` into `registry`. The other modules keep
  their names. See `names/README.md#code`.

## Decided 2026-10-06: one reader for the four hand-edited tables (issue #92)

`places.csv`, `curation.csv`, `dialects.csv` and `dialect_areas.csv` had four
hand-written CSV readers with three behaviours. They are now parsed in one
place, `frasch/tables.py`: `read_table` owns the byte order mark, the
`;`-separated export, columns named twice or missing, the cell count of every
row, blank lines and the line number an editor sees; `write_rows` writes
them. Each file's module keeps only the rules of its rows, and each file is
opened by one function. So all four now answer a `;`-separated export and a
row with a comma too many or too few with the same message, and name the true
line after a blank one — the area list did none of the three, and `places.csv`
refused a comma-short row only by accident.

- **Every documented column is required**, for every command alike:
  `curation.csv` needs all nine (`frasch check-inputs` and the tile build used
  to need only `osm`, `frasch curate apply` all of them), `dialect_areas.csv`
  all four (`name` and `note` were optional). A column of your own beyond
  them is still fine.
- **A problem has one shape**: `errors.Problem(path, line, message)`. A
  `ValidationError` means "a hand-edited file breaks its rules" and carries a
  list of them. What cannot name a line of such a file — an unknown dialect
  tag, a local reference without a position at build time, an old
  `work/matches.csv` — is a plain `PipelineError`; `Invalid` (one cell that
  breaks the rules) is one too. Messages and exit codes are unchanged.

## Decided 2026-10-06: the pipeline is defined once (issue #95)

For each generated file there were three answers to "what makes it, from
what, and is it current": a just recipe, a step of `frasch update` with its
own staleness rule, and a check in `frasch check-outputs` with the recipe's
name as a string. The two Python sides disagreed (for the dialect areas
`update` compared the whole stamp, the check only its hashes; for the objects
`update` wanted exactly the references on the map, the check only that none
was missing), and `REPORT.md` was committed without any check.

- **One table, `frasch/pipeline.py`**: an `Output` per generated file —
  `candidates`, `report`, `objects`, `areas`, `dialects`, `index` — with its
  files, what it is built from, `build` and `stale()`. `frasch update` builds
  the table's outputs in order, `frasch check-outputs` reports the committed
  ones that are stale or that a rebuild gives another file for, and
  `frasch build <name>` builds one. A new generated file is one entry.
- **One `stale()` for both.** The extracts are compared where they are at
  hand (`update`, `check-full`) and only the inputs where they are not (CI).
  For the objects it is `update`'s rule: located for exactly the references
  the rows on the map name, so a row taken off the map needs a rebuild too.
  The report is written from the candidates, so its extracts are compared
  with theirs, where there are candidates: after a new download the
  candidates are stale, and the report only once they were scanned again —
  rebuilding it earlier could not help.
- **`update` skips only a scan of an extract** (candidates, objects, dialect
  areas) whose output is not stale. The matcher runs every time (owner's
  decision): it changes `places.csv` and depends on Wikidata's answers,
  which no stamp covers. The frontend's registry and the search index are
  cheap and are built every time as well.
- **One `Stamp`** (`frasch/provenance.py`): `Stamp.of` makes it, `Stamp.read`
  reads it from any stamped file, `Stamp.other_than` says which inputs
  differ. Where a file carries it did not change — `built_from` at the top of
  a JSON file (the tiles carry the same object as `names.json`), in the
  `properties` of a GeoJSON, as the header line of `candidates.jsonl` — so no
  committed file changed and the candidates need no rescan.
  `dialects.json` carries none: the frontend compiles the array in, and its
  check is the byte comparison.
- **`osm_objects.json` records what was asked for**: `not_found` lists the
  references no extract holds (left out when empty, so the committed file
  stayed byte-identical and `names.json`'s stamp still matches the published
  tiles). Such a reference used to make `update` locate again on every run,
  with the advice to run `just objects`, which could not help. Now it is not
  stale, and one message (`objects.unlocated`) tells the two cases apart: not
  located yet, or in no extract — then the row's `osm` cell is to correct.
- **`REPORT.md` is stamped and checked** (owner's decision: it stays
  committed). Its last line is a comment with the stamp: `places.csv` as the
  matcher left it, `dialects.csv`, and the extracts behind the candidates. It
  cannot be rebuilt in CI, because the matcher needs the git-ignored
  candidates, so its check is the stamp. The consequence: after an edit to
  `places.csv` or `dialects.csv`, CI fails until `just update` (or
  `frasch match`) has rewritten the report. `work/match-extracts.json` is
  gone; the matcher's "other extracts than the last match" warning compares
  with the report's stamp.
- **Recipes and commands** (owner's decisions): the recipes `objects`,
  `areas`, `dialects`, `index` and `candidates` became `just rebuild <name>`
  (`just build` is the site's), which runs `frasch build <name>` and
  downloads the extracts only for an output the table says is built from
  them (`frasch build <name> --scans`), as `index` and `dialects` needed
  none before. The
  commands `frasch objects`, `frasch index` and `frasch dialects --export`
  went, since `frasch build` does the same; `frasch areas` and
  `frasch candidates` stay for their own options. `just check-full` rebuilds
  each file from the extracts it is given and no longer picks them by the
  file names in each stamp.

## Remaining open questions
1. Hosting provider for the site (R2 + Pages proposed, nothing set up yet); the tiles are GitHub release assets for now (issue #28).
2. When to do the planet build (needs the VM; only after the North Frisia build looks right).
3. Whether to also push confirmed names to OSM `name:frr` (separate track; import guidelines).

## Name-mapping pipeline (built 2026-09-15)

Scripts in `names/` (see `names/README.md` for the workflow; since #91 they are the commands of `frasch`, see the 2026-10-06 entry): `placelist.py` (reads/validates `places.csv`, shared); `build_candidates.py` (one pyosmium pass over the SH + DK extracts, ~8.5 min, 182k candidates); `match.py` (exact match after normalisation, no fuzzy matching; fills empty `osm`/`wikidata` cells of `places.csv` and marks them `status=auto`; writes `names/work/matches.csv` with the details and `names/REPORT.md` as the hand-review worklist); `tiles/inject_names.py` (tags the PBF). Keys: OSM reference `type/id` (several allowed for split rivers/dykes) plus the Wikidata QID where the object has one; countries via Wikidata only.

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
- **Python**: `uv` at `~/.local/bin/uv`; `uv sync` creates the project venv `.venv` (Python 3.12) from `pyproject.toml` / `uv.lock` (osmium, shapely, requests; pytest, ruff (lint and format) and mypy -- strict, tests included -- for development), see the root `README.md`. System Python 3.14 has no pip/venv.
- **pmtiles CLI** at `~/.local/bin/pmtiles` for inspecting archives.
- Docker is not needed with Planetiler.
- **Node v24.21.0 (LTS, npm 11.19.0)** installed in WSL via nvm 0.40.7 and set as the default (`lts/*`). Pin the version in `.nvmrc` once `web/` is scaffolded. Note: a Windows Node install exists at `/mnt/d/Program Files/nodejs/`; make sure WSL shells use the nvm one.
- **Docker is not available in WSL**; enable Docker Desktop WSL integration or install Docker Engine.
- Planetiler requires Java 21+.

## Next steps
1. Hand-review the *ambiguous* / *not found* rows in `names/REPORT.md`; write `osm` references (and `ok`/`skip`) into `names/places.csv`.
2. Run `tiles/build.sh schleswig-holstein`, open the web app, check labels.
3. Translate the UI strings in `web/src/locales/frr-x-mooring.json`.
4. Choose hosting; first deployment of the SH build.
5. Extend name matching to Denmark tiles (Rudbøl, Rømø, Tønder …) and country names via Wikidata.
6. Planet build on a rented VM.
