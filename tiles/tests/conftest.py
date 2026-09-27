"""Shared setup for the tile-build tests: tiles/ (inject_names.py) and
names/ (placelist, dialects -- which inject_names imports) on sys.path."""
from __future__ import annotations

import os
import sys

TILES = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
NAMES = os.path.normpath(os.path.join(TILES, "..", "names"))
for path in (NAMES, TILES):
    if path not in sys.path:
        sys.path.insert(0, path)
