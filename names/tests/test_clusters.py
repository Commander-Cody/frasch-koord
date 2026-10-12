"""clusters.py: which candidates describe one feature (README "Matching
rules (v1)")."""

from __future__ import annotations

import pytest

from frasch import clusters
from frasch.candidates import Candidate
from conftest import cand


def test_two_village_nodes_two_km_apart_are_two_villages() -> None:
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("n", 2, 8.80, 54.818, name="Holm", place="hamlet")  # 2.0 km north
    assert len(clusters.cluster([a, b])) == 2


def test_village_node_and_nearby_dwelling_way_are_one_feature() -> None:
    # only two *settlement nodes* are kept apart; a way within 3 km merges
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("w", 2, 8.80, 54.818, name="Holm", landuse="residential")
    assert len(clusters.cluster([a, b])) == 1


def test_point_features_further_apart_than_three_km_stay_apart() -> None:
    a = cand("w", 1, 8.80, 54.80, name="Holm", landuse="residential")
    b = cand("w", 2, 8.80, 54.836, name="Holm", landuse="residential")  # 4.0 km
    assert len(clusters.cluster([a, b])) == 2


def test_pieces_of_a_river_twenty_km_apart_are_one_river() -> None:
    a = cand("w", 1, 9.00, 54.60, name="Arlau", waterway="river")
    b = cand("w", 2, 9.00, 54.78, name="Arlau", waterway="river")  # 20 km
    assert len(clusters.cluster([a, b])) == 1


def test_cluster_position_is_the_mean_of_its_members() -> None:
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("w", 2, 8.82, 54.81, name="Holm", landuse="residential")
    (cl,) = clusters.cluster([a, b])
    assert cl["lon"] == pytest.approx(8.81)
    assert cl["lat"] == pytest.approx(54.805)


def test_a_record_without_location_is_a_cluster_of_its_own() -> None:
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("r", 2, None, None, name="Holm", boundary="administrative", admin_level="8")
    found = clusters.cluster([a, b])
    assert len(found) == 2
    assert found[1]["lon"] is None


RIVER_PIECE = cand("w", 1, 9.00, 54.60, name="Arlau", waterway="river")
RELATION_20_KM_ON = cand("r", 2, 9.00, 54.78, name="Arlau", type="waterway")


@pytest.mark.parametrize(
    "one,other", [(RIVER_PIECE, RELATION_20_KM_ON), (RELATION_20_KM_ON, RIVER_PIECE)]
)
def test_a_river_reaches_as_far_whichever_of_two_objects_is_asked_first(
    one: Candidate, other: Candidate
) -> None:
    assert clusters.same_feature(one, other)
