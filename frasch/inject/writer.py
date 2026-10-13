"""Where the injector writes: the copy of the extract -- or, on a dry run,
nowhere, so that the code that writes need not know which it is."""

from __future__ import annotations

from typing import Protocol

import osmium

from frasch import osmscan


class Writer(Protocol):
    """What the injector needs of an `osmium.SimpleWriter`."""

    def add(self, obj: object, /) -> None: ...
    def add_node(self, node: object, /) -> None: ...
    def add_way(self, way: object, /) -> None: ...
    def close(self) -> None: ...


class DryRun:
    """The writer of a dry run: everything is counted, nothing written."""

    def add(self, obj: object, /) -> None:
        pass

    def add_node(self, node: object, /) -> None:
        pass

    def add_way(self, way: object, /) -> None:
        pass

    def close(self) -> None:
        pass


def copy_of(extract: str, out: str | None) -> Writer:
    """The writer of the copy of `extract` at `out`; of a dry run for None."""
    if out is None:
        return DryRun()
    # copy the input header so the extract bounds survive (Planetiler uses
    # them; without bounds it renders low-zoom tiles for the whole world)
    return osmium.SimpleWriter(out, overwrite=True, header=osmscan.header(extract))
