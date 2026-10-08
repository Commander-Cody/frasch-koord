#!/usr/bin/env bash
# Which tags of the injected extract Planetiler carries into the tiles.
# Meant to be sourced, not run: `source ./nametags.sh` from build.sh, or from
# tiles/tests/test_nametags.py. Needs workspace.sh sourced first.
#
# Public functions:
#   name_tag_options <frasch>
#     Sets the array NAME_TAG_OPTIONS to the two Planetiler options that say
#     so, asking the command <frasch> for both lists, so that neither is
#     spelled out here:
#       --languages        which name:* tags end up in the tiles: German,
#                          Danish, Low Saxon and OSM's own Frisian, and one
#                          per dialect of the registry (`frasch dialects
#                          --tags`; names/dialects.csv, or $DIALECTS)
#       --extra_name_tags  stock Planetiler passes these through verbatim as
#                          string attributes on the labelled features -- that
#                          is how the frasch:* tags written by `frasch inject`
#                          reach the style (`frasch tile-keys`)
set -euo pipefail

name_tag_options() {
  local frasch=$1 dialect_tags attribute_keys
  local -a WORKSPACE_OPTIONS  # the caller's own stay as they are
  workspace_options dialects
  dialect_tags=$("$frasch" dialects --tags "${WORKSPACE_OPTIONS[@]}")
  attribute_keys=$("$frasch" tile-keys)
  # shellcheck disable=SC2034  # read by whoever sources this file
  NAME_TAG_OPTIONS=(
    "--languages=de,da,nds,frr,${dialect_tags}"
    "--extra_name_tags=${attribute_keys}"
  )
}
