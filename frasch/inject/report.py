"""What a run of the injector has to say, as lines for the command to print:
what its inputs hold (`input_lines`), and what the scan tagged, added and
curated and what it did not find (`result_lines`).  An object is written as
a cell of the lists spells it: `node/1`, `way/2`, `relation/3`."""

from __future__ import annotations

import collections
import os
from dataclasses import dataclass

from frasch import placelist, placenames, refs
from frasch.inject.inputs import FRISIAN_KEY, Inputs, local_keys
from frasch.inject.stats import Stats
from frasch.paths import Workspace
from frasch.placenames import DIALECT_KEY, LOCAL_KEY, MAXZOOM_KEY, MINZOOM_KEY


@dataclass(frozen=True)
class Report:
    """What a run counted, and its log, a line each."""

    stats: Stats
    log: list[str]


# ------------------------------------------------------------- the inputs ----
def input_lines(inputs: Inputs, ws: Workspace) -> list[str]:
    """What the inputs hold, a line per file of the workspace and pre-pass."""
    areas, objects = inputs.areas, inputs.objects
    lines = [
        *_name_lines(inputs, ws),
        f"areas     : {ws.areas} -> {len(areas)} polygon(s): {areas.summary()}",
        *_curation_lines(inputs, ws),
        f"objects   : {ws.objects} -> {len(objects)} located object(s)",
    ]
    if inputs.members:
        lines.append(f"waterways : {len(inputs.members)} member ways of matched waterway relations")
    if inputs.osm_local:
        lines.append(
            f"{FRISIAN_KEY}  : {len(inputs.osm_local)} object(s) that no row holds by reference have "
            "one in OSM and get a local name in their area (name:frr, or name:nds in a Low Saxon one)"
        )
    return lines


def _name_lines(inputs: Inputs, ws: Workspace) -> list[str]:
    names, reg = inputs.names, inputs.reg
    local = len(local_keys(names.by_id))
    return [
        f"name list : {ws.names}",
        f"dialects  : {ws.dialects} -> {len(reg)} columns ({', '.join(reg.tags)})",
        f"usable    : {names.used} rows -> {len(names.by_id) - local} OSM ids + "
        f"{len(names.by_qid)} wikidata QIDs" + (f" + {local} local reference(s)" if local else ""),
    ]


def _curation_lines(inputs: Inputs, ws: Workspace) -> list[str]:
    """What the curation holds, and the positions no row of the name list uses."""
    curation, by_id = inputs.curation, inputs.names.by_id
    tunings = curation.objects.values()
    lines = [
        f"curation  : {ws.curation} -> {len(tunings)} OSM ids "
        f"({sum(1 for tuning in tunings if MINZOOM_KEY in tuning['tags'])} with {MINZOOM_KEY}, "
        f"{sum(1 for tuning in tunings if MAXZOOM_KEY in tuning['tags'])} with {MAXZOOM_KEY})"
    ]
    if curation.squares:
        lines.append(f"synthetic : {len(curation.squares)} polygon(s) to add around nodes")
    if curation.points:
        lines.append(
            f"local     : {len(curation.points)} local reference(s) positioned in {ws.curation}"
        )
    lines += [
        f"  ! {refs.format([key])} ({curation.points[key]['label'] or '?'}) is "
        f"positioned in {ws.curation} but no row of {ws.names} uses it -- nothing added"
        for key in sorted(key for key in curation.points if key not in by_id)
    ]
    return lines


# -------------------------------------------------------------- the result ----
def _node(node_id: int) -> str:
    """An added node, as the lists spell a reference to one."""
    return refs.format([("n", node_id)])


def result_lines(stats: Stats, inputs: Inputs, extract: str, seconds: float) -> list[str]:
    """What the scan of `extract` tagged, added and curated, and what it did
    not find; a section starts with an empty line."""
    in_file = os.path.basename(extract)
    return [
        *_tagged_lines(stats, inputs, seconds),
        *_dialect_lines(stats, inputs),
        *_added_point_lines(stats, inputs),
        *_not_found_lines(stats, inputs, in_file),
        *_skipped_carrier_lines(stats, inputs),
        *_curated_lines(stats, inputs, in_file),
        *_square_lines(stats, inputs, in_file),
    ]


def _tagged_lines(stats: Stats, inputs: Inputs, seconds: float) -> list[str]:
    by_qid, tagged = inputs.names.by_qid, stats.tagged
    by_wikidata = (
        f" (of these {stats.qid_carriers} matched by wikidata: "
        f"{len(stats.present_qids)} of {len(by_qid)} QIDs present)"
    )
    members = f"; {stats.member_ways} same-named member ways of waterway relations"
    return [
        "",
        f"scanned {stats.scanned:,} objects in {seconds:.0f}s",
        f"tagged  {sum(tagged.values())} objects: "
        f"{tagged['n']} nodes, {tagged['w']} ways, {tagged['r']} relations"
        + (by_wikidata if by_qid else "")
        + (members if inputs.members else ""),
    ]


def _dialect_lines(stats: Stats, inputs: Inputs) -> list[str]:
    """The names written per dialect and the objects per dialect area."""
    lines = ["names written per dialect:"]
    for dialect in inputs.reg:
        key = placenames.dialect_key(dialect["tag"])
        if n := stats.names[key]:
            lines.append(f"  {key:<20} {n:>5}  {dialect['label']}")
    claimed, unclaimed = stats.osm_local_claimed, stats.osm_local_unclaimed
    lines.append(
        f"  {LOCAL_KEY:<20} {stats.local:>5}  local form"
        + (f" ({claimed} of them OSM's {FRISIAN_KEY})" if claimed else "")
    )
    if unclaimed:
        lines.append(
            f"  {LOCAL_KEY:<20} {unclaimed:>5}  OSM's {FRISIAN_KEY} on objects no row claims"
        )
    lines.append("objects per dialect area:")
    lines += [f"  {DIALECT_KEY}={tag:<15} {n:>5}" for tag, n in stats.dialects.most_common()]
    if not stats.dialects:
        lines.append("  (none -- no tagged object lies in a dialect area)")
    return lines


def _added_point_lines(stats: Stats, inputs: Inputs) -> list[str]:
    if not stats.added_points:
        return []
    by_id, reg = inputs.names.by_id, inputs.reg
    return [
        "",
        f"added {len(stats.added_points)} node(s) for places that are not in OSM:",
        *(
            f"  {_node(point.node_id)}  {refs.format([point.key])} "
            f"{placelist.describe(by_id[point.key], reg)} at {point.lat:.5f}, {point.lon:.5f}: "
            + ", ".join(
                f"{k}={v}" for k, v in sorted(point.tags.items()) if not k.startswith("name")
            )
            for point in stats.added_points
        ),
    ]


def _not_found_lines(stats: Stats, inputs: Inputs, in_file: str) -> list[str]:
    """The ids and QIDs of the name list that the extract does not have."""
    by_id, by_qid, reg = inputs.names.by_id, inputs.names.by_qid, inputs.reg
    lines: list[str] = []
    missing = sorted(key for key in set(by_id) - stats.found if key[0] != refs.LOCAL_TYPE)
    if missing:
        lines += ["", f"{len(missing)} rows reference ids that are not in {in_file}:"]
        lines += [
            f"  {refs.format([key])}  {placelist.any_name(by_id[key], reg)}" for key in missing
        ]
    absent = sorted(qid for qid in by_qid if qid not in stats.present_qids)
    if absent:
        lines += [
            "",
            f"{len(absent)} wikidata QIDs not present in the file: "
            + ", ".join(f"{qid} ({placelist.any_name(by_qid[qid], reg)})" for qid in absent),
        ]
    return lines


def _skipped_carrier_lines(stats: Stats, inputs: Inputs) -> list[str]:
    """The objects that carry a row's QID but are left alone (#55)."""
    if not stats.skipped_carriers:
        return []
    by_qid, reg = inputs.names.by_qid, inputs.reg
    return [
        "",
        f"{len(stats.skipped_carriers)} objects carry a QID of the list "
        "but are not place-like -- not tagged:",
        *(
            f"  {refs.format([ref])}  {name}: {qid} ({placelist.any_name(by_qid[qid], reg)})"
            for ref, name, qid in stats.skipped_carriers
        ),
    ]


def _curated_lines(stats: Stats, inputs: Inputs, in_file: str) -> list[str]:
    tunings = inputs.curation.objects
    if not tunings:
        return []
    by_type = collections.Counter(osm_type for osm_type, _ in stats.curated)
    lines = [
        "",
        f"curated {len(stats.curated)} objects: {by_type['n']} nodes, "
        f"{by_type['w']} ways, {by_type['r']} relations",
    ]
    lines += [
        f"  {refs.format([key])}  {tunings[key]['label'] or '?'}: "
        + ", ".join(f"{k}={v}" for k, v in sorted(tunings[key]["tags"].items()))
        for key in sorted(stats.curated)
    ]
    missing = sorted(set(tunings) - stats.curated)
    if missing:
        lines += ["", f"{len(missing)} curation rows reference ids that are not in {in_file}:"]
        lines += [f"  {refs.format([key])}  {tunings[key]['label'] or '?'}" for key in missing]
    return lines


def _square_lines(stats: Stats, inputs: Inputs, in_file: str) -> list[str]:
    """The synthetic polygons added, and those whose node the extract lacks."""
    squares = inputs.curation.squares
    if not (squares or stats.added_squares):
        return []
    lines = ["", f"added {len(stats.added_squares)} synthetic polygon(s):"]
    lines += [
        f"  {refs.format([('w', square.way_id)])} "
        f"({_node(square.node_ids[0])}..{_node(square.node_ids[-1])})  "
        f"{square.label or '?'}: {square.km2:g} km²"
        for square in stats.added_squares
    ]
    lines += [
        f"  ! {refs.format([key])} {squares[key]['label'] or '?'}: node not in "
        f"{in_file}, no polygon added"
        for key in sorted(set(squares) - {square.key for square in stats.added_squares})
    ]
    return lines
