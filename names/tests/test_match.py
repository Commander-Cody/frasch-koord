"""match.py: normalisation, name-value variants, kind rules, clustering, which
rows the matcher owns, and the decision `match_row` makes for a row
(README "Matching rules (v1)").

`match_row` runs against a real `Index` built from a tiny candidates.jsonl in
build_candidates.py's format.  The records are real OSM objects (ids,
positions and tags as in the Schleswig-Holstein / Denmark extracts of
September 2026), trimmed to the tags the matcher reads."""
from __future__ import annotations

import pytest

from frasch import match
from frasch import placelist
from conftest import cand, write_candidates


def make_index(tmp_path, *recs):
    return match.Index(str(write_candidates(tmp_path / "candidates.jsonl", *recs)))


def row(**cells):
    """A places.csv row as placelist.read returns it."""
    r = {c: "" for c in placelist.COLUMNS}
    r.update(cells, _line=2)
    return r


def run(tmp_path, r, *recs):
    index = make_index(tmp_path, *recs)
    return match.match_row(r, index, match.HintResolver(index))


# real objects -------------------------------------------------------------
HOLM_NF = cand("n", 240102263, 8.866668, 54.833305, name="Holm", place="village",
               wikidata="Q559369")
HOLM_HAMBURG = cand("n", 240086046, 9.672896, 53.620139, name="Holm", place="village",
                    wikidata="Q691934")
HOLME_DK = cand("n", 2716731633, 9.065537, 54.982492, src="denmark", name="Holme",
                name__da="Holme", name__de="Holm", place="hamlet",
                wikidata="Q140690355")
HOLM_STREET = cand("w", 33228153, 8.554547, 54.696678, name="Holm",
                   highway="residential")

MORSUM_SYLT = cand("n", 310191124, 8.429612, 54.872876, name="Morsum", place="village",
                   wikidata="Q20629")
NORDSTRAND_VILLAGE = cand("n", 85929111, 8.865286, 54.487378, name="Nordstrand",
                          place="village")
NORDSTRAND_PENINSULA = cand("n", 6337086093, 8.865555, 54.487371, name="Nordstrand",
                            natural="peninsula", wikidata="Q15058181")
SYLT = cand("r", 1576925, 8.418235, 54.888448, name="Sylt", name__de="Sylt",
            name__da="Sild", place="island", wikidata="Q3107")

KAMPEN_SYLT = cand("n", 240063898, 8.344065, 54.95377, name="Kampen (Sylt)",
                   place="village")
KAMPEN_STORMARN = cand("n", 6694657313, 9.937962, 53.857649, name="Kampen",
                       place="hamlet")

KIRCHWARFT_HOOGE = cand("n", 11711096159, 8.544362, 54.572982, name="Kirchwarft",
                        place="hamlet")
KIRCHWARFT_OCKHOLM = cand("n", 1333738478, 8.826992, 54.664965, name="Kirchwarft",
                          place="hamlet")
HOOGE = cand("w", 1472528450, 8.538734, 54.572607, name="Hooge", place="island",
             natural="coastline", wikidata="Q17047971")
OCKHOLM = cand("n", 240080339, 8.827915, 54.665533, name="Ockholm", name__de="Ockholm",
               name__da="Okholm", place="village")


# ------------------------------------------------------------------- norm ---
@pytest.mark.parametrize("a,b", [
    ("Holm", " holm "),                             # case, surrounding blanks
    ("Groß-Morsum", "Gross Morsum"),                # ß, hyphen
    ("Süderlügum", "Suederluegum"),                 # ü
    ("Ockholmer Koog", "Ockholmer  Koog"),          # inner blanks
    ("Højer", "Hoejer"),                            # ø
    ("Åbenrå", "Aabenraa"),                         # å
    ("Ærø", "Aeroe"),                               # æ
    ("Langeneß", "Langeness"),
    ("Wyk auf Föhr", "Wyk-auf-Foehr"),
])
def test_norm_treats_spellings_as_equal(a, b):
    assert match.norm(a) == match.norm(b)


def test_norm_spelling():
    assert match.norm("Sønder Løgum") == "soender loegum"
    assert match.norm("Groß-Morsum") == "gross morsum"


def test_norm_does_not_split_compounds():
    # README: `Gotteskoogsee` does not match OSM's `Gotteskoog See`
    assert match.norm("Gotteskoogsee") != match.norm("Gotteskoog See")


def test_norm_of_nothing_is_empty():
    assert match.norm("") == ""
    assert match.norm(None) == ""


# ------------------------------------------------------ split_name_values ---
def test_plain_name_is_its_only_value():
    assert match.split_name_values("Holm") == [("Holm", 0)]


def test_multilingual_slash_list_gives_each_language_unpenalised():
    vals = match.split_name_values("North Sea / Nordsee / Noordzee")
    assert ("Nordsee", 0) in vals
    assert ("North Sea / Nordsee / Noordzee", 0) in vals


def test_semicolon_list_gives_each_value_unpenalised():
    vals = match.split_name_values("Nord-Ost-Strand;Nordoststrand")
    assert ("Nord-Ost-Strand", 0) in vals and ("Nordoststrand", 0) in vals


@pytest.mark.parametrize("value,bare", [
    ("Kampen (Sylt)", "Kampen"),                    # OSM's disambiguator
    ("Kreis Dithmarschen", "Dithmarschen"),         # a type word in front
    ("Wyk auf Föhr", "Wyk"),                        # the island behind
    ("Hallig Hooge", "Hooge"),
])
def test_osm_annotations_give_a_penalised_bare_name(value, bare):
    vals = match.split_name_values(value)
    assert (value, 0) in vals
    assert (bare, 2) in vals


# ---------------------------------------------------------------- kind_ok ---
@pytest.mark.parametrize("kind,tags,ok", [
    ("settlement", {"place": "village"}, True),
    ("settlement", {"highway": "residential"}, False),   # the street "Holm"
    ("settlement", {"boundary": "administrative", "admin_level": "8"}, True),
    ("settlement", {"boundary": "administrative", "admin_level": "4"}, False),  # a Land
    ("hallig", {"place": "isolated_dwelling"}, True),    # some Halligen are one dwelling
    ("island", {"place": "isolated_dwelling"}, False),
    ("island", {"natural": "peninsula"}, True),          # Nordstrand
    ("warft", {"landuse": "residential"}, True),
    ("warft", {"highway": "service"}, False),
    ("water", {"waterway": "river"}, True),
    ("road", {"highway": "unclassified"}, True),
    ("road", {"place": "village"}, False),
    ("country", {"boundary": "administrative", "admin_level": "2"}, True),
    ("country", {"boundary": "administrative", "admin_level": "4"}, False),
])
def test_kind_ok(kind, tags, ok):
    assert match.kind_ok(kind, tags, []) is ok


# ---------------------------------------------------------------- cluster ---
def test_two_village_nodes_two_km_apart_are_two_villages():
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("n", 2, 8.80, 54.818, name="Holm", place="hamlet")      # 2.0 km north
    assert len(match.cluster([a, b])) == 2


def test_village_node_and_nearby_dwelling_way_are_one_feature():
    # only two *settlement nodes* are kept apart; a way within 3 km merges
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("w", 2, 8.80, 54.818, name="Holm", landuse="residential")
    assert len(match.cluster([a, b])) == 1


def test_point_features_further_apart_than_three_km_stay_apart():
    a = cand("w", 1, 8.80, 54.80, name="Holm", landuse="residential")
    b = cand("w", 2, 8.80, 54.836, name="Holm", landuse="residential")  # 4.0 km
    assert len(match.cluster([a, b])) == 2


def test_pieces_of_a_river_twenty_km_apart_are_one_river():
    a = cand("w", 1, 9.00, 54.60, name="Arlau", waterway="river")
    b = cand("w", 2, 9.00, 54.78, name="Arlau", waterway="river")      # 20 km
    assert len(match.cluster([a, b])) == 1


def test_cluster_position_is_the_mean_of_its_members():
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("w", 2, 8.82, 54.81, name="Holm", landuse="residential")
    (cl,) = match.cluster([a, b])
    assert cl["lon"] == pytest.approx(8.81)
    assert cl["lat"] == pytest.approx(54.805)


def test_a_record_without_location_is_a_cluster_of_its_own():
    a = cand("n", 1, 8.80, 54.80, name="Holm", place="village")
    b = cand("r", 2, None, None, name="Holm", boundary="administrative", admin_level="8")
    clusters = match.cluster([a, b])
    assert len(clusters) == 2
    assert clusters[1]["lon"] is None


# ------------------------------------------------------- owned_by_matcher ---
@pytest.mark.parametrize("cells,owned", [
    ({}, True),                                                    # nothing yet
    ({"osm": "node/240063898", "status": "auto"}, True),           # filled by match.py
    ({"wikidata": "Q35", "status": "auto", "kind": "country"}, True),
    ({"osm": "relation/1420394"}, False),                          # filled by hand
    ({"wikidata": "Q35", "kind": "country"}, False),
    ({"osm": "node/1331229597", "status": "ok"}, False),
    ({"status": "skip"}, False),
    ({"kind": "not_a_place"}, False),
])
def test_owned_by_matcher(cells, owned):
    assert match.owned_by_matcher(row(**{"kind": "settlement", **cells})) is owned


def test_a_local_reference_is_never_the_matchers_even_as_auto():
    # the only way it matters: `local/` with status auto would otherwise count
    r = row(kind="settlement", osm="local/westerheide-amrum", status="auto")
    assert match.owned_by_matcher(r) is False


# -------------------------------------------------------------- match_row ---
def test_one_candidate_is_matched(tmp_path):
    out = run(tmp_path, row(kind="settlement", solring="Muasem", de="Morsum"),
              MORSUM_SYLT)
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"], out["wikidata"]) == ("node", "310191124", "Q20629")


def test_a_hit_on_name_outranks_a_hit_on_name_de(tmp_path):
    """Holm/Holme: the Danish hamlet Holme carries name:de=Holm and lies
    inside the North Frisia box, 21 km from the North Frisian village Holm.
    Clustered as equals they would be two villages and the row ambiguous; the
    hit on the OSM `name` wins instead."""
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"),
              HOLME_DK, HOLM_NF)
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"], out["wikidata"]) == ("node", "240102263", "Q559369")


def test_only_candidate_in_north_frisia_wins_when_the_rivals_are_far(tmp_path):
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"),
              HOLM_HAMBURG, HOLM_NF)
    assert out["status"] == "matched"
    assert out["osm_id"] == "240102263"
    assert out["note"] == "auto: only candidate in North Frisia"


def test_a_street_of_the_same_name_is_no_candidate(tmp_path):
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"),
              HOLM_STREET, HOLM_NF)
    assert out["status"] == "matched"
    assert out["osm_id"] == "240102263"


def test_only_streets_of_that_name_is_not_found(tmp_path):
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"), HOLM_STREET)
    assert out["status"] == "not_found"
    assert out["osm_id"] == ""


def test_two_equal_villages_in_north_frisia_are_ambiguous(tmp_path):
    out = run(tmp_path, row(kind="warft", mooring="Schörkewärw", de="Kirchwarft"),
              KIRCHWARFT_HOOGE, KIRCHWARFT_OCKHOLM)
    assert out["status"] == "ambiguous"
    assert out["osm_id"] == ""
    assert "n/11711096159:Kirchwarft:hamlet:" in out["candidates"]
    assert "n/1333738478:Kirchwarft:hamlet:" in out["candidates"]


@pytest.mark.parametrize("hint,winner", [("Hooge", "11711096159"),
                                         ("Ockholm", "1333738478")])
def test_the_hint_picks_one_of_several_places_with_that_name(tmp_path, hint, winner):
    out = run(tmp_path,
              row(kind="warft", mooring="Schörkewärw", de="Kirchwarft", hint=hint),
              KIRCHWARFT_HOOGE, KIRCHWARFT_OCKHOLM, HOOGE, OCKHOLM)
    assert out["status"] == "matched"
    assert out["osm_id"] == winner
    assert out["note"] == "auto: location hint"


def test_a_hint_is_binding_even_for_the_only_candidate(tmp_path):
    """Morsum/Nordstrand: the list means a Morsum on Nordstrand; OSM's only
    Morsum is on Sylt, 50 km away.  The row goes to review instead of
    getting the Sylt village."""
    out = run(tmp_path, row(kind="settlement", mooring="Mursem", de="Morsum",
                            hint="Nordstrand"),
              MORSUM_SYLT, NORDSTRAND_VILLAGE, NORDSTRAND_PENINSULA)
    assert out["status"] == "ambiguous"
    assert out["osm_id"] == ""
    assert out["note"] == "location hint 'Nordstrand' matched no cluster"
    assert out["candidates"].startswith("n/310191124:Morsum:village:")


def test_a_hint_that_fits_confirms_the_only_candidate(tmp_path):
    out = run(tmp_path, row(kind="settlement", solring="Muasem", de="Morsum", hint="Sylt"),
              MORSUM_SYLT, SYLT)
    assert out["status"] == "matched"
    assert out["osm_id"] == "310191124"


def test_a_hint_nobody_knows_matches_nothing_and_binds_nothing(tmp_path):
    # an unresolvable hint is no hint: the single candidate still wins
    out = run(tmp_path, row(kind="settlement", solring="Muasem", de="Morsum",
                            hint="bei Keitum"),
              MORSUM_SYLT)
    assert out["status"] == "matched"
    assert out["osm_id"] == "310191124"


def test_a_weaker_osm_annotation_hit_beats_a_far_away_hamlet(tmp_path):
    """Kampen (Sylt): OSM calls the Sylt village `Kampen (Sylt)`, so for
    *Kampen* it is only a penalised hit, while the exact hit is a hamlet near
    Hamburg.  That far-away hamlet is implausible for the list, and the weaker
    hit in North Frisia is taken instead."""
    out = run(tmp_path, row(kind="settlement", solring="Kaamp", de="Kampen"),
              KAMPEN_STORMARN, KAMPEN_SYLT)
    assert out["status"] == "matched"
    assert out["osm_id"] == "240063898"
    assert out["match_name"] == "Kampen (Sylt)"
    assert out["note"] == "auto: only candidate in North Frisia (weaker name hit)"


def test_a_far_away_hamlet_alone_is_left_for_review(tmp_path):
    out = run(tmp_path, row(kind="settlement", solring="Kaamp", de="Kampen"),
              KAMPEN_STORMARN)
    assert out["status"] == "ambiguous"
    assert out["osm_id"] == ""
    assert "verify by hand" in out["note"]


def test_a_warft_outside_north_frisia_is_left_for_review(tmp_path):
    # a Warft exists only in North Frisia, however clear the name hit
    far = cand("n", 1, 10.5, 54.3, name="Kirchwarft", place="hamlet")
    out = run(tmp_path, row(kind="warft", mooring="Schörkewärw", de="Kirchwarft"), far)
    assert out["status"] == "ambiguous"
    assert "verify by hand" in out["note"]


def test_danish_name_is_used_when_there_is_no_german_one(tmp_path):
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", da="Holme"), HOLME_DK)
    assert out["status"] == "matched"
    assert out["osm_id"] == "2716731633"


def test_row_without_frisian_name_is_not_matched(tmp_path):
    out = run(tmp_path, row(kind="settlement", de="Morsum"), MORSUM_SYLT)
    assert out["status"] == "not_found"
    assert out["osm_id"] == ""


def test_row_without_german_or_danish_name_is_not_matched(tmp_path):
    out = run(tmp_path, row(kind="settlement", solring="Muasem"), MORSUM_SYLT)
    assert out["status"] == "not_found"


def test_any_dialect_column_counts_as_a_frisian_name(tmp_path):
    # README: which dialect it is does not matter for matching
    out = run(tmp_path, row(kind="hallig", hallig="de Huuge", de="Hooge"), HOOGE)
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"]) == ("way", "1472528450")


def test_the_place_node_wins_over_the_boundary_relation(tmp_path):
    relation = cand("r", 1420394, 8.857041, 54.831964, name="Holm",
                    boundary="administrative", admin_level="8", wikidata="Q559369")
    out = run(tmp_path, row(kind="settlement", mooring="Hulm", de="Holm"),
              relation, HOLM_NF)
    assert out["status"] == "matched"
    assert (out["osm_type"], out["osm_id"]) == ("node", "240102263")


def test_all_pieces_of_a_river_are_matched(tmp_path):
    pieces = [cand("w", i, 9.0, 54.6 + 0.01 * i, name="Arlau", waterway="river")
              for i in (44051133, 44051131, 44051132)]
    out = run(tmp_path, row(kind="water", mooring="Arlou", de="Arlau"), *pieces)
    assert out["status"] == "matched"
    assert out["osm_type"] == "way"
    assert out["osm_id"] == "44051131;44051132;44051133"
