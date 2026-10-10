"""namecell.py: the conventions of a name cell (README "Conventions that
apply to every name cell").

Malformed name cells (unbalanced brackets, `?`, `;` without a space) are
deliberately not pinned down here: `frasch check-inputs` owns them."""

from __future__ import annotations

from frasch import namecell


def test_parts_splits_variants_and_keeps_each_remark() -> None:
    assert namecell.parts("Rübel; Rübbel (wisinge)") == [("Rübel", ""), ("Rübbel", "wisinge")]


def test_semicolon_inside_a_remark_does_not_split() -> None:
    # the README's own example: two names, the remark lists two varieties
    assert namecell.parts("Huađer; Huuger (Sölring; Wisinge)") == [
        ("Huađer", ""),
        ("Huuger", "Sölring; Wisinge"),
    ]


def test_several_remarks_on_one_variant_are_joined() -> None:
    assert namecell.parts("Brouersweerw (Foortuftinge) (Nickelsen 1982)") == [
        ("Brouersweerw", "Foortuftinge; Nickelsen 1982")
    ]


def test_empty_and_missing_cells_have_no_parts() -> None:
    assert namecell.parts("") == []
    assert namecell.parts(None) == []


def test_variants_strip_the_remarks() -> None:
    assert namecell.variants("Huađer; Huuger (Sölring; Wisinge)") == ["Huađer", "Huuger"]


def test_variants_list_a_name_once() -> None:
    # the same spelling with and without a source remark is one name
    assert namecell.variants("Hulm; Hulm (Wisinge)") == ["Hulm"]


def test_primary_is_the_first_variant_without_its_remark() -> None:
    assert namecell.primary("Lätj-Jäns-Weerw (Foortuftinge); Latj-Jäns-Wärw") == "Lätj-Jäns-Weerw"


def test_primary_of_an_empty_cell_is_empty() -> None:
    assert namecell.primary("") == ""
    assert namecell.primary(None) == ""


def test_remark_is_that_of_the_primary_variant() -> None:
    assert namecell.remark("Brouersweerw (Foortuftinge)") == "Foortuftinge"


def test_remark_of_a_later_variant_is_not_the_cells_remark() -> None:
    assert namecell.remark("Huađer; Huuger (Sölring; Wisinge)") == ""
