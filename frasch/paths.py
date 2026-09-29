"""Where the pipeline's files live by default -- in one place, so that a
command's default and the module that reads the file cannot disagree.  Every
command takes its inputs and outputs as options too; tests pass their own."""
from __future__ import annotations

import os

# what a path parameter takes when the tests pass it a pathlib.Path
StrPath = str | os.PathLike[str]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = os.path.join(ROOT, "names")
WORK = os.path.join(NAMES, "work")          # git-ignored scratch

# the hand-edited inputs
PLACES = os.path.join(NAMES, "places.csv")
DIALECTS = os.path.join(NAMES, "dialects.csv")
CURATION = os.path.join(NAMES, "curation.csv")
DIALECT_AREA_LIST = os.path.join(NAMES, "dialect_areas.csv")
PATCH_SCHEMA = os.path.join(NAMES, "curate-patch.schema.json")

# the committed build outputs
DIALECT_AREAS = os.path.join(NAMES, "dialect_areas.geojson")
DIALECT_AREA_PARTS = os.path.join(NAMES, "dialect_areas_parts.geojson")
OBJECTS = os.path.join(NAMES, "osm_objects.json")
REPORT = os.path.join(NAMES, "REPORT.md")
SEARCH_INDEX = os.path.join(ROOT, "web", "public", "data", "names.json")
REGISTRY_JSON = os.path.join(ROOT, "web", "src", "generated", "dialects.json")

# the scratch files of matching and curation
CANDIDATES = os.path.join(WORK, "candidates.jsonl")
MATCHES = os.path.join(WORK, "matches.csv")
WIKIDATA_CACHE = os.path.join(WORK, "wikidata-countries.json")
WORKLIST = os.path.join(WORK, "curate.json")
PATCH = os.path.join(WORK, "curate-patch.jsonl")
