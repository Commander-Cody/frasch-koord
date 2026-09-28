"""Shared setup for the tile-build tests: tiles/ (inject_names.py),
names/ (placelist, dialects -- which inject_names imports) and names/tests/
(the fixture helpers the name-pipeline tests use too) on sys.path."""
from __future__ import annotations

import os
import sys

TILES = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
NAMES = os.path.normpath(os.path.join(TILES, "..", "names"))
for path in (os.path.join(NAMES, "tests"), NAMES, TILES):
    if path not in sys.path:
        sys.path.insert(0, path)
