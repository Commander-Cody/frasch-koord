"""The dialect registry (names/dialects.csv, frasch.registry) for the rest of
the build: printed, as the tag list for the tiles, or as JSON for the
frontend.

CLI:  `names/dialects.py`          prints the registry
      `names/dialects.py --tags`   prints `frr-x-mooring,frr-x-wieding,...`
                                   (tiles/build.sh feeds it to Planetiler)
      `names/dialects.py --export web/src/generated/dialects.json`
                                   writes the registry the frontend compiles
                                   in (every column but `note`)
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from frasch import cli, files, paths, registry
from frasch.registry import EXPORT_FIELDS, Registry


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--registry", default=paths.DIALECTS)
    ap.add_argument(
        "--tags",
        action="store_true",
        help="print the language tags as a comma-separated list "
        "(tiles/build.sh feeds them to Planetiler)",
    )
    ap.add_argument("--columns", action="store_true", help="print the places.csv columns instead")
    ap.add_argument(
        "--export",
        metavar="PATH",
        help="write the registry as JSON for the frontend (web/src/generated/dialects.json)",
    )
    a = ap.parse_args(argv)
    reg = registry.read(a.registry)
    if a.export:
        export_json(reg, a.export)
    elif a.tags:
        print(",".join(reg.tags))
    elif a.columns:
        print(",".join(reg.columns))
    else:
        for d in reg:
            print(
                f"{d['tag']:<16} {d['column']:<10} {d['label']:<18} "
                f"{d['status']:<7} view={d['view']:<4} {d['note']}"
            )
    return 0


def export_json(reg: Registry, path: str) -> None:
    """Write the registry the frontend compiles in: every column but `note`."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    files.atomic_write(
        path,
        json.dumps(
            [{k: v for k, v in d.items() if k in EXPORT_FIELDS} for d in reg],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
    )
