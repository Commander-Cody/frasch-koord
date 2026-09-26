"""dialects.py: the two name fallbacks (README "The shared name logic") and
the "smallest area containing a point wins" rule of the area lookup."""
from __future__ import annotations

import pytest
from shapely.geometry import box

import dialects
import placelist


@pytest.fixture(scope="module")
def reg():
    return dialects.read()


def row(**cells):
    r = {c: "" for c in placelist.COLUMNS}
    r.update(cells)
    return r


# Hanswarft on Hooge: the Mooring name is the foreign form, the Hallig one is
# what the people there say (README "Dialect areas")
HANSWARFT = row(kind="warft", mooring="Hanswärw", hallig="Hansweerf", de="Hanswarft")
# Broderswarft, Fahretoft: a sub-dialect form in `local` with its variety
BRODERSWARFT = row(kind="warft", mooring="Brouderswärw",
                   local="Brouersweerw (Foortuftinge)", de="Broderswarft")


# ---------------------------------------------------------- dialect_name ---
def test_dialect_name_is_the_dialects_column(reg):
    assert dialects.dialect_name(HANSWARFT, "frr-x-hallig", None, reg) == "Hansweerf"
    assert dialects.dialect_name(HANSWARFT, "frr-x-mooring", None, reg) == "Hanswärw"


def test_dialect_name_is_the_primary_variant(reg):
    r = row(kind="hallig", hallig="Schorkeweerw; Nees-Schorkeweerw")
    assert dialects.dialect_name(r, "frr-x-hallig", None, reg) == "Schorkeweerw"


def test_dialect_name_falls_back_to_local_in_the_areas_own_dialect(reg):
    # the Foortuftinge form IS the name in the dialect spoken at Fahretoft
    assert dialects.dialect_name(BRODERSWARFT, "frr-x-nordgoes", "frr-x-nordgoes",
                                 reg) == "Brouersweerw"


def test_dialect_name_does_not_fall_back_to_local_for_another_dialect(reg):
    assert dialects.dialect_name(BRODERSWARFT, "frr-x-wieding", "frr-x-nordgoes", reg) == ""


def test_dialect_name_does_not_fall_back_outside_any_area(reg):
    assert dialects.dialect_name(BRODERSWARFT, "frr-x-nordgoes", None, reg) == ""


def test_dialect_name_keeps_its_column_over_local(reg):
    # the column wins even in the area's own dialect
    assert dialects.dialect_name(BRODERSWARFT, "frr-x-mooring", "frr-x-mooring",
                                 reg) == "Brouderswärw"


# ------------------------------------------------------------ local_name ---
def test_local_name_is_the_local_column_first(reg):
    assert dialects.local_name(BRODERSWARFT, "frr-x-mooring", reg) == "Brouersweerw"


def test_local_name_is_the_local_column_also_outside_any_area(reg):
    assert dialects.local_name(BRODERSWARFT, None, reg) == "Brouersweerw"


def test_local_name_falls_back_to_the_areas_dialect(reg):
    assert dialects.local_name(HANSWARFT, "frr-x-hallig", reg) == "Hansweerf"


def test_local_name_is_empty_outside_any_area_without_local(reg):
    assert dialects.local_name(HANSWARFT, None, reg) == ""


def test_local_name_is_empty_when_the_area_dialect_has_no_name(reg):
    # a Mooring-only row on Sylt: no Sölring form known, nothing local to say
    r = row(kind="settlement", mooring="Muasem", de="Morsum")
    assert dialects.local_name(r, "frr-x-solring", reg) == ""


# ------------------------------------------------------------- AreaIndex ---
# Nested squares, like the Hamburger Hallig (Halligfriesisch) inside the
# municipality Reußenköge (Mooring)
OUTER = box(8.80, 54.55, 8.95, 54.65)       # Reußenköge
INNER = box(8.82, 54.58, 8.86, 54.60)       # Hamburger Hallig


@pytest.mark.parametrize("polygons", [
    [("frr-x-mooring", OUTER), ("frr-x-hallig", INNER)],
    [("frr-x-hallig", INNER), ("frr-x-mooring", OUTER)],
], ids=["large-first", "small-first"])
def test_the_smallest_area_containing_the_point_wins(polygons):
    areas = dialects.AreaIndex(polygons)
    assert areas.lookup(8.84, 54.59) == "frr-x-hallig"


def test_a_point_only_in_the_large_area_gets_its_dialect():
    areas = dialects.AreaIndex([("frr-x-mooring", OUTER), ("frr-x-hallig", INNER)])
    assert areas.lookup(8.90, 54.62) == "frr-x-mooring"


def test_a_point_outside_every_area_has_no_dialect():
    # Nordstrand has no Frisian area at all
    areas = dialects.AreaIndex([("frr-x-mooring", OUTER), ("frr-x-hallig", INNER)])
    assert areas.lookup(8.87, 54.49) is None


def test_a_point_on_the_outline_is_inside():
    areas = dialects.AreaIndex([("frr-x-mooring", OUTER)])
    assert areas.lookup(8.80, 54.60) == "frr-x-mooring"


def test_lookup_takes_coordinate_strings():
    areas = dialects.AreaIndex([("frr-x-mooring", OUTER)])
    assert areas.lookup("8.90", "54.62") == "frr-x-mooring"


def test_an_empty_index_knows_no_dialect():
    assert dialects.AreaIndex([]).lookup(8.84, 54.59) is None
