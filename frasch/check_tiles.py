"""Do the tiles and the search index agree?  Decode a built PMTiles archive
and compare every labelled feature with its entry in names.json.

    frasch check-tiles <archive.pmtiles> [--zoom 14]

A feature that carries a `frasch:ref` must say what that row's search entry
says: every field of the table of tile keys (placenames.TILE_KEY) -- the same
`frasch:kind`, `frasch:dialect`, `frasch:local` and `frasch:variety`, the
same `name:de` where the list has a German name (the place card's German
step reads the list's, the label the tile's, #61) -- the same name in every
dialect of the registry and, for a node, the same position (a polygon's
label point is Planetiler's own choice).  Only the feature of
the entry's own object is held to that (the first reference of the row's
`osm` cell, or its local reference): a row's other objects lie elsewhere and
may lie in another dialect area, and objects found through a Wikidata QID
have no entry to compare with.

Both sides are built from the same files (names/osm_objects.json,
names/dialect_areas.geojson, names/places.csv) by the same rule
(frasch.placenames), so a disagreement means the archive and the index were
built from different states of them -- compare their `built_from` stamps --
or one of two things the injector does to a feature beyond that rule: a
second row that claims the entry's object fills what the first leaves empty
(`frasch check-inputs` rejects such a claim), and a curation row may set a
tag of its own on it, `frasch:kind` among them.  Anything else is a bug
(#24).  The tile build does not run in CI; run this (`just check-tiles`)
after building tiles.
"""

from __future__ import annotations

import gzip
import json
import math
import sys
from collections.abc import Iterator, Mapping, Sequence
from typing import Literal, NotRequired, TypedDict

import mapbox_vector_tile
from pmtiles.reader import MmapSource, Reader

from frasch import cli, registry
from frasch.geo import LonLat
from frasch.placenames import GERMAN_KEY, REF_KEY, TILE_KEY, SearchEntry, dialect_key
from frasch.registry import Registry

# OpenMapTiles feature ids: the OSM id times ten plus the type
# (web/src/names.ts's osmRefFromFeatureId)
OSM_TYPE_BY_DIGIT = {1: "node", 2: "way", 3: "relation"}
TOLERANCE_DEG = 1e-4  # ~10 m, far above tile precision at z14

# the value of a feature property in a vector tile
PropValue = str | int | float | bool


class Label(TypedDict):
    """A labelled feature of the tiles: its OSM object (`node/1`, None for
    one the injector added), its properties and, for a point, its position."""

    osm: str | None
    props: dict[str, PropValue]
    lon: NotRequired[float]
    lat: NotRequired[float]


def compare(
    entries: Mapping[str, SearchEntry], features: Sequence[Label], reg: Registry
) -> list[str]:
    """The disagreements between the search entries (`{id: entry}`) and the
    labelled features (`{"osm": "node/1" or None, "props": {...}}`, with
    `lon`/`lat` for a point feature), as readable lines."""
    problems = []
    for f in features:
        ref = f["props"].get(REF_KEY)
        entry = entries.get(ref) if isinstance(ref, str) else None
        if entry is None or not _is_entry_object(entry, f):
            continue
        where = f"{ref} ({f['osm'] or 'added by the injector'})"
        for field, key, said in _repeated(entry, reg):
            shown = f["props"].get(key)
            if said != shown:
                problems.append(f"{where}: tiles {key}={shown!r}, names.json {field}={said!r}")
        if (
            _is_point_object(f)
            and math.dist((f["lon"], f["lat"]), (entry["lon"], entry["lat"])) > TOLERANCE_DEG
        ):
            problems.append(
                f"{where}: tiles at {f['lat']:.5f}, {f['lon']:.5f}, "
                f"names.json at {entry['lat']:.5f}, {entry['lon']:.5f}"
            )
    return problems


def _repeated(entry: SearchEntry, reg: Registry) -> Iterator[tuple[str, str, object]]:
    """What the entry's feature must repeat, as (the entry's field, the tile
    property it is in, the entry's value -- None for none): every field of
    placenames.TILE_KEY and its name in every dialect.  Only the German name
    may differ, where the list has none: there the tiles keep OSM's (#61)."""
    for field, key in TILE_KEY.items():
        if key != GERMAN_KEY or entry["name_de"]:
            yield field, key, entry.get(field) or None
    for tag in reg.tags:
        yield f"names[{tag}]", dialect_key(tag), entry["names"].get(tag)


def checked_entries(entries: Mapping[str, SearchEntry], features: Sequence[Label]) -> set[str]:
    """The ids of the entries `compare` holds to a feature: those whose own
    object is among the features, not merely another object of the row."""
    return {
        ref
        for f in features
        if isinstance(ref := f["props"].get(REF_KEY), str)
        and ref in entries
        and _is_entry_object(entries[ref], f)
    }


def _is_point_object(feature: Label) -> bool:
    """Whether a point feature is where the object is: a node, or a node the
    injector added (no OSM id).  A way or relation labelled as a point sits
    where Planetiler put its label, which is its business, not ours."""
    return "lon" in feature and (feature["osm"] is None or feature["osm"].startswith("node/"))


def _is_entry_object(entry: SearchEntry, feature: Label) -> bool:
    """Whether the feature is the object the entry was placed by."""
    osm = entry.get("osm", "")
    if osm.startswith("local/"):
        return True
    return feature["osm"] == osm.split(";")[0].strip()


# ------------------------------------------------------------- the archive ----
class _PointGeometry(TypedDict):
    type: Literal["Point"]
    coordinates: list[float]  # [x, y] in tile units, y pointing down


class _ShapeGeometry(TypedDict):
    # coordinates never read here
    type: Literal["LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon"]


class _TileFeature(TypedDict):
    """A feature as mapbox_vector_tile decodes it."""

    geometry: _PointGeometry | _ShapeGeometry
    properties: dict[str, PropValue]
    id: NotRequired[int]


class _TileLayer(TypedDict):
    extent: int
    features: list[_TileFeature]


def tile_of(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """The (x, y) of the web-mercator tile holding a point."""
    n = 2**zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def lonlat(zoom: int, x: int, y: int, px: float, py: float, extent: int) -> LonLat:
    """A tile-local point (y pointing down) in degrees."""
    n = 2**zoom
    lon = (x + px / extent) / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / extent) / n))))
    return lon, lat


def osm_ref(feature_id: int | None) -> str | None:
    """`node/1` for an OpenMapTiles feature id, None for an id the injector
    or Planetiler made up."""
    if not isinstance(feature_id, int) or feature_id <= 0:
        return None
    kind = OSM_TYPE_BY_DIGIT.get(feature_id % 10)
    return f"{kind}/{feature_id // 10}" if kind else None


def tile_features(data: bytes, zoom: int, x: int, y: int) -> list[Label]:
    """The features of one (gzip-compressed) tile that carry a row's id."""
    layers: dict[str, _TileLayer] = mapbox_vector_tile.decode(
        gzip.decompress(data), default_options={"y_coord_down": True}
    )
    out: list[Label] = []
    for layer in layers.values():
        for f in layer["features"]:
            if REF_KEY not in f["properties"]:
                continue
            feature: Label = {"osm": osm_ref(f.get("id")), "props": f["properties"]}
            geom = f["geometry"]
            if geom["type"] == "Point":
                px, py = geom["coordinates"]
                lon, lat = lonlat(zoom, x, y, px, py, layer["extent"])
                feature |= {"lon": lon, "lat": lat}
            out.append(feature)
    return out


def archive_features(path: str, entries: Mapping[str, SearchEntry], zoom: int) -> list[Label]:
    """The labelled features of the tiles the entries lie in, each once."""
    seen: set[tuple[str | None, PropValue, float | None, float | None]] = set()
    out: list[Label] = []
    with open(path, "rb") as fh:
        reader = Reader(MmapSource(fh))
        for x, y in sorted({tile_of(e["lon"], e["lat"], zoom) for e in entries.values()}):
            data: bytes | None = reader.get(zoom, x, y)
            for f in tile_features(data, zoom, x, y) if data else []:
                key = (f["osm"], f["props"][REF_KEY], f.get("lon"), f.get("lat"))
                if key not in seen:
                    seen.add(key)
                    out.append(f)
    return out


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("check-tiles", __doc__)
    ap.add_argument("archive")
    cli.add_workspace_options(ap, "index", "dialects")
    ap.add_argument("--zoom", type=int, default=14)
    a = ap.parse_args(argv)
    ws = cli.workspace(a)
    index = ws.index
    with open(index, encoding="utf-8") as fh:
        entries: dict[str, SearchEntry] = {e["id"]: e for e in json.load(fh)["places"]}
    features = archive_features(a.archive, entries, a.zoom)
    problems = compare(entries, features, registry.read(ws.dialects))
    print(
        f"{len(features)} labelled features in the z{a.zoom} tiles of "
        f"{len(entries)} entries; {len(checked_entries(entries, features))} "
        f"entries compared on their own object"
    )
    for p in problems:
        print(f"  ! {p}")
    if problems:
        print(f"{len(problems)} disagreement(s) between {a.archive} and {index}", file=sys.stderr)
        return 1
    return 0
