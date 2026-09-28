"""The North Frisian map's pipeline: the name list and its checks, the OSM
matching and curation, the dialect areas, the search index and the tile
injector.

Library modules (imported by the rest): `paths`, `errors`, `registry`,
`placelist`, `curationlist`, `dialects`, `geo`, `osmscan`, `osmgeom`,
`locate`, `nameindex`, `candidates`, `provenance`.  Each command has a module of its
own with a `main(argv)`; the scripts in names/ and tiles/ only launch it.
"""
