"""Shared fixtures for the name-pipeline tests: a throwaway copy of the name
list's world (places.csv, curation.csv, work/) in a temp directory, built from
the real column layout (names/dialects.csv)."""
from __future__ import annotations

import csv
import io
import json
import os
import sys

import pytest

NAMES = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if NAMES not in sys.path:
    sys.path.insert(0, NAMES)

import placelist  # noqa: E402


def places_text(rows) -> str:
    """A places.csv with the real header; `rows` are dicts of the cells that
    are not empty."""
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=placelist.COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in placelist.COLUMNS})
    return buf.getvalue()


# a row of the name list, as several tests need one
TOFTUM = {"kind": "settlement", "mooring": "Toftem", "de": "Toftum",
          "osm": "node/240044107", "status": "ok"}


def cand(t, id, lon, lat, src="schleswig-holstein", **tags):
    """One candidates.jsonl record (build_candidates.py's format).  Tag keys
    with a colon are passed with a double underscore (`name__de`)."""
    tags = {k.replace("__", ":"): v for k, v in tags.items()}
    cls = [f"{k}={tags[k]}" for k in ("place", "natural", "boundary", "highway",
                                      "man_made") if k in tags]
    if "wikidata" in tags:
        cls.append("wikidata")
    return {"src": src, "t": t, "id": id, "lon": lon, "lat": lat,
            "cls": cls, "tags": tags}


def write_candidates(path, *recs):
    """Write `recs` as a candidates.jsonl to `path` and return it."""
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
                    encoding="utf-8")
    return path


CURATION_HEADER = "osm,name,lat,lon,set_tags,minzoom,maxzoom,polygon_km2,note\n"


@pytest.fixture
def world(tmp_path):
    """`tmp_path` laid out like names/: places.csv, curation.csv, work/."""
    (tmp_path / "work").mkdir()
    (tmp_path / "curation.csv").write_text(CURATION_HEADER, encoding="utf-8")
    return tmp_path
