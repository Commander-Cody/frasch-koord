#!/usr/bin/env python3
"""ONE-TIME IMPORT of the owner's Google-Sheets export (September 2026).

This produced the first version of names/places.csv.  The sheet is NOT the
source of truth any more -- names/places.csv is, and it has been hand-edited
since.  Re-running this script therefore only makes sense for a fresh list;
it writes to --out (default: places-from-sheet.csv next to this file), never
to names/places.csv.

Input : bootstrap/sheet-export.csv  (File -> Download -> CSV of the sheet)
Output: a places.csv-shaped table with two extra leading columns, sheet_row
        and section, and with empty osm / wikidata / status columns

The raw sheet is a flat list split into sections by heading rows (only the first
cell filled).  Name cells carry annotations that are unpacked here:

Mooring / older-Mooring column
  Raevn?              -> note "uncertain"
  Naam (wisinge)      -> kept as a remark: "Naam (wisinge)"; a non-Mooring
                         dialect marker moves the name to the `other` column
  Naam (Noom?)        -> alternative name, uncertain
  faeaer(i)nge        -> primary with the optional letters, alt without
  (Latj) Tuner        -> primary "Latj Tuner", alt "Tuner"
  A, B  /  A / B      -> primary A, alternatives B...

German column
  Name (bei Leck)     -> hint=Leck
  Name (Langeness)    -> hint=Langeness
  Name (?)  (wo?)     -> uncertain / note
  Name (free text)    -> note
  A, B  /  A / B      -> primary A, alternatives B...

Run:  .venv/bin/python names/bootstrap/import_sheet.py
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IN = os.path.join(HERE, "sheet-export.csv")
DEFAULT_OUT = os.path.join(HERE, "places-from-sheet.csv")

sys.path.insert(0, os.path.dirname(HERE))
from placelist import COLUMNS  # noqa: E402

# ---------------------------------------------------------------- sections ---
# sheet_row (1-based incl. header) of each heading row -> (section label, kind)
SECTIONS = [
    (2,   "Steeden än doorpe (implicit)", "settlement"),
    (353, "Kuuge", "koog"),
    (444, "Hiirde", "harde"),
    (456, "Hålie, ailönje än sönje", "island"),     # refined per row below
    (502, "Wäärwe än latj krååm", "warft"),
    (782, "Loonschape / Härtuchdoomer ...", "landscape"),
    (794, "Wååder", "water"),
    (844, "Stroote än weege", "road"),
    (849, "Oudere betiikninge", "not_a_place"),
    (860, "Lönje", "country"),
    (876, "Hålilönj", "helgoland"),
]
HEADING_ROWS = {r for r, _, _ in SECTIONS if r != 2}

# dialect / variant markers that may appear in parentheses in a Frisian cell.
# (Also covers "Kaarhiirdinge"/"Gooshiirdinge"-style sub-area markers and the
# occasional source marker "Wikipedia".)
DIALECT_QUALIFIER_RE = re.compile(
    r"^(?:[\w åøæÅØÆ,?-]*?)"
    r"(wisinge|mooring|halunder|h[åa]lifra[sc]ch|halifreesk|s[öo]lring|salring|"
    r"[öo]{1,2}mr(?:ing|ang)|fering|f[äa]iring|hiirding|hiirder|tuftinge|"
    r"doogbling|houlmer freesk|houlmer freesch|wikipedia)"
    r"(?:[\w åøæÅØÆ,?-]*)$", re.I)
# dialects that are NOT Mooring -> name_source=other_dialect
NON_MOORING_RE = re.compile(
    r"halunder|h[åa]lifra[sc]ch|halifreesk|s[öo]lring|salring|[öo]{1,2}mr(?:ing|ang)|"
    r"fering|f[äa]iring", re.I)

# article-only strings that must not become alternative names
ARTICLES = {"e", "di", "de", "dåt", "det", "et", "at", "da", "deät", "dåt"}

# parenthetical German content that is a note, not a place hint
NOTE_WORDS = re.compile(
    r"^(bauernhof|kirchspiel|stadt|dorf|gemeinde|wo\?|\?|halligen und inseln)$", re.I
)
NOTE_PREFIX = re.compile(
    r"^(google|stra(ß|ss)e |nebenfluss|ehemals|ehemalige|früher|heute|teil |siehe )", re.I
)
# comma parts that are qualifiers rather than alternative names
COMMA_NOTE = re.compile(r"^(kirchspiel|stadt|dorf|gemeinde)$", re.I)


def split_parens(text: str):
    """Return (text_without_parens, [paren_contents])."""
    parts, out, depth, buf, cur = [], [], 0, "", ""
    for ch in text:
        if ch == "(":
            if depth == 0:
                out.append(cur)
                cur = ""
            else:
                buf += ch
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                parts.append(buf)
                buf = ""
            else:
                buf += ch
        else:
            if depth:
                buf += ch
            else:
                cur += ch
    out.append(cur)
    if depth:  # unbalanced
        return text, []
    return "".join(out), parts


def tidy(s: str) -> str:
    return re.sub(r"\s{2,}", " ", s).strip(" \t,;/")


def parse_frisian(cell: str):
    """-> dict(primary, alts[list], qualifier, uncertain, dialect_of)"""
    raw = cell.strip()
    res = {"primary": "", "alts": [], "qualifier": "", "uncertain": 0, "non_mooring": False}
    if not raw:
        return res
    text = raw
    quals, alts = [], []
    uncertain = 0

    # 1) optional letters / words glued to a word:  faeaer(i)nge, Treen(e), Klasblinge(r)
    def optional_letters(m):
        return m.group(1)
    while True:
        m = re.search(r"(?<=\w)\(([A-Za-zÀ-ÿåøæÅØÆ]{1,3})\)(?=\w|$|\s)", text)
        if not m:
            break
        without = text[: m.start()] + text[m.end():]
        text = text[: m.start()] + m.group(1) + text[m.end():]
        alts.append(tidy(without))

    # 2) remaining parentheses
    body, parens = split_parens(text)
    for p in parens:
        p = p.strip()
        low = p.lower().strip(" ?")
        if not p:
            continue
        if p in ("?", "??"):
            uncertain = 1
        elif DIALECT_QUALIFIER_RE.match(low):
            quals.append(p)
            if NON_MOORING_RE.search(low):
                res["non_mooring"] = True
        else:
            if p.endswith("?"):
                uncertain = 1
                p = p[:-1].strip()
            # a leading "(Latj) Tuner" style optional word
            if body.strip().startswith(("", " ")) and text.strip().startswith("("):
                alts.append(tidy(body))            # variant without the word
                body = p + " " + body              # primary with the word
            else:
                alts.append(tidy(p))
    text = tidy(body)

    # 3) trailing uncertainty marker
    if text.endswith("?"):
        uncertain = 1
        text = text[:-1].strip()
    if text.endswith("?"):
        uncertain = 1
        text = text[:-1].strip()

    # 4) comma / slash alternatives
    pieces = [tidy(x) for x in re.split(r"\s*[,/]\s*", text) if tidy(x)]
    primary = pieces[0] if pieces else ""
    alts = pieces[1:] + [a for a in alts if a]
    # clean alts: strip '?' and dedupe against primary
    cleaned = []
    for a in alts:
        a = a.strip()
        if a.endswith("?"):
            uncertain = 1
            a = a[:-1].strip()
        a = tidy(a)
        if a and a != primary and a not in cleaned and a.lower() not in ARTICLES:
            cleaned.append(a)
    res.update(primary=primary, alts=cleaned, qualifier="; ".join(quals), uncertain=uncertain)
    return res


def parse_german(cell: str):
    """-> dict(primary, alts, note, hint, uncertain)"""
    raw = cell.strip()
    res = {"primary": "", "alts": [], "note": "", "hint": "", "uncertain": 0}
    if not raw:
        return res
    body, parens = split_parens(raw)
    notes, hints, alts = [], [], []
    uncertain = 0
    body_tokens = {t.lower() for t in re.findall(r"\w+", body)}
    body_low = body.lower()
    for p in parens:
        p = p.strip()
        if not p:
            continue
        if p in ("?", "??"):
            uncertain = 1
            continue
        if p.lower() in ("wo?",):
            uncertain = 1
            notes.append(p)
            continue
        if NOTE_WORDS.match(p) or NOTE_PREFIX.match(p) or ":" in p:
            notes.append(p)
            continue
        m = re.match(r"^bei\s+(.+)$", p, re.I)
        if m:
            hints.append(m.group(1).strip())
            continue
        toks = re.findall(r"\w+", p)
        # parenthetical that repeats part of the name -> alternative spelling
        if toks and any(t.lower() in body_tokens or t.lower() in body_low for t in toks):
            alts.append(tidy(p))
            continue
        if len(toks) <= 3:
            hints.append(tidy(p))
        else:
            notes.append(tidy(p))
    text = tidy(body)
    pieces = [tidy(x) for x in re.split(r"\s*(?:,|\s/\s)\s*", text) if tidy(x)]
    keep = []
    for pc in pieces:
        if COMMA_NOTE.match(pc):
            notes.append(pc)
        else:
            keep.append(pc)
    primary = keep[0] if keep else ""
    alts = [a for a in keep[1:] + alts if a and a != primary]
    seen, out = set(), []
    for a in alts:
        if a not in seen:
            seen.add(a)
            out.append(a)
    res.update(primary=primary, alts=out, note="; ".join(notes),
               hint="; ".join(hints), uncertain=uncertain)
    return res


def parse_plain(cell: str):
    """Danish / Low German: primary + comma alternatives, parens -> note."""
    raw = cell.strip()
    if not raw:
        return "", [], ""
    body, parens = split_parens(raw)
    pieces = [tidy(x) for x in re.split(r"\s*[,/]\s*", body) if tidy(x)]
    return (pieces[0] if pieces else ""), pieces[1:], "; ".join(p.strip() for p in parens if p.strip())


# The Halligen whose German name does not contain "Hallig" -- the ten remaining
# ones plus the former Halligen that have since grown together with Langeneß.
# Matched on the whole German name (a name *part* of "A / B"), never as a
# substring, so that "Norderoogsand" stays a sand and not a Hallig.
HALLIG_NAMES = {
    "hooge", "langeness", "langeneß", "gröde", "groede", "oland",
    "nordstrandischmoor", "lütt moor", "luett moor", "süderoog", "suederoog",
    "norderoog", "habel", "südfall", "suedfall",
    "nordmarsch", "appelland", "buhtwehl",
}


def refine_kind(kind: str, frr: str, de: str) -> str:
    """Sub-classify the island/hallig/sand section into island / hallig / sand."""
    if kind != "island":
        return kind
    blob = f"{frr} {de}".lower()
    if "helgoland" in de.lower():          # Hålilönj / Deät Lun -- an island
        return "island"
    # named Halligen first: "Hooge" carries no marker in its name at all
    for part in re.split(r"\s*/\s*", de.lower()):
        if part.strip() in HALLIG_NAMES:
            return "hallig"
    if re.search(r"sand\b|sönj|söön|soun|flak|knip|rücken|reeg", blob):
        return "sand"
    if "hallig" in blob or "håli" in blob or "hali" in blob:
        return "hallig"
    return "island"


def join(primary_name, alts, remark=""):
    """-> (cell text, uncertain).  Variants joined with `; `, the remark (a
    local variety / dialect marker) appended once, stray `?` stripped."""
    uncertain = False
    parts = []
    for p in [primary_name] + list(alts):
        p = tidy(p)
        if remark:
            p = tidy(p.replace(f"({remark})", ""))
        while p.endswith("?"):
            uncertain = True
            p = p[:-1].strip()
        if p and p not in parts:
            parts.append(p)
    text = "; ".join(parts)
    if text and remark:
        text += f" ({remark})"
    return text, uncertain


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN)
    ap.add_argument("--out", dest="out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    with open(args.inp, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))

    sec_by_row = {}
    cur = SECTIONS[0]
    idx = 1
    for n in range(2, len(rows) + 1):
        while idx < len(SECTIONS) and SECTIONS[idx][0] == n:
            cur = SECTIONS[idx]
            idx += 1
        sec_by_row[n] = cur

    out_rows = []
    stats = {"empty": 0, "heading": 0, "kept": 0, "no_name": 0}
    for n in range(2, len(rows) + 1):
        raw = [c.strip() for c in (rows[n - 1] + [""] * 10)[:10]]
        if n in HEADING_ROWS:
            stats["heading"] += 1
            continue
        if not any(raw):
            stats["empty"] += 1
            continue
        mo_raw, old_raw, adj, oadj, de_raw, nds_raw, da_raw, sj, uul, kwal = raw
        _, section, kind = sec_by_row[n]

        mo = parse_frisian(mo_raw)
        old = parse_frisian(old_raw)
        ger = parse_german(de_raw)
        da_p, da_alts, da_note = parse_plain(da_raw)

        mooring, u1 = join(mo["primary"], mo["alts"], mo["qualifier"])
        older = other = ""
        u2 = False
        if old["primary"]:
            if old["non_mooring"]:
                # the "older name" is really a name in another dialect
                # (Sölring, Halunder, ...): keep it, but never as a Mooring label
                other, u2 = join(old["primary"], old["alts"], old["qualifier"])
            else:
                older, u2 = join(old["primary"], old["alts"], old["qualifier"])
        de, u3 = join(ger["primary"], ger["alts"])
        uncertain = (mo["uncertain"] or old["uncertain"] or ger["uncertain"]
                     or u1 or u2 or u3)

        notes = []
        if uncertain:
            notes.append("uncertain")
        if ger["note"]:
            notes.append(ger["note"])
        if da_note:
            notes.append("da: " + da_note)
        # The sheet's inhabitant adjectives (adj, oadj), Low German (nds_raw),
        # South Jutish (sj), old names (uul) and source (kwal) columns are
        # deliberately NOT imported: the map does not use them and the owner
        # wants places.csv small.  They stay in sheet-export.csv.

        kind_r = refine_kind(kind, f"{mooring} {older}", de_raw)

        out_rows.append({
            "sheet_row": n,                  # dropped by the caller; kept for the merge
            "section": section,
            "kind": kind_r,
            "mooring": mooring,
            "older": older,
            "other": other,
            "de": de,
            "hint": ger["hint"],
            "da": join(da_p, da_alts)[0],
            "osm": "", "wikidata": "", "status": "",
            "note": " | ".join(notes),
        })
        stats["kept"] += 1
        if not (mooring or older or other):
            stats["no_name"] += 1

    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["sheet_row", "section"] + COLUMNS,
                           lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)

    import collections
    per_kind = collections.Counter(r["kind"] for r in out_rows)
    print(f"read {len(rows)-1} sheet rows: {stats['heading']} headings, "
          f"{stats['empty']} empty, {stats['kept']} kept "
          f"({stats['no_name']} without any Frisian name)")
    print("kind :", dict(per_kind))
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
