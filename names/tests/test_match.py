"""match.py: clustering, and the decision `match_row` makes for a row
(README "Matching rules (v1)").

`match_row` runs against a real `NameIndex` built from a tiny candidates.jsonl
in build_candidates.py's format.  The records are real OSM objects (ids,
positions and tags as in the Schleswig-Holstein / Denmark extracts of
September 2026), trimmed to the tags the matcher reads."""

from __future__ import annotations

from pathlib import Path

import pytest

from frasch import match
from frasch import placelist
from frasch.nameindex import NameIndex
from frasch.hints import HintResolver
from frasch.candidates import Candidate, read_records
from conftest import REGISTRY, cand, write_candidates


def make_index(tmp_path: Path, *recs: Candidate) -> NameIndex:
    return NameIndex(read_records(str(write_candidates(tmp_path / "candidates.jsonl", *recs))))


def row(**cells: str) -> placelist.PlaceRow:
    """A places.csv row as placelist.read returns it."""
    return placelist.PlaceRow({c: "" for c in placelist.columns(REGISTRY)} | cells, 2)


def run(tmp_path: Path, r: placelist.PlaceRow, *recs: Candidate) -> match.MatchResult:
    index = make_index(tmp_path, *recs)
    return match.match_row(r, index, HintResolver(index), REGISTRY)


# real objects -------------------------------------------------------------
HOLM_NF = cand(
    "n", 240102263, 8.866668, 54.833305, name="Holm", place="village", wikidata="Q559369"
)
HOLM_HAMBURG = cand(
    "n", 240086046, 9.672896, 53.620139, name="Holm", place="village", wikidata="Q691934"
)
HOLME_DK = cand(
    "n",
    2716731633,
    9.065537,
    54.982492,
    src="denmark",
    name="Holme",
    name__da="Holme",
    name__de="Holm",
    place="hamlet",
    wikidata="Q140690355",
)
HOLM_STREET = cand("w", 33228153, 8.554547, 54.696678, name="Holm", highway="residential")

MORSUM_SYLT = cand(
    "n", 310191124, 8.429612, 54.872876, name="Morsum", place="village", wikidata="Q20629"
)
NORDSTRAND_VILLAGE = cand("n", 85929111, 8.865286, 54.487378, name="Nordstrand", place="village")
NORDSTRAND_PENINSULA = cand(
    "n",
    6337086093,
    8.865555,
    54.487371,
    name="Nordstrand",
    natural="peninsula",
    wikidata="Q15058181",
)
SYLT = cand(
    "r",
    1576925,
    8.418235,
    54.888448,
    name="Sylt",
    name__de="Sylt",
    name__da="Sild",
    place="island",
    wikidata="Q3107",
)

KAMPEN_SYLT = cand("n", 240063898, 8.344065, 54.95377, name="Kampen (Sylt)", place="village")
KAMPEN_SYLT_MUNICIPALITY = cand(
    "r",
    1147133,
    8.356739,
    54.967875,
    name="Kampen (Sylt)",
    boundary="administrative",
    admin_level="8",
    wikidata="Q27332",
)
KAMPEN_STORMARN = cand("n", 6694657313, 9.937962, 53.857649, name="Kampen", place="hamlet")

OSTENFELD_RENDSBURG = cand(
    "n", 240062575, 9.780628, 54.316519, name="Ostenfeld", place="village", wikidata="Q667300"
)
OSTENFELD_HUSUM = cand(
    "n",
    240104163,
    9.232751,
    54.46359,
    name="Ostenfeld (Husum)",
    name__da="Østerfjolde",
    place="village",
)
RENDSBURG = cand("n", 43366937, 9.665008, 54.300292, name="Rendsburg", place="town")

DRAGE_STEINBURG = cand("n", 240054933, 9.51933, 54.004272, name="Drage", place="village")
DRAGE_STEINBURG_MUNICIPALITY = cand(
    "r",
    450076,
    9.533033,
    54.016063,
    name="Drage",
    boundary="administrative",
    admin_level="8",
    wikidata="Q634156",
)
DRAGE_ELBE_MUNICIPALITY = cand(
    "r",
    308488,
    10.327176,
    53.42993,
    name="Drage",
    boundary="administrative",
    admin_level="8",
    wikidata="Q665062",
)

# the village node carries wikidata=Q551483 -- left out to test the fallback
SCHAFFLUND_NO_QID = cand("n", 240090603, 9.183447, 54.759282, name="Schafflund", place="village")
SCHAFFLUND_MUNICIPALITY = cand(
    "r",
    1156027,
    9.137018,
    54.771625,
    name="Schafflund",
    boundary="administrative",
    admin_level="8",
    wikidata="Q551483",
)
AMT_SCHAFFLUND = cand(
    "r",
    1156150,
    9.154304,
    54.763147,
    name="Schafflund",
    name__prefix="Amt",
    boundary="administrative",
    admin_level="7",
    wikidata="Q479884",
)

KIRCHWARFT_HOOGE = cand("n", 11711096159, 8.544362, 54.572982, name="Kirchwarft", place="hamlet")
KIRCHWARFT_OCKHOLM = cand("n", 1333738478, 8.826992, 54.664965, name="Kirchwarft", place="hamlet")
HOOGE = cand(
    "w",
    1472528450,
    8.538734,
    54.572607,
    name="Hooge",
    place="island",
    natural="coastline",
    wikidata="Q17047971",
)
OCKHOLM = cand(
    "n",
    240080339,
    8.827915,
    54.665533,
    name="Ockholm",
    name__de="Ockholm",
    name__da="Okholm",
    place="village",
)


# ---------------------------------------------------------------- cluster ---
def test_two_village_nodes_two_km_apart_are_two_villages() -> None:
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("n", 2, 8.80, 54.818, name="Holm", place="hamlet")  # 2.0 km north
    assert len(match.cluster([a, b])) == 2


def test_village_node_and_nearby_dwelling_way_are_one_feature() -> None:
    # only two *settlement nodes* are kept apart; a way within 3 km merges
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("w", 2, 8.80, 54.818, name="Holm", landuse="residential")
    assert len(match.cluster([a, b])) == 1


def test_point_features_further_apart_than_three_km_stay_apart() -> None:
    a = cand("w", 1, 8.80, 54.80, name="Holm", landuse="residential")
    b = cand("w", 2, 8.80, 54.836, name="Holm", landuse="residential")  # 4.0 km
    assert len(match.cluster([a, b])) == 2


def test_pieces_of_a_river_twenty_km_apart_are_one_river() -> None:
    a = cand("w", 1, 9.00, 54.60, name="Arlau", waterway="river")
    b = cand("w", 2, 9.00, 54.78, name="Arlau", waterway="river")  # 20 km
    assert len(match.cluster([a, b])) == 1


def test_cluster_position_is_the_mean_of_its_members() -> None:
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("w", 2, 8.82, 54.81, name="Holm", landuse="residential")
    (cl,) = match.cluster([a, b])
    assert cl["lon"] == pytest.approx(8.81)
    assert cl["lat"] == pytest.approx(54.805)


def test_a_record_without_location_is_a_cluster_of_its_own() -> None:
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("r", 2, None, None, name="Holm", boundary="administrative", admin_level="8")
    clusters = match.cluster([a, b])
    assert len(clusters) == 2
    assert clusters[1]["lon"] is None


# -------------------------------------------------------------- match_row ---
def test_one_candidate_is_matched(tmp_path: Path) -> None:
    out = run(tmp_path, row(kind="settlement", solring="Muasem", de="Morsum"), MORSUM_SYLT)
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"], out["wikidata"]) == ("node", "310191124", "Q20629")


def test_a_hit_on_name_outranks_a_hit_on_name_de(tmp_path: Path) -> None:
    """Holm/Holme: the Danish hamlet Holme carries name:de=Holm and lies
    inside the North Frisia box, 21 km from the North Frisian village Holm.
    Clustered as equals they would be two villages and the row ambiguous; the
    hit on the OSM `name` wins instead."""
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"), HOLME_DK, HOLM_NF)
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"], out["wikidata"]) == ("node", "240102263", "Q559369")


def test_only_candidate_in_north_frisia_wins_when_the_rivals_are_far(tmp_path: Path) -> None:
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"), HOLM_HAMBURG, HOLM_NF)
    assert out["status"] == "matched"
    assert out["osm_id"] == "240102263"
    assert out["note"] == "auto: only candidate in North Frisia"


def test_a_street_of_the_same_name_is_no_candidate(tmp_path: Path) -> None:
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"), HOLM_STREET, HOLM_NF)
    assert out["status"] == "matched"
    assert out["osm_id"] == "240102263"


def test_only_streets_of_that_name_is_not_found(tmp_path: Path) -> None:
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"), HOLM_STREET)
    assert out["status"] == "not_found"
    assert out["osm_id"] == ""


def test_a_name_nothing_in_osm_carries_is_not_found_with_the_matchers_note(
    tmp_path: Path,
) -> None:
    owners = row(kind="settlement", mooring="Hulm", de="Holm", note="ask the Heimatverein")
    out = run(tmp_path, owners, MORSUM_SYLT)
    assert (out["status"], out["note"]) == ("not_found", "no name match in OSM")


def test_two_equal_villages_in_north_frisia_are_ambiguous(tmp_path: Path) -> None:
    out = run(
        tmp_path,
        row(kind="warft", mooring="Schörkewärw", de="Kirchwarft"),
        KIRCHWARFT_HOOGE,
        KIRCHWARFT_OCKHOLM,
    )
    assert out["status"] == "ambiguous"
    assert out["osm_id"] == ""
    assert "n/11711096159:Kirchwarft:hamlet:" in out["candidates"]
    assert "n/1333738478:Kirchwarft:hamlet:" in out["candidates"]


@pytest.mark.parametrize("hint,winner", [("Hooge", "11711096159"), ("Ockholm", "1333738478")])
def test_the_hint_picks_one_of_several_places_with_that_name(
    tmp_path: Path, hint: str, winner: str
) -> None:
    out = run(
        tmp_path,
        row(kind="warft", mooring="Schörkewärw", de="Kirchwarft", hint=hint),
        KIRCHWARFT_HOOGE,
        KIRCHWARFT_OCKHOLM,
        HOOGE,
        OCKHOLM,
    )
    assert out["status"] == "matched"
    assert out["osm_id"] == winner
    assert out["note"] == "auto: location hint"


def test_a_hint_is_binding_even_for_the_only_candidate(tmp_path: Path) -> None:
    """Morsum/Nordstrand: the list means a Morsum on Nordstrand; OSM's only
    Morsum is on Sylt, 50 km away.  The row goes to review instead of
    getting the Sylt village."""
    out = run(
        tmp_path,
        row(kind="settlement", mooring="Mursem", de="Morsum", hint="Nordstrand"),
        MORSUM_SYLT,
        NORDSTRAND_VILLAGE,
        NORDSTRAND_PENINSULA,
    )
    assert out["status"] == "ambiguous"
    assert out["osm_id"] == ""
    assert out["note"] == "location hint 'Nordstrand' matched no cluster"
    assert out["candidates"].startswith("n/310191124:Morsum:village:")


def test_a_hint_that_fits_confirms_the_only_candidate(tmp_path: Path) -> None:
    out = run(
        tmp_path,
        row(kind="settlement", solring="Muasem", de="Morsum", hint="Sylt"),
        MORSUM_SYLT,
        SYLT,
    )
    assert out["status"] == "matched"
    assert out["osm_id"] == "310191124"


def test_a_hint_that_names_an_archipelago_reaches_as_far_as_one_that_names_an_island(
    tmp_path: Path,
) -> None:
    halligen = cand("r", 1, 8.60, 54.60, name="Halligen", natural="archipelago")
    nine_km_north = cand("n", 2, 8.60, 54.681, name="Holm", place="village")
    out = run(
        tmp_path,
        row(kind="settlement", mooring="Hulm", de="Holm", hint="Halligen"),
        nine_km_north,
        halligen,
    )
    assert out["note"] == "auto: location hint"


def test_a_hint_means_the_island_of_that_name_rather_than_a_nearer_namesake(
    tmp_path: Path,
) -> None:
    islet = cand("w", 1, 8.00, 54.70, name="Oland", natural="islet")  # 58 km from the centre
    namesake = cand("r", 2, 9.30, 54.70, name="Oland", boundary="administrative")  # 26 km
    on_the_islet = cand("n", 3, 8.01, 54.70, name="Holm", place="village")
    out = run(
        tmp_path,
        row(kind="settlement", mooring="Hulm", de="Holm", hint="Oland"),
        on_the_islet,
        islet,
        namesake,
    )
    assert out["note"] == "auto: location hint"


def test_a_hint_nobody_knows_matches_nothing_and_binds_nothing(tmp_path: Path) -> None:
    # an unresolvable hint is no hint: the single candidate still wins
    out = run(
        tmp_path,
        row(kind="settlement", solring="Muasem", de="Morsum", hint="bei Keitum"),
        MORSUM_SYLT,
    )
    assert out["status"] == "matched"
    assert out["osm_id"] == "310191124"


def test_a_weaker_osm_annotation_hit_beats_a_far_away_hamlet(tmp_path: Path) -> None:
    """Kampen (Sylt): OSM calls the Sylt village `Kampen (Sylt)`, so for
    *Kampen* it is only a penalised hit, while the exact hit is a hamlet near
    Hamburg.  That far-away hamlet is implausible for the list, and the weaker
    hit in North Frisia is taken instead."""
    out = run(
        tmp_path, row(kind="settlement", solring="Kaamp", de="Kampen"), KAMPEN_STORMARN, KAMPEN_SYLT
    )
    assert out["status"] == "matched"
    assert out["osm_id"] == "240063898"
    assert out["match_name"] == "Kampen (Sylt)"
    assert out["note"] == "auto: only candidate in North Frisia (weaker name hit)"


def test_a_far_away_village_with_a_weaker_hit_in_north_frisia_is_ambiguous(tmp_path: Path) -> None:
    """Ostenfeld: the exact hit is the village near Rendsburg, outside North
    Frisia; OSM calls the one near Husum `Ostenfeld (Husum)`, only a weaker
    hit.  A far-away village is no implausible winner the way a hamlet is, so
    neither is taken -- the row goes to review with both."""
    out = run(
        tmp_path,
        row(kind="settlement", mooring="Ååstenfälj", de="Ostenfeld"),
        OSTENFELD_RENDSBURG,
        OSTENFELD_HUSUM,
    )
    assert out["status"] == "ambiguous"
    assert (out["osm_id"], out["wikidata"]) == ("", "")
    assert "n/240062575:Ostenfeld:village:" in out["candidates"]
    assert "n/240104163:Ostenfeld (Husum):village:" in out["candidates"]
    assert out["note"] == (
        "best name hit is 71 km from North Frisia, a weaker one lies inside -- verify by hand"
    )


def test_a_hint_confirms_a_far_away_village_over_a_weaker_hit_in_north_frisia(
    tmp_path: Path,
) -> None:
    # the hint is binding: it says the list means the Ostenfeld near Rendsburg
    out = run(
        tmp_path,
        row(kind="settlement", mooring="Ååstenfälj", de="Ostenfeld", hint="Rendsburg"),
        OSTENFELD_RENDSBURG,
        OSTENFELD_HUSUM,
        RENDSBURG,
    )
    assert out["status"] == "matched"
    assert out["osm_id"] == "240062575"
    assert out["note"] == "auto: location hint"


def test_a_candidate_two_names_find_keeps_its_best_hit(tmp_path: Path) -> None:
    """`Holme; Holm`: the Danish hamlet Holme is a `name` hit for the first
    name and only a `name:de` hit for the second -- it keeps the `name` hit
    and is the village Holm's equal: two clusters inside North Frisia."""
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holme; Holm"), HOLME_DK, HOLM_NF)
    assert out["status"] == "ambiguous"
    assert out["note"] == "2 plausible candidates"


def test_a_far_away_hamlet_stays_for_review_when_the_weaker_hits_are_far_too(
    tmp_path: Path,
) -> None:
    # made up: a second Kampen hamlet, further still from North Frisia, as a weaker hit
    kampen_lippe = cand("n", 1, 8.9, 51.9, name="Kampen (Lippe)", place="hamlet")
    out = run(
        tmp_path,
        row(kind="settlement", solring="Kaamp", de="Kampen"),
        KAMPEN_STORMARN,
        kampen_lippe,
    )
    assert out["status"] == "ambiguous"
    assert out["note"] == "only match is 115 km from North Frisia (settlement) -- verify by hand"
    assert out["candidates"].startswith("n/6694657313:Kampen:hamlet:")
    assert "n/1:Kampen (Lippe):hamlet:" in out["candidates"]


def test_a_far_away_hamlet_alone_is_left_for_review(tmp_path: Path) -> None:
    out = run(tmp_path, row(kind="settlement", solring="Kaamp", de="Kampen"), KAMPEN_STORMARN)
    assert out["status"] == "ambiguous"
    assert out["osm_id"] == ""
    assert "verify by hand" in out["note"]


def test_a_warft_outside_north_frisia_is_left_for_review(tmp_path: Path) -> None:
    # a Warft exists only in North Frisia, however clear the name hit
    far = cand("n", 1, 10.5, 54.3, name="Kirchwarft", place="hamlet")
    out = run(tmp_path, row(kind="warft", mooring="Schörkewärw", de="Kirchwarft"), far)
    assert out["status"] == "ambiguous"
    assert "verify by hand" in out["note"]


def test_a_match_the_scan_could_not_place_is_left_for_review_as_such(tmp_path: Path) -> None:
    unplaced = cand("r", 1, None, None, name="Neuer Koog", place="polder")
    out = run(tmp_path, row(kind="koog", mooring="Naie Kuuch", de="Neuer Koog"), unplaced)
    assert out["note"] == "only match has no known position (koog) -- verify by hand"


def test_danish_name_is_used_when_there_is_no_german_one(tmp_path: Path) -> None:
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", da="Holme"), HOLME_DK)
    assert out["status"] == "matched"
    assert out["osm_id"] == "2716731633"


def test_row_without_frisian_name_is_not_matched(tmp_path: Path) -> None:
    out = run(tmp_path, row(kind="settlement", de="Morsum"), MORSUM_SYLT)
    assert out["status"] == "not_found"
    assert out["osm_id"] == ""


def test_row_without_german_or_danish_name_is_not_matched(tmp_path: Path) -> None:
    out = run(tmp_path, row(kind="settlement", solring="Muasem"), MORSUM_SYLT)
    assert out["status"] == "not_found"


def test_any_dialect_column_counts_as_a_frisian_name(tmp_path: Path) -> None:
    # README: which dialect it is does not matter for matching
    out = run(tmp_path, row(kind="hallig", hallig="de Huuge", de="Hooge"), HOOGE)
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"]) == ("way", "1472528450")


def test_the_place_node_wins_over_the_boundary_relation(tmp_path: Path) -> None:
    relation = cand(
        "r",
        1420394,
        8.857041,
        54.831964,
        name="Holm",
        boundary="administrative",
        admin_level="8",
        wikidata="Q559369",
    )
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"), relation, HOLM_NF)
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"]) == ("node", "240102263")


def test_the_boundary_relation_lends_its_wikidata_to_the_place_node(tmp_path: Path) -> None:
    """Kampen (Sylt): the village node has no `wikidata`, the municipality's
    boundary relation 1.8 km away has.  The node wins, with the relation's QID."""
    out = run(
        tmp_path,
        row(kind="settlement", solring="Kaamp", de="Kampen"),
        KAMPEN_SYLT_MUNICIPALITY,
        KAMPEN_SYLT,
    )
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"], out["wikidata"]) == ("node", "240063898", "Q27332")


def test_a_far_away_namesake_boundary_lends_no_wikidata(tmp_path: Path) -> None:
    """Drage: the Drage (Elbe) municipality lies 83 km from the Drage
    (Steinburg) village node -- another place, its QID is not the node's."""
    out = run(
        tmp_path,
        row(kind="settlement", mooring="Draage", de="Drage"),
        DRAGE_ELBE_MUNICIPALITY,
        DRAGE_STEINBURG,
    )
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"], out["wikidata"]) == ("node", "240054933", "")


def test_of_two_municipalities_nearby_the_nearer_lends_its_wikidata(tmp_path: Path) -> None:
    # made up: a second Gemeinde "Drage" 8 km from the village node
    neighbour = cand(
        "r",
        1,
        9.64,
        54.004272,
        name="Drage",
        boundary="administrative",
        admin_level="8",
        wikidata="Q1",
    )
    out = run(
        tmp_path,
        row(kind="settlement", mooring="Draage", de="Drage"),
        neighbour,
        DRAGE_STEINBURG_MUNICIPALITY,
        DRAGE_STEINBURG,
    )
    assert out["status"] == "matched"
    assert (out["osm_id"], out["wikidata"]) == ("240054933", "Q634156")


def test_the_municipality_lends_its_wikidata_rather_than_the_nearer_amt(tmp_path: Path) -> None:
    """Schafflund: the Amt relation (admin_level 7) lies 1.9 km from the
    village node, the Gemeinde relation (admin_level 8) 3.3 km.  The most
    local boundary is the village's."""
    out = run(
        tmp_path,
        row(kind="settlement", mooring="Schååflem", de="Schafflund"),
        AMT_SCHAFFLUND,
        SCHAFFLUND_MUNICIPALITY,
        SCHAFFLUND_NO_QID,
    )
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"], out["wikidata"]) == ("node", "240090603", "Q551483")


def test_all_pieces_of_a_river_are_matched(tmp_path: Path) -> None:
    pieces = [
        cand("w", i, 9.0, 54.6 + 0.01 * i, name="Arlau", waterway="river")
        for i in (44051133, 44051131, 44051132)
    ]
    out = run(tmp_path, row(kind="water", mooring="Arlou", de="Arlau"), *pieces)
    assert out["status"] == "matched"
    assert out["osm_type"] == "way"
    assert out["osm_id"] == "44051131;44051132;44051133"
