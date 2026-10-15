"""Shared setup for the tile-build tests: names/tests/ on sys.path, for the
fixture helpers (`conftest`, `osm_fixture`) the name-pipeline tests use too."""

from __future__ import annotations

import os
import sys

import pytest

NAME_TESTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "names", "tests"))
if NAME_TESTS not in sys.path:
    sys.path.insert(0, NAME_TESTS)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--write-scenarios",
        action="store_true",
        help="rewrite the place card's listed scenarios (test_consistency.py) before checking them",
    )
