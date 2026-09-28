# The whole pipeline, from the committed name files and the OSM extracts to
# the search index and the tiles.  `uv run just <recipe>` (just is a dev
# dependency; `uv sync` installs it).  `uv run just --list` shows the recipes.
#
#   extracts (download) ─┬─ candidates ── match           the matcher's worklist
#                        ├─ objects ─┐                    names/osm_objects.json
#                        └─ areas ───┼─ index             web/public/data/names.json
#                                    └─ tiles             tiles/data/<region>.pmtiles
#   dialects                                              web/src/generated/dialects.json
#
# `objects`, `areas`, `index` and `dialects` write committed files; `check`
# (CI) proves they match their inputs.  just has no file timestamps: a
# recipe runs when you ask for it, not when its inputs changed.  What a recipe
# needs first is a dependency instead -- `candidates`, `objects`, `areas` and
# `check-full` first run `extracts` (which downloads only what is missing),
# `index` first runs `dialects`; `tiles` downloads its own region's extract.

set shell := ["bash", "-euo", "pipefail", "-c"]

py := "uv run python"
# the region the tiles are built for, and the extracts the name list's
# objects are found in -- North Frisia reaches into Denmark (Fanø, Röm, Ripen)
region := "schleswig-holstein"
extracts := "tiles/data/schleswig-holstein-latest.osm.pbf tiles/data/denmark-latest.osm.pbf"

# list the recipes
default:
    @{{just_executable()}} --list

# download (or with REFRESH=1 re-download) and verify the OSM extracts
extracts:
    #!/usr/bin/env bash
    set -euo pipefail
    source tiles/fetch.sh
    mkdir -p tiles/data
    for region in schleswig-holstein europe/denmark; do
      dest="tiles/data/$(region_stem "$region")-latest.osm.pbf"
      if [ "${REFRESH:-}" = "1" ] || [ ! -f "$dest" ]; then
        fetch_geofabrik_verified "https://download.geofabrik.de/$(geofabrik_path "$region")-latest.osm.pbf" "$dest"
      fi
    done

# scan the extracts for every object that could be a place (names/work/candidates.jsonl)
candidates: extracts
    {{py}} names/build_candidates.py {{extracts}}

# fill the empty osm cells of places.csv (pass --dry-run to only look)
match *args:
    {{py}} names/match.py {{args}}

# locate the name list's objects in the extracts (names/osm_objects.json)
objects: extracts
    {{py}} names/locate.py {{extracts}}

# build the dialect areas from dialect_areas.csv (names/dialect_areas*.geojson)
areas: extracts
    {{py}} names/build_dialect_areas.py tiles/data/schleswig-holstein-latest.osm.pbf

# export the dialect registry for the frontend (web/src/generated/dialects.json)
dialects:
    {{py}} names/dialects.py --export web/src/generated/dialects.json

# export the search index (web/public/data/names.json)
index: dialects
    {{py}} names/export_search_index.py

# build the tiles of a region (tiles/data/<region>.pmtiles); extra args go to Planetiler
tiles region=region *args:
    tiles/build.sh {{region}} {{args}}

# prove the committed outputs match the committed inputs (no extract needed; runs in CI)
check:
    {{py}} names/check_built.py

# like check, and also rebuild objects and areas from the local extracts and compare
check-full: extracts
    {{py}} names/check_built.py --extracts {{extracts}}

# compare a built tile archive with names.json, label by label
check-tiles region=region:
    {{py}} tiles/check_tiles.py tiles/data/{{file_name(region)}}.pmtiles
