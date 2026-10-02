# frasch-maps

A web map with its labels and interface in North Frisian, starting with the
Mooring dialect. The names come from a hand-kept list of North Frisian place
names. They are joined to OpenStreetMap objects, written into vector tiles
(OpenMapTiles schema, built with Planetiler into a PMTiles archive), and shown
with MapLibre GL JS.

| directory | what |
|---|---|
| [`names/`](names/README.md) | the name list (`places.csv`, the single source of truth) and the pipeline that matches it to OSM, checks it and exports the search index |
| [`tiles/`](tiles/README.md) | the tile build: injects the names into an OSM extract, then runs Planetiler |
| [`frasch/`](names/README.md#code) | the Python code of both, one package; the scripts in `names/` and `tiles/` only launch its commands |
| [`web/`](web/README.md) | the frontend: React + Vite + TypeScript, MapLibre, PMTiles |
| [`docs/`](docs/project-decisions.md) | decisions and open questions |

## Setup

You need [uv](https://docs.astral.sh/uv/) (it brings Python 3.12 and, as a
dev dependency, `just`) and Node 24 (see `web/.nvmrc`) on `PATH`. Every
routine task is a recipe of the root `justfile`; `uv run just` lists them by
group:

```sh
uv run just setup        # once, and after a lockfile change: the venv, web/'s packages,
                         #   the glyphs and the published tile archive (not in git),
                         #   and the smoke test's headless Chromium
uv run just dev          # the map's dev server
uv run just check        # every lint, format, type check and test, Python and web
uv run just format       # format all code
uv run just build        # the production build of the site into web/dist/, checked
uv run just smoke        # build, then smoke-test it in headless Chromium
uv run just update       # after editing the name list or curating in ?curate
```

`check` runs every check even after one fails and lists the failed ones at
the end; `check-python` is its Python half. The name pipeline — extracts,
matching, locating, dialect areas, search index — is `update` in one go, see
[`names/README.md`](names/README.md#workflow); its single steps and the tile
recipes are listed under their own groups.

`web/` needs no Python: `npm ci`, `npm run fetch-assets`, then `npm run dev`,
`npm run check`, `npm run build` or `npm run smoke` there, see
[`web/README.md`](web/README.md). On a bare Linux the smoke test's browser
also needs system libraries, once: `sudo npx playwright install-deps` in
`web/`.

Both parts have a formatter, and CI fails on unformatted code: `ruff format`
for Python, [oxfmt](https://oxc.rs/docs/guide/usage/formatter) for `web/`
(configured in `web/.oxfmtrc.json`). The commit that first formatted
everything is listed in `.git-blame-ignore-revs`; to have `git blame` skip
it:

```sh
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

The map needs a tile archive and the glyphs, which are not in git:
`npm run fetch-assets` (part of `setup`) fetches both, the archive as pinned
in `web/tiles.lock` (see [`web/README.md`](web/README.md#tile-hosting)).
Building tiles yourself is only needed to change them, see
[`tiles/README.md`](tiles/README.md) (JDK 21).

CI (`.github/workflows/ci.yml`) runs `uv run just check-python`,
`npm run check` and `npm run smoke` on every push, the last against the
fetched assets.

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
