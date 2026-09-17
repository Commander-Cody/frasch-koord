# tiles/

Vector tile build (OpenMapTiles schema → PMTiles) with [Planetiler](https://github.com/onthegomap/planetiler).

- `build.sh <region>` — injects a `name:<tag>` per dialect + the `frasch:*` tags from `names/places.csv`, `names/dialect_areas.geojson` and `names/curation.csv` into the OSM extract, then runs stock Planetiler. Output: `data/<region>.pmtiles` (the file `web/` symlinks). The injected extract is `data/<region>-frasch.osm.pbf`. Add `--bounds=8.3,54.35,8.95,54.8` for a ~1 min Halligen-area test build (but redirect the output, it overwrites the real archive).
- `inject_names.py` — the tag injection step (pyosmium). Works with any OSM PBF, so it is independent of the tile tool. `--dry-run` reports what would be tagged and curated without writing. A `places.csv` row whose `osm` is a local reference (`local/<slug>`, for a place OSM does not have) gets its position from the matching `curation.csv` row's `lat`/`lon`: a new node, or — with that row's `polygon_km2` — only a synthetic square, no node. See `names/README.md`.
- `data/` — downloads and build outputs, not in git. `data/sources/` holds Planetiler's global inputs (Natural Earth, water polygons, lake centerlines; ~1.4 GB, downloaded once).

```
inject_names.py <in.osm.pbf> <out.osm.pbf>
                [--names ../names/places.csv]          the name list
                [--dialects ../names/dialects.csv]     the registry -> which name:* tags exist
                [--areas ../names/dialect_areas.geojson]  which dialect is spoken where
                [--curation ../names/curation.csv] [--no-curation] [--no-areas]
                [--dry-run]
```

There is no `--dialect` switch any more: **every** dialect of the registry is injected in one pass, and the frontend picks one at display time. The dialect areas are optional — without them the injector warns and writes no `frasch:dialect` (and `frasch:local` only where a row has an explicit `local` name).

### The `frasch:*` tile attributes

Planetiler runs with `--extra_name_tags=frasch:kind,frasch:minzoom,frasch:maxzoom,frasch:dialect,frasch:local,frasch:variety`. The stock OpenMapTiles profile passes tags listed there through verbatim, so they arrive as **string** attributes on the labelled `place` features. The names themselves are ordinary `name:*` attributes: one per dialect of `names/dialects.csv` (`--languages=de,da,nds,frr,$(names/dialects.py --tags)`), e.g. `name:frr-x-mooring`, `name:frr-x-fering`.

| attribute | source | meaning |
|---|---|---|
| `frasch:kind` | `places.csv`'s `kind` column, or `set_tags` in `curation.csv` | `island`, `hallig`, `sand`, `settlement`, `koog`, `harde`, `warft`, `landscape`, `water`, `road`, `country`, `helgoland`, `other` — lets the style give a Hallig a different symbol from an island, even though OMT calls both `class=island` |
| `frasch:minzoom` | `curation.csv`'s `minzoom` column | the earliest zoom the label should appear at. **Planetiler does not enforce this** — it is a hint the style must honour, and it can only push a label later, never earlier. |
| `frasch:maxzoom` | `curation.csv`'s `maxzoom` column | the last zoom (inclusive) the label should be shown at. Style-enforced like `frasch:minzoom`. Nordstrand's synthetic island polygon uses it to hand over to the village label at z12. |
| `frasch:dialect` | `names/dialect_areas.geojson` (point in polygon, smallest area wins) | the dialect spoken **where the object is**, e.g. `frr-x-hallig` — not necessarily a dialect the object has a name in. Absent outside the Frisian areas. |
| `frasch:local` | `places.csv`'s `local` column, else the name in `frasch:dialect`'s column | what the people of the place themselves call it. This is what the local-dialect view labels with: `coalesce(frasch:local, name:nds, name:latin, name)` — deliberately no `name:frr` and no `name:de`. |
| `frasch:variety` | the bracket remark on the primary `local` variant | the name of that local variety, e.g. `Foortuftinge` (Fahretoft) or `ååstermooring`. For the UI to show next to the name. |

`curation.csv`'s `polygon_km2` makes the injector add a synthetic `place=island` square around a node (new node and way ids above the extract's highest, written in node/way/relation order so Planetiler's node map stays happy). The square inherits the node's `name` / `name:*` / `frasch:dialect` / `frasch:local` / `frasch:variety`. It exists because OMT labels island *nodes* only from z12 but island *polygons* by area from z8, at the polygon's interior point. For a local reference (a place OSM does not have), the square centres on the curation row's own `lat`/`lon` instead of an OSM node, and no node is written at all. See `names/README.md`.

Anything that has to change how OMT *classifies* a feature (which class, which rank, which minzoom Planetiler picks) must instead be a real OSM tag, written by `curation.csv`'s `set_tags` before Planetiler runs — see `names/README.md`.

Requirements: JDK 21 (user-local install under `~/.local/opt/jdk-21*`), the repo's Python venv (`.venv`, see `names/README.md`). Memory: `XMX=3g` is enough for Schleswig-Holstein; Germany needs ~8g and a raised WSL memory limit; the planet does not fit on the dev machine (build it on a rented VM with ≥64 GB RAM, then upload the PMTiles).

Planet plan ("the map must never be blank"): one full planet build (~100 GB PMTiles) as the single source; the Frisian name list simply covers only part of it and labels fall back to `name:de` / `name` elsewhere.

## Injector details worth knowing
- Rivers are matched to their `type=waterway` relation, but the OpenMapTiles waterway layer is built from the member ways. The injector reads the relations first and tags every member way that carries the same OSM `name` as the relation (side arms such as "Alte Eider" keep their own name); a member gets the relation's full tag set, dialect area included.
- For the area lookup an object needs a position: a node has its own, a way is placed at its first node, a relation at its `label` / `admin_centre` member or the first node of its first member way. These come from three **id-filtered pre-passes** (matched relations → their member ways → those ways' first nodes, a few seconds on Schleswig-Holstein), never from a location cache for the whole extract — the dev machine has no memory for one. Objects found only through their Wikidata QID therefore have no `frasch:dialect`.
- Two rows claiming the same object are not an error: the first row in file order wins **per tag**, so two rows for one place can contribute different dialects; the rest is reported.
- Every name-list row with a Wikidata QID also tags all OSM objects carrying that QID. This is how the North Sea and Wadden Sea labels (offshore `place=sea` nodes, only present in a planet build) and the place node next to a matched boundary relation get their names.
