# tiles/

Vector tile build (OpenMapTiles schema → PMTiles) with [Planetiler](https://github.com/onthegomap/planetiler).

- `build.sh <region>` — injects `name:frr-x-mooring` + `frasch:*` tags from `names/places.csv` and `names/curation.csv` into the OSM extract, then runs stock Planetiler. Output: `data/<region>.pmtiles` (the file `web/` symlinks). Add `--bounds=8.3,54.35,8.95,54.8` for a ~1 min Halligen-area test build (but redirect the output, it overwrites the real archive).
- `inject_names.py` — the tag injection step (pyosmium). Works with any OSM PBF, so it is independent of the tile tool. `--dry-run` reports what would be tagged and curated without writing.
- `data/` — downloads and build outputs, not in git. `data/sources/` holds Planetiler's global inputs (Natural Earth, water polygons, lake centerlines; ~1.4 GB, downloaded once).

### The `frasch:*` tile attributes

Planetiler runs with `--extra_name_tags=frasch:kind,frasch:minzoom,frasch:maxzoom`. The stock OpenMapTiles profile passes tags listed there through verbatim, so they arrive as **string** attributes on the labelled `place` features:

| attribute | source | meaning |
|---|---|---|
| `frasch:kind` | `places.csv`'s `kind` column, or `set_tags` in `curation.csv` | `island`, `hallig`, `sand`, `settlement`, `koog`, `harde`, `warft`, `landscape`, `water`, `road`, `country`, `helgoland`, `other` — lets the style give a Hallig a different symbol from an island, even though OMT calls both `class=island` |
| `frasch:minzoom` | `curation.csv`'s `minzoom` column | the earliest zoom the label should appear at. **Planetiler does not enforce this** — it is a hint the style must honour, and it can only push a label later, never earlier. |
| `frasch:maxzoom` | `curation.csv`'s `maxzoom` column | the last zoom (inclusive) the label should be shown at. Style-enforced like `frasch:minzoom`. Nordstrand's synthetic island polygon uses it to hand over to the village label at z12. |

`curation.csv`'s `polygon_km2` makes the injector add a synthetic `place=island` square around a node (new node and way ids above the extract's highest, written in node/way/relation order so Planetiler's node map stays happy). It exists because OMT labels island *nodes* only from z12 but island *polygons* by area from z8, at the polygon's interior point. See `names/README.md`.

Anything that has to change how OMT *classifies* a feature (which class, which rank, which minzoom Planetiler picks) must instead be a real OSM tag, written by `curation.csv`'s `set_tags` before Planetiler runs — see `names/README.md`.

Requirements: JDK 21 (user-local install under `~/.local/opt/jdk-21*`), the repo's Python venv (`.venv`, see `names/README.md`). Memory: `XMX=3g` is enough for Schleswig-Holstein; Germany needs ~8g and a raised WSL memory limit; the planet does not fit on the dev machine (build it on a rented VM with ≥64 GB RAM, then upload the PMTiles).

Planet plan ("the map must never be blank"): one full planet build (~100 GB PMTiles) as the single source; the Frisian name list simply covers only part of it and labels fall back to `name:de` / `name` elsewhere.

## Injector details worth knowing
- Rivers are matched to their `type=waterway` relation, but the OpenMapTiles waterway layer is built from the member ways. The injector reads the relations first and tags every member way that carries the same OSM `name` as the relation (side arms such as "Alte Eider" keep their own name).
- Every name-list row with a Wikidata QID also tags all OSM objects carrying that QID. This is how the North Sea and Wadden Sea labels (offshore `place=sea` nodes, only present in a planet build) and the place node next to a matched boundary relation get their names.
