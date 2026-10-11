"""What the matcher makes of a row: the result of `frasch.match`'s decision,
as the matches file (frasch.matchfile), the report (frasch.matchreport) and
the curation export (frasch.curate) read it."""

from __future__ import annotations

import enum
from dataclasses import dataclass

from frasch import geo, osmtags
from frasch.candidates import Candidate
from frasch.geo import LonLat
from frasch.refs import OsmRef


class Outcome(enum.Enum):
    """What a run made of a row the matcher owns; the value is how
    work/matches.jsonl and the curation worklist spell it."""

    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"  # several plausible objects
    NOT_FOUND = "not_found"  # no object, or only near misses
    LOOKUP_FAILED = "lookup_failed"  # no answer from Wikidata: the row is left as it is

    @property
    def for_review(self) -> bool:
        """Whether the outcome leaves the row for a human to decide."""
        return self in (Outcome.AMBIGUOUS, Outcome.NOT_FOUND)


class RankedCandidate(Candidate):
    """A candidate record with the best name-field rank (`NameIndex.lookup`)
    any of the row's names found it with."""

    rank: int


@dataclass(frozen=True)
class MatchResult:
    """The matcher's result for one row.

    result      what it made of the row
    why         its remark: how it came to the match, or why there is none.
                For the matches file and the report only -- it never goes
                into places.csv, whose `note` column belongs to the owner
    refs        the objects the name goes on (a matched row; none for a
                country, which is matched by its item alone)
    wikidata    the Wikidata item of a matched row, `""` for none
    match_name, match_tags
                the name and the decisive tags of the object that was chosen
    lonlat      where that object is, None when the scan could not place it
    candidates  the objects a reviewer should see, the best first: every
                plausible one of a row left for review, the near misses of a
                row without any, the rivals of a match
    """

    result: Outcome
    why: str = ""
    refs: tuple[OsmRef, ...] = ()
    wikidata: str = ""
    match_name: str = ""
    match_tags: str = ""
    lonlat: LonLat | None = None
    candidates: tuple[RankedCandidate, ...] = ()


def summary(c: Candidate) -> tuple[str, str, int | None]:
    """A candidate as a reviewer reads it in a list: its name
    (`osmtags.name_of`), what it is in one word (`osmtags.class_of`, `-`
    when no tag says) and its distance from the centre of North Frisia in
    km (None for an object without a position)."""
    km = geo.from_centre(c["lon"], c["lat"])
    return (
        osmtags.name_of(c["tags"]),
        osmtags.class_of(c["tags"]) or "-",
        None if km is None else round(km),
    )
