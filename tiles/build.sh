#!/usr/bin/env bash
# Build an OpenMapTiles-schema PMTiles archive with North Frisian names merged in.
#
# Usage: tiles/build.sh <region> [planetiler args...]
#   region  = a Geofabrik path: either a bare file stem, meaning
#             europe/germany/<region> (e.g. schleswig-holstein), or a full
#             path (e.g. europe/denmark, europe/germany/schleswig-holstein).
#             Its last path component names the files in tiles/data:
#             <stem>-latest.osm.pbf (downloaded automatically if missing;
#             <stem>-<SNAPSHOT>.osm.pbf with SNAPSHOT set)
#             and <stem>.pmtiles (the build output).
#
# Steps: 1. inject a name:<tag> per dialect (names/dialects.csv) + the frasch:*
#           attributes from names/places.csv, names/dialect_areas.geojson,
#           names/osm_objects.json and the set_tags / frasch:minzoom /
#           frasch:maxzoom of names/curation.csv into the PBF
#        2. run Planetiler (stock OpenMapTiles profile, no fork) on the result,
#           stamping the archive with what it was built from (the same
#           `built_from` names.json carries, see frasch/provenance.py)
#
# Env: JAVA_HOME (default ~/.local/opt/jdk-21*, else `java` on PATH),
#      XMX (default 3g),
#      NAMES, DIALECTS, AREAS, OBJECTS, CURATION to build from another file
#      than the committed one (a path relative to tiles/ or absolute; the
#      defaults are the frasch commands' own, see workspace.sh),
#      REFRESH=1 to re-download the extract even if one is already present,
#      SNAPSHOT=yymmdd (e.g. 260923) to build from the extract Geofabrik dated
#      that day instead of the -latest one
#
# Tip: add --bounds=8.3,54.35,8.95,54.8 for a ~1 min Halligen-area test build.
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck source=tiles/fetch.sh
source ./fetch.sh
# shellcheck source=tiles/java.sh
source ./java.sh
# shellcheck source=tiles/workspace.sh
source ./workspace.sh
# shellcheck source=tiles/nametags.sh
source ./nametags.sh

# Planetiler pinned to the version the current tiles were built with, and
# verified by sha256 -- see fetch.sh for why a plain download is not enough.
PLANETILER_VERSION="0.10.2"
PLANETILER_URL="https://github.com/onthegomap/planetiler/releases/download/v${PLANETILER_VERSION}/planetiler.jar"
PLANETILER_SHA256="f310bd0413e2e4512b27f4046d418664e8e1d3bf31603c2a70e23de06c167e4d"

# Planetiler's global inputs, pinned the same way instead of its unpinned
# `--download`. Natural Earth (5.1.2, public domain) and the water polygons
# (osmdata.openstreetmap.de of 2026-09-14, ODbL, (c) OpenStreetMap contributors)
# have no versioned upstream URL, so they are mirrored as assets of a release
# of this repo; the lake centerlines are the release Planetiler 0.10.2 pins.
SOURCES_DIR="data/sources"
NATURAL_EARTH="$SOURCES_DIR/natural_earth_vector.sqlite.zip"
NATURAL_EARTH_URL="https://github.com/Commander-Cody/frasch-koord/releases/download/tile-sources-2026-09-30/natural_earth_vector.sqlite.zip"
NATURAL_EARTH_SHA256="375da61836d4779dffa8b87887bc4faa94dac77745ba0ee3914bd7cbedf40a02"
WATER_POLYGONS="$SOURCES_DIR/water-polygons-split-3857.zip"
WATER_POLYGONS_URL="https://github.com/Commander-Cody/frasch-koord/releases/download/tile-sources-2026-09-30/water-polygons-split-3857.zip"
WATER_POLYGONS_SHA256="e10d8462782b41bbc280bef91a979786b77ff85ccdb2107dac6570972735f8c6"
LAKE_CENTERLINES="$SOURCES_DIR/lake_centerline.shp.zip"
LAKE_CENTERLINES_URL="https://github.com/acalcutt/osm-lakelines/releases/download/v12/lake_centerline.shp.zip"
LAKE_CENTERLINES_SHA256="6c900507c88fc9f5b5a386f90fd0a42d0495e8755a03d075538fb9a6801a3192"

REGION_ARG="${1:?region name, e.g. schleswig-holstein or europe/denmark}"; shift || true
XMX="${XMX:-3g}"
FRASCH="../.venv/bin/frasch"

# -- up-front checks, so a missing Java or venv fails fast with a clear message ---
JAVA_HOME=$(find_java_home)
JAVA_BIN="$JAVA_HOME/bin/java"
[ -x "$JAVA_BIN" ] || { echo "build.sh: $JAVA_BIN is not executable (bad JAVA_HOME?)" >&2; exit 1; }
JAVA_VERSION_LINE=$("$JAVA_BIN" -version 2>&1 | head -1)
if ! JAVA_MAJOR=$(java_major "$JAVA_VERSION_LINE") || [ "$JAVA_MAJOR" -lt 21 ]; then
  echo "build.sh: Java 21+ required, found: $JAVA_VERSION_LINE" >&2
  exit 1
fi

[ -x "$FRASCH" ] || { echo "build.sh: $FRASCH not found or not executable -- run 'uv sync' first" >&2; exit 1; }

STEM=$(region_stem "$REGION_ARG")
SRC_URL=$(geofabrik_extract_url "$REGION_ARG" "${SNAPSHOT:-}")
SRC="data/$(geofabrik_extract_name "$REGION_ARG" "${SNAPSHOT:-}")"
INJECTED_TMP="data/${STEM}-frasch.tmp.osm.pbf"
INJECTED="data/${STEM}-frasch.osm.pbf"
OUT_TMP="data/${STEM}.tmp.pmtiles"
OUT="data/${STEM}.pmtiles"

mkdir -p data

# Both build outputs are written to a temp path and only mv'd into place once
# complete, so a failed build never disturbs the previous data/<stem>.pmtiles
# (which the dev server serves via a symlink) -- and this trap sweeps up the
# temp files on any failure along the way.
cleanup() {
  rm -f "$INJECTED_TMP" "$OUT_TMP"
}
trap cleanup EXIT

# --languages and --extra_name_tags: the tags Planetiler has to carry into
# the tiles, a name:<tag> per dialect of the registry and the frasch:* ones
name_tag_options "$FRASCH"

# a missing jar or source, or one that fails its pin, is downloaded again
fetch_pinned "$PLANETILER_URL" planetiler.jar "$PLANETILER_SHA256"
fetch_pinned "$NATURAL_EARTH_URL" "$NATURAL_EARTH" "$NATURAL_EARTH_SHA256"
fetch_pinned "$WATER_POLYGONS_URL" "$WATER_POLYGONS" "$WATER_POLYGONS_SHA256"
fetch_pinned "$LAKE_CENTERLINES_URL" "$LAKE_CENTERLINES" "$LAKE_CENTERLINES_SHA256"

if [ "${REFRESH:-}" = "1" ] || [ ! -f "$SRC" ]; then
  fetch_geofabrik_verified "$SRC_URL" "$SRC"
fi

echo "== injecting names + areas + curation into $SRC"
workspace_options names dialects areas objects curation
"$FRASCH" inject "$SRC" "$INJECTED_TMP" "${WORKSPACE_OPTIONS[@]}"
mv "$INJECTED_TMP" "$INJECTED"
BUILT_FROM=$("$FRASCH" provenance "${WORKSPACE_OPTIONS[@]}")

echo "== building $OUT"
# NAME_TAG_OPTIONS:  which name:* and frasch:* tags end up in the tiles
#                    (nametags.sh).
# --archive_description: the build's `built_from` stamp; the frontend compares
#                    it with names.json's (web/src/provenance.ts). Planetiler
#                    records the extract's replication time by itself.
"$JAVA_BIN" -Xmx"$XMX" -jar planetiler.jar \
  --osm-path="$INJECTED" \
  --natural_earth_path="$NATURAL_EARTH" \
  --water_polygons_path="$WATER_POLYGONS" \
  --lake_centerlines_path="$LAKE_CENTERLINES" \
  --output="$OUT_TMP" \
  "${NAME_TAG_OPTIONS[@]}" \
  --archive_description="$BUILT_FROM" \
  --force "$@"
mv "$OUT_TMP" "$OUT"
ls -la "$OUT"
