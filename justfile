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
#   extracts (download) ─┬─ candidates ── report          the matcher's worklist
#                        ├─ objects ─┐                    names/osm_objects.json
#                        └─ areas ───┼─ index             web/public/data/names.json
#                                    └─ tiles             tiles/data/<region>.pmtiles
#                                         └─ publish-tiles  a release + web/tiles.lock
#   dialects                                              web/src/generated/dialects.json
#
# The generated files of its name part -- candidates, report, objects, areas,
# dialects, index -- are defined once, in frasch/pipeline.py: what builds
# each, from what, and when it is stale.  `rebuild <name>` builds one of
# them; `uv run frasch build --help` lists them.
#
# `update` builds them all in one go -- after an edit to places.csv or a
# session in the curation view: ids and check-inputs, the view's decisions,
# the generated files in the order above, the worklist for the view,
# check-outputs.  It skips a scan of the extracts whose output is not stale.
#
# The pipeline's commands are those of `frasch` (`uv run frasch --help`); a
# recipe has its command's name -- but `rebuild`, which runs `frasch build`,
# since `build` is the site's.
#
# All of the generated files but the candidates are committed;
# `check-outputs` (CI) proves they match their inputs.  just has no file
# timestamps: a recipe runs when you ask for it, not when its inputs changed.
# What a recipe needs first is a dependency instead -- `update`, `rebuild`
# and `check-full` first run `extracts` (which downloads only what is
# missing); `tiles` downloads its own region's extract.

set shell := ["bash", "-euo", "pipefail", "-c"]

frasch := "uv run frasch"
# the region the tiles are built for, and the extracts the name list's
# objects are found in -- North Frisia reaches into Denmark (Fanø, Röm, Ripen)
region := "schleswig-holstein"
extracts := "tiles/data/schleswig-holstein-latest.osm.pbf tiles/data/denmark-latest.osm.pbf"
# the one of them the dialect areas are built from
area_extract := "tiles/data/schleswig-holstein-latest.osm.pbf"
# in CI, where GITHUB_STEP_SUMMARY names the run's summary page, pytest and
# `frasch check-inputs` write their overviews onto it
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
      "{{frasch}} check-inputs {{names_check_summary}}" \
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
    {{frasch}} update {{extracts}} --area-extract {{area_extract}}

# check the hand-edited name files for damage (pass --fix to give new rows an id; runs in CI)
[group('name pipeline')]
check-inputs *args:
    {{frasch}} check-inputs {{args}}

# prove the committed outputs match the committed inputs (no extract needed; runs in CI)
[group('name pipeline')]
check-outputs:
    {{frasch}} check-outputs

# SNAPSHOT=yymmdd builds from Geofabrik's extract of that day instead of the latest one
# build the tiles of a region (tiles/data/<region>.pmtiles); extra args go to Planetiler
[group('tiles')]
tiles region=region *args:
    tiles/build.sh {{region}} {{args}}

# compare a built tile archive with names.json, label by label
[group('tiles')]
check-tiles region=region:
    {{frasch}} check-tiles tiles/data/{{file_name(region)}}.pmtiles

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

# build one generated file of the pipeline by its name (`uv run frasch build --help` lists them)
[group('pipeline steps')]
rebuild name: extracts
    {{frasch}} build {{name}} {{extracts}} --area-extract {{area_extract}}

# fill the empty osm cells of places.csv (pass --dry-run to only look)
[group('pipeline steps')]
match *args:
    {{frasch}} match {{args}}

# like check-outputs, and also rebuild objects and areas from the local extracts and compare
[group('pipeline steps')]
check-full: extracts
    {{frasch}} check-outputs --extracts {{extracts}} --area-extract {{area_extract}}
