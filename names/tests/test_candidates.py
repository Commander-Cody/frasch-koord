"""The candidates file's own rules (frasch.candidates).  Writing it is
covered in test_build_candidates.py, reading it in the matcher's tests."""

from __future__ import annotations

import pytest

from frasch import candidates


@pytest.mark.parametrize(
    "extract",
    [
        "tiles/data/schleswig-holstein-latest.osm.pbf",
        "tiles/data/schleswig-holstein-260923.osm.pbf",  # `SNAPSHOT=260923 just tiles`
    ],
)
def test_an_extract_of_schleswig_holstein_is_that_source_whatever_day_it_is_of(
    extract: str,
) -> None:
    assert candidates.is_sh(candidates.source(extract))
