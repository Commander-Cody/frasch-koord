"""The grammar of a name cell of the name list (names/README.md,
"Conventions that apply to every name cell"):

* a cell may hold several variants separated by `;` -- the first one is the
  primary name (the map label).  A `;` inside a remark does not separate
  variants (`Huađer; Huuger (Sölring; Wisinge)` is two names)
* `(...)` after a variant is a remark about it (local variety, source), never
  part of the name

This reads a cell as it is; what is wrong with a damaged one is
frasch.check_inputs' to say.
"""

from __future__ import annotations

import re

_REMARK = re.compile(r"\(([^()]*)\)")


def split_variants(cell: str | None) -> list[str]:
    """Split a name cell on `;` -- but not inside brackets, because a remark
    may itself list several dialects: `Huađer; Huuger (Sölring; Wisinge)` is
    two variants, not three."""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in cell or "":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def parts(cell: str | None) -> list[tuple[str, str]]:
    """`"Rübel; Rübbel (wisinge)"` -> `[("Rübel", ""), ("Rübbel", "wisinge")]`.

    The remark comes back without its brackets; several brackets on one
    variant are joined with `; `.  Variants without a name are dropped."""
    out: list[tuple[str, str]] = []
    for part in split_variants(cell):
        remarks = [m.group(1).strip() for m in _REMARK.finditer(part)]
        name = _REMARK.sub("", part).strip().rstrip("?").strip()
        if name:
            out.append((name, "; ".join(r for r in remarks if r)))
    return out


def variants(cell: str | None) -> list[str]:
    """`"Rübel; Rübbel (wisinge)"` -> `["Rübel", "Rübbel"]` (remarks stripped)."""
    out: list[str] = []
    for name, _ in parts(cell):
        if name not in out:
            out.append(name)
    return out


def primary(cell: str | None) -> str:
    """The first variant of a cell without its remark: the map label."""
    v = variants(cell)
    return v[0] if v else ""


def remark(cell: str | None) -> str:
    """The remark of the PRIMARY variant of a cell (`""` when it has none)."""
    p = parts(cell)
    return p[0][1] if p else ""
