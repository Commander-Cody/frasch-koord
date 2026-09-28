# frasch-maps

A web map with its labels and interface in North Frisian, starting with the
Mooring dialect. The names come from a hand-kept list of North Frisian place
names. They are joined to OpenStreetMap objects, written into vector tiles
(OpenMapTiles schema, built with Planetiler into a PMTiles archive), and shown
with MapLibre GL JS.

| directory | what |
|---|---|
| [`names/`](names/README.md) | the name list (`places.csv`, the single source of truth) and the Python pipeline that matches it to OSM, checks it and exports the search index |
| [`tiles/`](tiles/README.md) | the tile build: injects the names into an OSM extract, then runs Planetiler |
| [`web/`](web/README.md) | the frontend: React + Vite + TypeScript, MapLibre, PMTiles |
| [`docs/`](docs/project-decisions.md) | decisions and open questions |

## Setup

Python, for the name pipeline and the tile build. [uv](https://docs.astral.sh/uv/)
creates `.venv` from `pyproject.toml` and `uv.lock`:

```sh
uv sync
.venv/bin/pytest                    # tests of names/ and tiles/
.venv/bin/python names/check.py     # check places.csv, curation.csv, dialects.csv
.venv/bin/ruff check .
uv run just check                   # the committed build outputs match their inputs
uv run shellcheck tiles/*.sh web/scripts/*.sh
```

The whole pipeline — extracts, matching, locating, dialect areas, search
index, tiles — runs through the recipes of the `justfile`
(`uv run just --list`; `just` comes with `uv sync`). See
[`names/README.md`](names/README.md#workflow).

Node 24 (see `web/.nvmrc`), for the frontend:

```sh
cd web
npm ci
npm run dev                         # also: npm test, npm run lint, npm run typecheck
```

The map needs a tile archive and the glyphs, which are not in git. See
[`web/README.md`](web/README.md) for how to get them, and
[`tiles/README.md`](tiles/README.md) for building tiles (JDK 21).

CI (`.github/workflows/ci.yml`) runs all of the above checks on every push,
plus `npm run build` and `npm run check:build`.

## License

- **Code:** MIT, see [`LICENSE`](LICENSE).
- **Name list** (`places.csv` and the other hand-edited files in `names/`):
  Open Database License 1.0, see [`names/LICENSE`](names/LICENSE).
  Attribution: "Frasche stääsnoome, Thore Andresen, ODbL 1.0".
- **Map style and sprites:** a fork of OSM Bright, BSD 3-Clause (code) and
  CC BY 4.0 (design), see
  [`web/src/style/LICENSE-osm-bright.md`](web/src/style/LICENSE-osm-bright.md).
- **Map data:** © OpenStreetMap contributors, ODbL; tiles in the
  OpenMapTiles schema (© OpenMapTiles).
