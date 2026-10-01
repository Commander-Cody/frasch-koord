"""nameindex.py: how a name is normalised, which variants of an OSM name
value count, and the index of candidate records by name that the matcher and
the curation export look names up in."""

from __future__ import annotations

import pytest

from frasch import nameindex
from conftest import cand


# ------------------------------------------------------------------- norm ---
@pytest.mark.parametrize(
    "a,b",
    [
        ("Holm", " holm "),  # case, surrounding blanks
        ("Groß-Morsum", "Gross Morsum"),  # ß, hyphen
        ("Süderlügum", "Suederluegum"),  # ü
        ("Ockholmer Koog", "Ockholmer  Koog"),  # inner blanks
        ("Højer", "Hoejer"),  # ø
        ("Åbenrå", "Aabenraa"),  # å
        ("Ærø", "Aeroe"),  # æ
        ("Langeneß", "Langeness"),
        ("Wyk auf Föhr", "Wyk-auf-Foehr"),
    ],
)
def test_norm_treats_spellings_as_equal(a: str, b: str) -> None:
    assert nameindex.norm(a) == nameindex.norm(b)


def test_norm_spelling() -> None:
    assert nameindex.norm("Sønder Løgum") == "soender loegum"
    assert nameindex.norm("Groß-Morsum") == "gross morsum"


def test_norm_does_not_split_compounds() -> None:
    # README: `Gotteskoogsee` does not match OSM's `Gotteskoog See`
    assert nameindex.norm("Gotteskoogsee") != nameindex.norm("Gotteskoog See")


def test_norm_of_nothing_is_empty() -> None:
    assert nameindex.norm("") == ""
    assert nameindex.norm(None) == ""


# ------------------------------------------------------ split_name_values ---
def test_plain_name_is_its_only_value() -> None:
    assert nameindex.split_name_values("Holm") == [("Holm", 0)]


def test_multilingual_slash_list_gives_each_language_unpenalised() -> None:
    vals = nameindex.split_name_values("North Sea / Nordsee / Noordzee")
    assert ("Nordsee", 0) in vals
    assert ("North Sea / Nordsee / Noordzee", 0) in vals


def test_semicolon_list_gives_each_value_unpenalised() -> None:
    vals = nameindex.split_name_values("Nord-Ost-Strand;Nordoststrand")
    assert ("Nord-Ost-Strand", 0) in vals and ("Nordoststrand", 0) in vals


@pytest.mark.parametrize(
    "value,bare",
    [
        ("Kampen (Sylt)", "Kampen"),  # OSM's disambiguator
        ("Kreis Dithmarschen", "Dithmarschen"),  # a type word in front
        ("Wyk auf Föhr", "Wyk"),  # the island behind
        ("Hallig Hooge", "Hooge"),
    ],
)
def test_osm_annotations_give_a_penalised_bare_name(value: str, bare: str) -> None:
    vals = nameindex.split_name_values(value)
    assert (value, 0) in vals
    assert (bare, 2) in vals


# ----------------------------------------------------------------- lookup ---
HOLM = cand("n", 240102263, 8.866668, 54.833305, name="Holm", place="village")
HOLME = cand("n", 2716731633, 9.065537, 54.982492, name="Holme", name__de="Holm", place="hamlet")
KAMPEN = cand("n", 240063898, 8.344065, 54.95377, name="Kampen (Sylt)", place="village")


def test_a_name_finds_its_records_with_the_rank_of_the_field_it_is_in() -> None:
    index = nameindex.NameIndex([HOLM, HOLME])
    assert sorted((rec["id"], rank) for rec, rank in index.lookup("holm")) == [
        (240102263, 0),
        (2716731633, 1),
    ]


def test_a_bare_name_behind_an_osm_annotation_is_found_with_a_penalty() -> None:
    assert [(rec["id"], rank) for rec, rank in nameindex.NameIndex([KAMPEN]).lookup("Kampen")] == [
        (240063898, 2)
    ]


def test_records_are_found_by_their_reference_too() -> None:
    assert nameindex.NameIndex([HOLM]).by_key[("n", 240102263)] is HOLM


def test_an_empty_name_finds_nothing() -> None:
    assert nameindex.NameIndex([HOLM]).lookup("") == []
