"""Export the rows of names/places.csv that are on the map as the client-side
search index used by web/ (web/public/data/names.json) -- what goes into it,
and why, is frasch/searchindex.py's docstring.

Usage: names/export_search_index.py [--names names/places.csv]
                                    [--dialects names/dialects.csv]
                                    [--areas names/dialect_areas.geojson]
                                    [--objects names/osm_objects.json]
                                    [--curation names/curation.csv]
                                    [--out web/public/data/names.json]
"""
import argparse
import os

from frasch import cli, paths, searchindex


@cli.command
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default=paths.PLACES)
    ap.add_argument("--dialects", default=paths.DIALECTS)
    ap.add_argument("--areas", default=paths.DIALECT_AREAS)
    ap.add_argument("--objects", default=paths.OBJECTS)
    ap.add_argument("--curation", default=paths.CURATION,
                    help="positions of the local references (places OSM does not have)")
    ap.add_argument("--out", default=paths.SEARCH_INDEX)
    a = ap.parse_args(argv)
    index = searchindex.build(a.names, a.dialects, a.curation, a.areas, a.objects)
    searchindex.write(index, a.out)
    places = index["places"]
    print(f"wrote {len(places)} entries to {a.out} "
          f"({os.path.getsize(a.out)/1e3:.0f} kB); "
          f"{sum(1 for e in places if 'dialect' in e)} in a dialect area, "
          f"{sum(1 for e in places if 'local' in e)} with a local name, "
          f"{sum(1 for e in places if 'name_nds' in e)} with a Low Saxon one; "
          f"rows keyed by Wikidata alone (no position) are left out")
    return 0
