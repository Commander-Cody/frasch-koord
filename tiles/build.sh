#!/usr/bin/env bash
# Build an OpenMapTiles-schema PMTiles archive with North Frisian names merged in.
#
# Usage: tiles/build.sh <region> [planetiler args...]
#   region  = a Geofabrik path: either a bare file stem, meaning
#             europe/germany/<region> (e.g. schleswig-holstein), or a full
#             path (e.g. europe/denmark, europe/germany/schleswig-holstein).
#             Its last path component names the files in tiles/data:
#             <stem>-latest.osm.pbf (downloaded automatically if missing)
#             and <stem>.pmtiles (the build output).
#
# Steps: 1. inject a name:<tag> per dialect (names/dialects.csv) + the frasch:*
#           attributes from names/places.csv, names/dialect_areas.geojson,
#           names/osm_objects.json and the set_tags / frasch:minzoom /
#           frasch:maxzoom of names/curation.csv into the PBF
#        2. run Planetiler (stock OpenMapTiles profile, no fork) on the result,
#           stamping the archive with what it was built from (the same
#           `built_from` names.json carries, see names/provenance.py)
#
# Env: JAVA_HOME (default ~/.local/opt/jdk-21*, else `java` on PATH),
#      XMX (default 3g), NAMES, DIALECTS, AREAS, OBJECTS, CURATION,
#      REFRESH=1 to re-download the extract even if one is already present
#
# Tip: add --bounds=8.3,54.35,8.95,54.8 for a ~1 min Halligen-area test build.
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck source=tiles/fetch.sh
source ./fetch.sh
# shellcheck source=tiles/java.sh
source ./java.sh

# Planetiler pinned to the version the current tiles were built with, and
# verified by sha256 -- see fetch.sh for why a plain download is not enough.
PLANETILER_VERSION="0.10.2"
PLANETILER_URL="https://github.com/onthegomap/planetiler/releases/download/v${PLANETILER_VERSION}/planetiler.jar"
PLANETILER_SHA256="f310bd0413e2e4512b27f4046d418664e8e1d3bf31603c2a70e23de06c167e4d"

REGION_ARG="${1:?region name, e.g. schleswig-holstein or europe/denmark}"; shift || true
XMX="${XMX:-3g}"
PY="../.venv/bin/python"
NAMES="${NAMES:-../names/places.csv}"
DIALECTS="${DIALECTS:-../names/dialects.csv}"
AREAS="${AREAS:-../names/dialect_areas.geojson}"
OBJECTS="${OBJECTS:-../names/osm_objects.json}"
CURATION="${CURATION:-../names/curation.csv}"

# -- up-front checks, so a missing Java/Python fails fast with a clear message ---
JAVA_HOME=$(find_java_home)
JAVA_BIN="$JAVA_HOME/bin/java"
[ -x "$JAVA_BIN" ] || { echo "build.sh: $JAVA_BIN is not executable (bad JAVA_HOME?)" >&2; exit 1; }
JAVA_VERSION_LINE=$("$JAVA_BIN" -version 2>&1 | head -1)
if ! JAVA_MAJOR=$(java_major "$JAVA_VERSION_LINE") || [ "$JAVA_MAJOR" -lt 21 ]; then
  echo "build.sh: Java 21+ required, found: $JAVA_VERSION_LINE" >&2
  exit 1
fi

[ -x "$PY" ] || { echo "build.sh: $PY not found or not executable -- run 'uv sync' first" >&2; exit 1; }

REGION_PATH=$(geofabrik_path "$REGION_ARG")
STEM=$(region_stem "$REGION_ARG")
SRC="data/${STEM}-latest.osm.pbf"
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

# every dialect of the registry, e.g. frr-x-mooring,frr-x-fering,... -- the
# list Planetiler has to carry into the tiles
TAGS=$("$PY" ../names/dialects.py --registry "$DIALECTS" --tags)

if [ ! -f planetiler.jar ]; then
  fetch_verified "$PLANETILER_URL" planetiler.jar sha256 "$PLANETILER_SHA256"
elif [ "$(sha256sum planetiler.jar | cut -d' ' -f1)" != "$PLANETILER_SHA256" ]; then
  echo "build.sh: tiles/planetiler.jar does not match the pinned v${PLANETILER_VERSION} (sha256 ${PLANETILER_SHA256}) -- delete it to have it re-downloaded" >&2
  exit 1
fi

if [ "${REFRESH:-}" = "1" ] || [ ! -f "$SRC" ]; then
  fetch_geofabrik_verified "https://download.geofabrik.de/${REGION_PATH}-latest.osm.pbf" "$SRC"
fi

echo "== injecting names ($TAGS) + areas + curation into $SRC"
"$PY" inject_names.py "$SRC" "$INJECTED_TMP" \
  --names "$NAMES" --dialects "$DIALECTS" --areas "$AREAS" --objects "$OBJECTS" \
  --curation "$CURATION"
mv "$INJECTED_TMP" "$INJECTED"
BUILT_FROM=$("$PY" ../names/provenance.py --names "$NAMES" --dialects "$DIALECTS" \
  --curation "$CURATION" --areas "$AREAS" --objects "$OBJECTS")

echo "== building $OUT"
# --languages:       which name:* tags end up in the tiles. The dialect tags come
#                    from names/dialects.csv, so the registry stays the one list.
# --extra_name_tags: stock Planetiler passes these through verbatim as string
#                    attributes on the labelled features -- that is how the
#                    frasch:* tags written by inject_names.py reach the style.
# --archive_description: the build's `built_from` stamp; the frontend compares
#                    it with names.json's (web/src/provenance.ts). Planetiler
#                    records the extract's replication time by itself.
"$JAVA_BIN" -Xmx"$XMX" -jar planetiler.jar \
  --osm-path="$INJECTED" \
  --download \
  --output="$OUT_TMP" \
  --languages="de,da,nds,frr,${TAGS}" \
  --extra_name_tags=frasch:kind,frasch:minzoom,frasch:maxzoom,frasch:dialect,frasch:local,frasch:variety,frasch:ref \
  --archive_description="$BUILT_FROM" \
  --force "$@"
mv "$OUT_TMP" "$OUT"
ls -la "$OUT"
