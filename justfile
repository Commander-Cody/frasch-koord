# Every routine task of the repository: `uv run just <recipe>` (just is a dev
# dependency; `uv sync` installs it).  `uv run just` lists the recipes by
# group: the everyday ones (set up, run, check, build and smoke-test the
# site), the name pipeline, the tiles, and the pipeline's single steps.  The
# web recipes call web/'s npm scripts and need node on PATH; web/ itself
# builds without Python (`npm run build`, `npm run check`, `npm run smoke`).
#
# The pipeline, from the committed name files and the OSM extracts to the
# search index and the tiles:
#
#   extracts (download) ─┬─ candidates ── match           the matcher's worklist
#                        ├─ objects ─┐                    names/osm_objects.json
#                        └─ areas ───┼─ index             web/public/data/names.json
#                                    └─ tiles             tiles/data/<region>.pmtiles
#                                         └─ publish-tiles  a release + web/tiles.lock
#   dialects                                              web/src/generated/dialects.json
#
# `update` runs the name part of it in one go -- after an edit to places.csv
# or a session in the curation view: ids and checks, the view's decisions,
# candidates, match, objects, areas, the dialect registry, index, the
# worklist for the view, check-outputs.
# It skips the slow steps whose inputs did not change (names/update.py).
#
# `objects`, `areas`, `index` and `dialects` write committed files;
# `check-outputs` (CI) proves they match their inputs.  just has no file
# timestamps: a recipe runs when you ask for it, not when its inputs changed.
# What a recipe needs first is a dependency instead -- `candidates`,
# `objects`, `areas` and `check-full` first run `extracts` (which downloads
# only what is missing), `index` first runs `dialects`; `tiles` downloads its
# own region's extract.

set shell := ["bash", "-euo", "pipefail", "-c"]

py := "uv run python"
# the region the tiles are built for, and the extracts the name list's
# objects are found in -- North Frisia reaches into Denmark (Fanø, Röm, Ripen)
region := "schleswig-holstein"
extracts := "tiles/data/schleswig-holstein-latest.osm.pbf tiles/data/denmark-latest.osm.pbf"
# in CI, where GITHUB_STEP_SUMMARY names the run's summary page, pytest and
# names/check.py write their overviews onto it
summary := env("GITHUB_STEP_SUMMARY", "")
pytest_summary := if summary == "" { "" } else { "--md-report --md-report-flavor gfm --md-report-color never --md-report-zeros empty --md-report-output " + quote(summary) }
names_check_summary := if summary == "" { "" } else { "--summary " + quote(summary) }

# list the recipes
default:
    @{{just_executable()}} --list --unsorted

# once, and after a lockfile change: the venv, web/'s packages, the glyphs and tiles, the smoke test's browser
[group('everyday')]
setup:
    uv sync
    cd web && npm ci
    cd web && npm run fetch-assets
    cd web && npx playwright install chromium-headless-shell

# the map's dev server (also /?curate)
[group('everyday')]
dev:
    cd web && npm run dev

# every static check and test, Python and web; runs them all and lists what failed
[group('everyday')]
check:
    scripts/run-all.sh "{{just_executable()}} check-python" "cd web && npm run check"

# the Python half of check (CI's Python job); in CI also writes the run's summary page
[group('everyday')]
check-python:
    scripts/run-all.sh \
      "uv run ruff check ." \
      "uv run ruff format --check ." \
      "uv run mypy" \
      "uv run pytest {{pytest_summary}}" \
      "{{py}} names/check.py {{names_check_summary}}" \
      "{{just_executable()}} check-outputs" \
      "uv run shellcheck scripts/*.sh tiles/*.sh web/scripts/*.sh"

# format the Python code (ruff format) and the web code (oxfmt)
[group('everyday')]
format:
    uv run ruff format .
    cd web && npm run format

# the production build of the site into web/dist/, checked (needs the fetched glyphs and tiles)
[group('everyday')]
build:
    cd web && npm run build

# build the site, then smoke-test it in headless Chromium
[group('everyday')]
smoke:
    cd web && npm run smoke

# after editing places.csv or curating in /?curate: bring every name file up to date
[group('name pipeline')]
update: extracts
    {{py}} names/update.py {{extracts}} --area-extract tiles/data/schleswig-holstein-latest.osm.pbf

# prove the committed outputs match the committed inputs (no extract needed; runs in CI)
[group('name pipeline')]
check-outputs:
    {{py}} names/check_built.py

# SNAPSHOT=yymmdd builds from Geofabrik's extract of that day instead of the latest one
# build the tiles of a region (tiles/data/<region>.pmtiles); extra args go to Planetiler
[group('tiles')]
tiles region=region *args:
    tiles/build.sh {{region}} {{args}}

# compare a built tile archive with names.json, label by label
[group('tiles')]
check-tiles region=region:
    {{py}} tiles/check_tiles.py tiles/data/{{file_name(region)}}.pmtiles

# publish the built tiles as a GitHub release and pin web/tiles.lock to them (needs gh)
[group('tiles')]
publish-tiles:
    tiles/publish.sh {{region}}

# download (or with REFRESH=1 re-download) and verify the OSM extracts
[group('pipeline steps')]
extracts:
    #!/usr/bin/env bash
    set -euo pipefail
    source tiles/fetch.sh
    mkdir -p tiles/data
    for region in schleswig-holstein europe/denmark; do
      dest="tiles/data/$(geofabrik_extract_name "$region")"
      if [ "${REFRESH:-}" = "1" ] || [ ! -f "$dest" ]; then
        fetch_geofabrik_verified "$(geofabrik_extract_url "$region")" "$dest"
      fi
    done

# scan the extracts for every object that could be a place (names/work/candidates.jsonl)
[group('pipeline steps')]
candidates: extracts
    {{py}} names/build_candidates.py {{extracts}}

# fill the empty osm cells of places.csv (pass --dry-run to only look)
[group('pipeline steps')]
match *args:
    {{py}} names/match.py {{args}}

# locate the name list's objects in the extracts (names/osm_objects.json)
[group('pipeline steps')]
objects: extracts
    {{py}} names/locate.py {{extracts}}

# build the dialect areas from dialect_areas.csv (names/dialect_areas*.geojson)
[group('pipeline steps')]
areas: extracts
    {{py}} names/build_dialect_areas.py tiles/data/schleswig-holstein-latest.osm.pbf

# export the dialect registry for the frontend (web/src/generated/dialects.json)
[group('pipeline steps')]
dialects:
    {{py}} names/dialects.py --export web/src/generated/dialects.json

# export the search index (web/public/data/names.json)
[group('pipeline steps')]
index: dialects
    {{py}} names/export_search_index.py

# like check-outputs, and also rebuild objects and areas from the local extracts and compare
[group('pipeline steps')]
check-full: extracts
    {{py}} names/check_built.py --extracts {{extracts}}
