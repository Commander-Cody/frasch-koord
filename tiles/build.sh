#!/usr/bin/env bash
# Build an OpenMapTiles-schema PMTiles archive with North Frisian names merged in.
#
# Usage: tiles/build.sh <region> [planetiler args...]
#   region  = Geofabrik file stem in tiles/data, e.g. schleswig-holstein (expects
#             tiles/data/<region>-latest.osm.pbf; downloaded automatically if missing)
#
# Steps: 1. inject name:<dialect> + frasch:kind tags from names/places.csv and
#           the set_tags / frasch:minzoom / frasch:maxzoom of names/curation.csv into the PBF
#        2. run Planetiler (stock OpenMapTiles profile, no fork) on the result
#
# Env: JAVA_HOME (default ~/.local/opt/jdk-21*), XMX (default 3g),
#      DIALECT (default frr-x-mooring), NAMES, CURATION
#
# Tip: add --bounds=8.3,54.35,8.95,54.8 for a ~1 min Halligen-area test build.
set -euo pipefail
cd "$(dirname "$0")"
REGION="${1:?region name, e.g. schleswig-holstein}"; shift || true
DIALECT="${DIALECT:-frr-x-mooring}"
XMX="${XMX:-3g}"
JAVA_HOME="${JAVA_HOME:-$(ls -d ~/.local/opt/jdk-21* | head -1)}"
PY="../.venv/bin/python"
NAMES="${NAMES:-../names/places.csv}"
CURATION="${CURATION:-../names/curation.csv}"
SRC="data/${REGION}-latest.osm.pbf"
INJECTED="data/${REGION}-${DIALECT}.osm.pbf"
OUT="data/${REGION}.pmtiles"

[ -f planetiler.jar ] || curl -sL https://github.com/onthegomap/planetiler/releases/latest/download/planetiler.jar -o planetiler.jar
[ -f "$SRC" ] || curl -L "https://download.geofabrik.de/europe/germany/${REGION}-latest.osm.pbf" -o "$SRC"

echo "== injecting names ($DIALECT) + curation into $SRC"
"$PY" inject_names.py "$SRC" "$INJECTED" \
  --names "$NAMES" --curation "$CURATION" --dialect "$DIALECT"

echo "== building $OUT"
# --languages:       which name:* tags end up in the tiles. Keep the dialect tags
#                    in sync with names/.
# --extra_name_tags: stock Planetiler passes these through verbatim as string
#                    attributes on the labelled features -- that is how the
#                    frasch:* tags written by inject_names.py reach the style.
"$JAVA_HOME/bin/java" -Xmx"$XMX" -jar planetiler.jar \
  --osm-path="$INJECTED" \
  --download \
  --output="$OUT" \
  --languages="de,da,nds,frr,${DIALECT}" \
  --extra_name_tags=frasch:kind,frasch:minzoom,frasch:maxzoom \
  --force "$@"
ls -la "$OUT"
