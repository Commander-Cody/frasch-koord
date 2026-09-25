"""The 2026-09-17 restore script must not be re-run (#21, H5)."""
from __future__ import annotations

import argparse
import csv

import pytest

import placelist
import restore_deleted_names


def test_refuses_to_run():
    with pytest.raises(SystemExit, match="history"):
        restore_deleted_names.main([])
    with pytest.raises(SystemExit, match="history"):
        restore_deleted_names.main(["--dry-run"])


def test_skips_a_line_that_now_holds_another_row(tmp_path, capsys):
    rows, _ = placelist.read()
    target = rows[0]                    # line 2 of the real places.csv
    wrong_de = "Nirgendwo"
    assert wrong_de not in placelist.variants(target["de"])
    proposal = tmp_path / "proposal.csv"
    with open(proposal, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["sheet_row", "section", "de", "name", "remark", "source_column",
                    "status", "suggested_column", "confidence", "area", "reason",
                    "current_row_line"])
        w.writerow(["1", "x", wrong_de, "Nüjnoom", "", "", "", "mooring", "high",
                    "", "", str(target["_line"])])
    restore_deleted_names.apply(argparse.Namespace(
        proposal=str(proposal), review=str(tmp_path / "none.csv"),
        min_confidence="low", only_agreed=False, dry_run=True))
    out = capsys.readouterr().out
    assert "added 0 name(s)" in out
    assert "changed since the proposal" in out
