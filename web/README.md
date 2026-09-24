# frasch-maps — web

Google-Maps-like web map with labels and UI in North Frisian (dialect: Mooring
first). React + Vite (TypeScript) frontend using MapLibre GL JS and PMTiles.
See `/docs/project-decisions.md` at the repo root for the overall project
context.

## Running

```sh
source ~/.nvm/nvm.sh   # Node 24 via nvm; not on PATH in non-interactive shells
nvm use                # picks up 24 from .nvmrc
npm install
npm run dev
```

Other scripts: `npm run build` (type-checks with `tsc -b` then builds with
Vite), `npm run typecheck` (`tsc -b` only; `npx tsc --noEmit` checks nothing,
the root tsconfig has `files: []`), `npm run lint` (oxlint), `npm test`
(Vitest, `src/**/*.test.ts(x)`), and the two checks of a production build
below.

## Production build

`npm run build` writes `dist/`, which `npm run preview` serves. Two things
make a build differ from `npm run dev`, and each has a check:

- **The MapLibre worker.** MapLibre 6 looks for `maplibre-gl-worker.mjs` next
  to its own module, a file Vite never emits; a production build would get
  `index.html` back and parse no tile at all. `src/components/Map.tsx` imports
  the worker with `?worker&url`, so Vite bundles it (with the shared chunk it
  imports) as `assets/maplibre-gl-worker-<hash>.js`, and hands that URL to
  `setWorkerUrl` before any map exists.
- **No dev tools.** `?curate` and `?areas` (below) are chosen in
  `src/main.tsx` behind `import.meta.env.DEV`, so the build leaves them and
  `src/dev/` out entirely; there the parameters open the public map.

After a build:

```sh
npm run check:build   # dist/ has the worker the bundle names, no dev tool strings
npm run smoke         # vite preview + headless Chromium: map loads, search, card
```

`npm run smoke` needs the tiles and glyphs in `public/` (see below) and
Playwright's headless Chromium, once: `npx playwright install
chromium-headless-shell` (plus `sudo npx playwright install-deps` for the
system libraries on a bare Linux).

**Base path.** Everything the site serves itself — `data/names.json`, the
glyphs, the sprites, the default tiles URL — goes through `siteUrl()` in
`src/config.ts`, which prefixes Vite's `base`. So the same code runs at a
domain root or under a sub-path, e.g. a GitHub Pages project site:
`npx vite build --base /frasch-koord/`.

**What `dist/` holds.** Vite copies `public/` as it is: the name list, the
sprites, the ~100 MB of glyphs in `public/fonts/` (the style always loads them
from the site) and the ~125 MB PMTiles archive. With `VITE_TILES_URL` set the
tiles live elsewhere, and `vite-plugins/external-tiles.ts` leaves the archive
out of `dist/`.

**Load errors are shown, not just logged.** A `names.json` that fails to load
(an HTTP error, or an SPA fallback's `index.html`) puts an error line under
the search field instead of "no results" to every query; a map error (tiles,
glyphs, sprites, or a first render that has not happened after 30 s) shows a
strip at the top of the map; and a crash in the side panel is caught by
`src/components/ErrorBoundary.tsx`, so it never takes the map with it.

The map is created with MapLibre's `hash: true` option, so the URL hash
reflects the current view (`#zoom/lat/lon`, e.g. `#13/54.52/8.65`) and an
initial view can be linked to or loaded directly, e.g.
`http://localhost:5173/#12/54.64/8.77`. Useful for sharing a view or for
scripted screenshots at a specific place/zoom.

MapLibre rewrites the whole hash on every move, so the rest of what a link
carries lives in the query string (`src/urlState.ts`), which it leaves alone:

- `?view=<tag>` — the selected label option (`frr-x-mooring`, `frr-x-local`,
  …). A tag the selector does not offer falls back to the default.
- `?place=<id>` — the name-list id of the place whose card is open
  (`node/240042766`, `local/<slug>`). Only name-list places can be linked; a
  card built from a tile feature alone has nothing to look it up by before
  its tile is on screen. With a `#zoom/lat/lon` the link opens there and just
  marks the place; without one the map flies to it, like a search result.

App keeps both in sync with `history.replaceState`, so the address bar always
is a link to what is on screen, e.g.
`/?view=frr-x-local&place=node/240042766#12/54.79/8.83`. The share button
next to the dialect selector hands that URL to the system share sheet on
touch devices and copies it everywhere else (`src/components/ShareButton.tsx`).

## Tile hosting

The **only** place this frontend depends on how/where tiles are hosted is
`VITE_TILES_URL`, read in `src/config.ts`. Copy `.env.example` to `.env` to
override it (e.g. to point at a CDN-hosted PMTiles archive). Unset, it
defaults to a PMTiles file served by this site itself:

```
pmtiles://<site>/tiles/schleswig-holstein.pmtiles
```

i.e. `web/public/tiles/schleswig-holstein.pmtiles`, resolved against the page
and the site's base path (`siteUrl()` in `src/config.ts`). That path is gitignored (`public/tiles/*.pmtiles`) — only
`public/tiles/.gitkeep` is tracked. For local development, symlink or copy a
built PMTiles archive there, e.g.:

```sh
ln -s ../../../tiles/data/schleswig-holstein-baseline.pmtiles \
  web/public/tiles/schleswig-holstein.pmtiles
```

(This symlink already exists in this checkout, pointing at
`tiles/data/schleswig-holstein-baseline.pmtiles`; it won't survive a fresh
clone since it's gitignored — recreate it locally.)

The `pmtiles://` protocol is registered once with MapLibre in
`src/components/Map.tsx` (`addProtocol('pmtiles', protocol.tile)`); MapLibre
then reads TileJSON straight out of the archive itself.

## Map style and dialect-aware labels

### Style ownership

- `src/style/frasch-bright.json` **is our style**, edited directly. It
  started as a fork of upstream OSM Bright
  ([openmaptiles/osm-bright-gl-style](https://github.com/openmaptiles/osm-bright-gl-style),
  `openmaptiles:version` "3.x", downloaded as-is on 2026-09-15 — see
  `docs/project-decisions.md`) and was renamed from `osm-bright.json` on
  2026-09-15, when the `place`-layer label group was restructured for
  Frisian place kinds (see "Label classes" below). Everything else in the
  file is still stock OSM Bright.
- `src/style/localize.ts` — `buildStyle(baseStyle, tilesUrl, labels)` keeps
  doing only what has to stay dynamic at runtime:
  - points the `openmaptiles` source at `tilesUrl` and adds OSM/OpenMapTiles
    attribution to it;
  - rewrites every name-based symbol layer's `text-field` to
    `nameExpression(labels)` below;
  - points `glyphs`/`sprite` at the locally hosted copies below, resolved
    as absolute URLs against the page origin (MapLibre requires this for
    sprites).

  Layers labelling something else (e.g. `{ref}` road shields) are left
  untouched. Changing the selector calls `map.setStyle()` with a freshly
  built style for the new label option.

### Dialect registry and the selector

`names/dialects.csv` is the single list of North Frisian dialects for the
whole project; the exporter writes it to `src/generated/dialects.json`
(`{tag, column, label, status, view}` per dialect, registry order) which
`src/config.ts` imports — **generated, do not edit by hand.** `config.ts`
derives the one dropdown from it:

- one option per dialect with `view = yes` (today only Mooring — the other
  dialects' name coverage is too thin for a whole map view), labelled from
  the registry;
- plus the **local dialect** view, `LOCAL_TAG = 'frr-x-local'`. That is not a
  real dialect and has no `name:<tag>` tile property: it labels every place
  the way the people of that place speak (the injector's `frasch:local`), so
  one map shows Mooring around Niebüll, Fering on Föhr, Sölring on Sylt…

Each option carries a `uiLanguage`, and `App.tsx` calls
`i18n.changeLanguage(option.uiLanguage)` when the selection changes, so map
labels and UI chrome move together. A dialect view uses its own dialect;
the local view has no dialect of its own and borrows one —
`LOCAL_VIEW_UI_LANGUAGE` in `config.ts` (Mooring today) is the single place
to change that. i18next falls back to German for every language without
resources, so an option whose UI is unwritten is harmless.

### Label chain

`labelChain(tag)` in `src/labelChain.ts` is the one definition of which name
a place is shown by. `nameExpression(tag)` in `src/style/localize.ts` turns it
into the `text-field` of every name-based symbol layer, and `resolveName` in
`src/names.ts` walks the same chain over a name-list entry for the place card
and the search results — so neither can drift from the map label again (it
did once: the card said Flensburg where the map said Flensborg). Dialect view
(`tag = "frr-x-mooring"`):

```
coalesce(name:frr-x-mooring, frasch:local, name:frr, name:nds, name:de, name:latin, name)
```

i.e. `coalesce(get "name:frr-x-mooring", get "frasch:local", get "name:frr",
get "name:nds", get "name:de", get "name:latin", get "name")`. `frasch:local`
sits right behind the selected dialect so that a place the dialect has no
name for still gets a *Frisian* label (the Fering name on Föhr) rather than
dropping to German.

Local view (`tag = LOCAL_TAG`):

```
coalesce(frasch:local, name:nds, name:latin, name)
```

Deliberately **no `name:frr`** — that is some other dialect's name, which is
exactly what this view avoids — and **no `name:de`**: German still arrives
via `name:latin`/`name`, but only after Low Saxon has had its turn.

Both chains assume Low Saxon is the local majority language wherever there is
no Frisian name, which holds for Phase 1 (Schleswig-Holstein tiles only) and
breaks as soon as the tiles leave northern Germany. Planned for the planet
build, not yet implemented: two symbol layers per label layer sharing the same
base filter, one filtered `within` a northern-Germany polygon using these
chains, the other filtered to its complement using a chain without `name:nds`
(and, outside Germany, preferring `name:en` over `name:de`). Not implemented
today because there is no such polygon in the style yet.

### Tile attributes contract (source-layer `place`)

OpenMapTiles schema plus our extras, injected by the `tiles/` build
(`tiles/inject_names.py` and the Planetiler run — see `tiles/README.md`):

- `class` (string): `country`, `state`, `city`, `town`, `village`, `hamlet`,
  `suburb`, `neighbourhood`, `isolated_dwelling`, `island`, … `rank`
  (integer): islands 3..6 by area, villages ~10..14.
- `frasch:kind` (string, **only on features from our name list or
  curation**): `island`, `hallig`, `sand`, `settlement`, `koog`, `harde`,
  `warft`, `landscape`, `water`, `road`, `country`, `helgoland`, `other`.
  Missing on many features — the style always `coalesce`s around its
  absence rather than assuming it's there.
- `frasch:minzoom` (**string**, e.g. `"10"`, only where curated): the
  feature must not be labelled below that zoom.
- `frasch:maxzoom` (**string**, only where curated): the feature must not
  be labelled above that zoom (inclusive).
- `frasch:dialect` (string, only inside a Frisian dialect area): tag of the
  dialect area the feature lies in, e.g. `frr-x-fering`. Not used by the
  style today; it is what `frasch:local` was computed from.
- `frasch:local` (string, only where known): the name the people of the
  place use themselves — the area dialect's name, or the `local` column of
  `names/places.csv` where a sub-dialect differs (Fahretoft). Drives the
  local view.
- `frasch:variety` (string, rare): the sub-dialect the local name belongs to,
  e.g. `Foortuftinge`. Shown by the place card; nothing in the style reads it.
- `frasch:ref` (string, only on features from our name list): which row of
  `names/places.csv` the names come from — `node/240042766`,
  `relation/3352541`, `local/huelltoft`, or a QID for a row without an `osm`
  column. It is the `id` of that row's entry in the search index, which is how
  a click on a label finds the rest of the place's names (see "Place info
  card"). Absent on everything the name list does not cover.
- Names: `name:<tag>` for every dialect of the registry that has a name for
  the feature (`name:frr-x-mooring`, `name:frr-x-fering`, …), plus
  `name:frr`, `name:nds`, `name:de`, `name:da`, `name:latin`, `name`.

The style degrades gracefully when `frasch:*` is absent (an archive built
before the name-list merge): every `frasch:kind`-based filter has a
`class`-based fallback or default, and `frasch:minzoom`'s absence just means
"no floor" (see the minzoom filter clause below).

### Per-feature minzoom / maxzoom filter clauses

Every symbol layer on source-layer `place` gets these clauses `&&`-ed
(`["all", …]`) onto its filter, converted to expression syntax:

```json
[">=", ["zoom"], ["to-number", ["coalesce", ["get", "frasch:minzoom"], 0]]]
["<=", ["zoom"], ["to-number", ["coalesce", ["get", "frasch:maxzoom"], 99]]]
```

`frasch:minzoom` / `frasch:maxzoom` are stored as strings; `to-number`
converts them, and the `coalesce` defaults of `0` / `99` make the clauses
no-ops when the property is absent. Zoom expressions are allowed in filters
in MapLibre 6.x (verified: no console errors, `getFilter()` round-trips the
expression unchanged).

**Nordstrand** is the one place that uses `frasch:maxzoom` today. OSM has
no island polygon for it (it is a peninsula), so `names/curation.csv` makes
the injector add a synthetic 50 km² `place=island` square centred on the
village node: Planetiler then emits the island label at the node's position
from z8 like the other islands' polygons. That feature has `frasch:maxzoom=11`;
the village node itself has `frasch:minzoom=12`, so at z12 "e Strönj" turns
from the island label into the village label at the same spot, and the two
never show together.

### Label classes and priority

The old single `place-other` layer (which rendered island, hamlet,
isolated_dwelling, neighbourhood, … all identically in uppercase) is split
into dedicated layers, keyed on `frasch:kind` first, then `class`:

| Layer            | Filter (besides the minzoom clause above)                                            | Layer `minzoom` | `symbol-sort-key` tier |
|------------------|----------------------------------------------------------------------------------------|:---:|:---:|
| `place-island`   | `frasch:kind == island`, or (no `frasch:kind` and `class == island`)                   | – | 0 (highest) |
| `place-hallig`   | `frasch:kind == hallig`; the smallest Halligen (OpenMapTiles island `rank` 6, e.g. Habel, Norderoog) additionally wait until z12 | – | 1 |
| `place-village`  | `class == village`                                                                      | – | 2 |
| `place-town`     | `class == town`                                                                         | – | 2 |
| `place-sand`     | not a settlement class (city/town/village/state/country/continent) and `frasch:kind == sand` (sands are `place=island` polygons in OSM, so `class == island` must NOT be excluded here) | 10 | 3 |
| `place-other`    | not a settlement class, not `class == island`, not `frasch:kind` island/hallig/sand/warft, and not a Warft by the rule below (i.e. hamlet, neighbourhood, suburb, … as OSM Bright had them) | – | 4 |
| `place-warft`    | not a settlement class, and (`frasch:kind == warft`, or — for features without `frasch:kind` — `class == isolated_dwelling` or a name containing *warf* / *weerw* / *wäärw*). Catches the Hallig Warften that OSM tags `place=hamlet` (Ipkenswarft, Ockenswarft, Olandswarft) so all Warften look the same and start at z13 | 13 | 5 (lowest) |

`symbol-sort-key = tier * 100 + coalesce(rank, 0)`, so within a tier a
bigger/more important feature (lower `rank`) still sorts first.

`place-sand`/`place-warft` explicitly exclude the "big" classes so that a
`frasch:kind` tag can never *demote* a feature OSM/OpenMapTiles already
classifies more prominently — e.g. Tammensiel on Pellworm is `class=village`
**and** `frasch:kind=warft` (a warft that grew into a village); it must stay
in `place-village` rather than drop behind `place-warft`'s `minzoom: 13`
floor, which would bury its curated `frasch:minzoom=10` under an unrelated
class-tier default.

**Cross-layer priority (MapLibre limitation to know about):** MapLibre
processes symbol placement in *reverse* `style.layers` array order — the
*last* layer in the array is inserted into the shared collision index first
and therefore wins collisions; the first layer is processed last and is most
likely to lose (see `PauseablePlacement.continuePlacement` in maplibre-gl:
it starts at `order.length - 1` and counts down). `symbol-sort-key` only
reorders features *within* one layer's own bucket — it cannot change
priority between two different layers. So to get islands > halligen >
town/village > sand > hamlet/other > warft (highest priority first), the
layers appear in the **reverse** of that order in `frasch-bright.json`:
`place-warft`, `place-other`, `place-sand`, `place-village`, `place-town`,
`place-hallig`, `place-island`, then the untouched administrative layers
(`place-state` … `place-continent`), which — as in upstream OSM Bright, whose
existing order already relied on this same reverse-priority behavior — sit
last and so outrank everything above. Verified with
`map.showCollisionBoxes = true`: at z9–z11 island/hallig names (Pellworm,
Hooge, Langeneß, Habel) win their collisions against village names on the
same landmass (Tilli, Tammensiel); at z12 Habel's hallig name wins over its
single Warft (which in any case doesn't render before `place-warft`'s
`minzoom: 13`).

`text-optional`/`icon-optional`: left at their defaults on all of the above
— none of these layers set `icon-image`, so both properties would be no-ops
(they only affect layers that pair an icon with text, like
`place-city-capital`'s star, which is unchanged from upstream).

## Glyphs and sprites (served locally, not from a third party)

- `public/sprites/` — `sprite.json`, `sprite.png`, `sprite@2x.json`,
  `sprite@2x.png`, downloaded from
  https://openmaptiles.github.io/osm-bright-gl-style/. ~136 KB total.
- `public/fonts/` — **not in git** (~100 MB); run `scripts/fetch-fonts.sh` once after cloning. PBF glyph ranges for the three fontstacks OSM Bright's
  style.json actually uses: `Noto Sans Regular`, `Noto Sans Italic`,
  `Noto Sans Bold`. Sourced pre-built from the `noto-sans.zip` asset of the
  [openmaptiles/fonts v2.0 release](https://github.com/openmaptiles/fonts/releases/tag/v2.0)
  (extracted as-is — that asset already contains exactly these three
  stacks, all Unicode ranges, nothing extra). **~102 MB** on disk (256
  range files × 3 stacks). That's committed as-is per the task's "include
  all ranges if they are cheap" guidance; revisit (e.g. trim to Latin/
  Latin-Extended only) if repo size becomes a problem.

## Search

`src/components/SearchPanel.tsx` builds a MiniSearch index over
`public/data/names.json`, which `App` fetches once at startup (`useNames` in
`src/names.ts`) and shares with the place card. Schema (one entry per place):

```jsonc
{
  "id": "string",                 // stable identifier, e.g. "node/240044177"
  "names": { "frr-x-mooring": "Naibel" },  // by registry tag; only non-empty ones
  "local": "string",              // omitted when unknown: the place's own name
  "dialect": "frr-x-fering",      // omitted outside the Frisian dialect areas
  "variety": "Foortuftinge",      // omitted: sub-dialect of the local name
  "name_nds": "string",           // omitted: OSM's Low Saxon name of the matched object
  "name_de": "string",            // German name, shown alongside as a hint
  "name_da": "string",            // omitted: Danish name, where the list has one
  "wikidata": "Q3127",            // omitted: QID of the place, where the row has one
  "lon": 0,
  "lat": 0,
  "kind": "string"                // e.g. "settlement", "island", "hallig"
}
```

`id` is `placelist.entry_id` — the row's first `osm` reference, else its QID —
and the tiles carry the same string as `frasch:ref`. That is the whole link
between a label on the map and its row in the name list.

Written by `names/export_search_index.py`; only non-empty values are
exported, so an absent field really means "no such name".

**All** of an entry's names (every dialect, the local one, Low Saxon and German)
are flattened into one indexed string, so a place stays findable under any of
its names whichever view is selected — typing "Naibel" while the map is in
Fering still finds Niebüll. Which name a result *shows* follows the selected
option through `resolveName`, i.e. the label chain above, with the German
name on the second line when it differs. Selecting a result flies the map to it.

## Place info card

`src/components/PlaceCard.tsx`. Clicking a place label — or picking a search
result — opens a card with the whole name list of that place: the name in the
selected view large at the top, then every other dialect that has a name (in
`names/dialects.csv` order, labelled from the registry, extinct dialects
marked with †), the local form with its `frasch:variety` remark, German,
Danish, and links to the OpenStreetMap object and to Wikidata.

Where the data comes from (`src/names.ts`):

- `App` loads `public/data/names.json` once (`useNames`) and keeps it as
  `byRef`, entries by `id`.
- `Map` hit-tests a 13 px box around the click against the label layers of the
  current style (`placeLayerIds` in `style/localize.ts` reads them off the
  style, so a new label class is clickable without touching the map) and hands
  the topmost feature up.
- The feature's `frasch:ref` looks the row up in `byRef`. `cardEntry` then
  merges the two: the name-list entry wins field by field, the tile fills what
  the list does not have — which is how Föhr shows a Danish name (OSM's
  `name:da`) although our own `da` column is empty there.
- A feature with no row in the list (a plain German village, or an object only
  `names/curation.csv` touches) still gets a card, built from the tile
  attributes alone, with the OSM link decoded from the tile feature id
  (Planetiler writes `osmId * 10 + type`). No QID, and the only Frisian name
  it can show is OSM's dialect-less `name:frr` — which the style labels with
  too, so the card would otherwise contradict the label that was clicked. It
  is marked as coming from OSM (`card.frisian`) and left out wherever it only
  repeats a name the card already shows.
- Low Saxon (`name_nds`) is the same kind of name: the list has no column for
  it, but both chains fall back to `name:nds` before German. A clicked card
  takes it from the tile, one opened from search from `names.json`
  (`export_search_index.py` reads it off the matched OSM object in
  `names/work/matches.csv`). It gets its own line (`card.lowSaxon`) only where
  it differs from both the headline and the German name.

Two details worth knowing:

- **The area dialect's name and the local form are often the same string.**
  `names/dialects.py:dialect_name()` falls the dialect of the place's own area
  back to the `local` column, so e.g. `names["frr-x-fering"]` on Föhr *is* the
  local form. The card shows such a name once, on the local line, which names
  the dialect it belongs to.
- **The headline never lies about which dialect it is in.** When the selected
  dialect has no name for the place, `displayName` falls back to the local or
  the German name, and the line under the headline says so instead of naming
  the selected dialect.

Escape, the × button and a click on the map (that hits no label) close the
card. The open card is in the URL (`?place=`, see above); the "report a wrong
or missing name" link is issue #8.

## Curation view (dev only)

`http://localhost:5173/?curate` swaps the search panel for
`src/dev/CuratePanel.tsx`: the rows `names/match.py` left `ambiguous`
or `not_found`, each with its candidates as numbered pins on the map. Export
the worklist first — `names/curate.py export` writes `names/work/curate.json`
— and run it under `npm run dev`; the endpoints live in a Vite plugin with
`apply: 'serve'` (`vite-plugins/curate.ts`, `GET /__curate/worklist`,
`GET`/`POST /__curate/patch`), and `src/main.tsx` only loads the view under
`vite dev` (`import.meta.env.DEV`), so a production build has neither the
endpoints nor the panel: `?curate` there is just the public map. English only on purpose: it
is a tool for the name list, not part of the map.

Every pick (an OSM reference, a local reference, or a skip) is appended to
`names/work/curate-patch.jsonl` — append-only, last entry per row wins, a
`clear` withdraws one — which `names/curate.py apply` folds back into
`names/places.csv` and `names/curation.csv`. Nothing in `names/` is written by
the browser directly. The selected row is mirrored into the URL
(`?curate&line=481`, next to MapLibre's view hash), so a reload or a pasted
link reopens the same row; ↑/↓ or `j`/`k` walk the list. A place that is
several OSM objects is picked by ticking candidates and lookup results (or
shift-clicking their pins) and "Pick N selected": one entry with
`osm: "a; b; c"`, plus a wikidata id only when the ticked objects agree on one.

The "Nominatim" and "Overpass" lookups are **called from the browser** against
the public instances (`nominatim.openstreetmap.org`, `overpass-api.de`), bounded
to the North Frisia bbox of the worklist. Light, hand-driven use only — that is
what those instances' usage policies allow; errors and rate limits show up as a
message in the panel.

## Dialect-area review (dev only)

`http://localhost:5173/?areas` swaps the search panel for
`src/dev/AreaPanel.tsx`: every municipality of
`names/dialect_areas.csv` drawn in its dialect's colour, so the mainland
assignments — a researched draft nobody has checked — can be reviewed on the
map instead of in a spreadsheet. Clicking a polygon or a list row shows the
municipality, the dialect and the row's research `note` verbatim. The
municipalities **no row claims** are drawn in grey: those places get no dialect
at all, and the detail block hands you the `relation/<id>` to paste into a new
CSV row. `?areas&area=<line>` reopens a row (line in `dialect_areas.csv`); ↑/↓
or `j`/`k` walk the list. English only on purpose, like the curation view.

Build the geometry first —
`names/build_dialect_areas.py tiles/data/schleswig-holstein-latest.osm.pbf`
writes `names/dialect_areas_parts.geojson` — and run under `npm run dev`; the
endpoint is a Vite plugin with `apply: 'serve'` (`vite-plugins/areas.ts`,
`GET /__areas/parts`), and like the curation view it is only loaded under
`vite dev`, so a production build has none of it. That is deliberate
as well as tidy: the notes quote research prose about assignments nobody has
confirmed ("best guess only", "no direct source found"), which should not ship
to the public site. **The view is read-only** — unlike `?curate`, nothing
writes back. Edit `names/dialect_areas.csv`, re-run the build, press *Reload*.

The four layers (`src/dev/areaLayers.ts`) are inserted before
`waterway-name`, the style's first symbol layer, so no place label is ever
covered. The outline is drawn in the **same hue as the fill at ~3x the alpha**:
that is what keeps two adjacent municipalities *of the same dialect* apart,
which is the whole job, since what is being reviewed is a per-municipality
assignment. `fill-antialias` cannot do it — it draws the fill's own edge in the
fill colour.

The eleven dialect colours were not picked by eye. The hues come from the
data-viz reference palette, and the assignment was solved against the dialect
adjacency computed from the geometry itself (which turned up
Sölring/Wiedingharder as a touching pair, out in the Wattenmeer): every
touching pair, and every pair within ~6 km, clears the colour-vision gates with
~1.5x margin. Eleven categories cannot all be pairwise colourblind-safe — no
choice of eleven hues can — so pairs that never touch may look alike under
protan, Karrharder/Südergoesharder most of all. Colour is therefore never the
only channel: the legend pairs each swatch with its name, the list is grouped
by dialect, the detail block spells the dialect out, and clicking a legend row
draws that dialect alone.

The checklist of rows to confirm is `docs/dialect-area-review.md`.

## i18n

`i18next` + `react-i18next`, configured in `src/i18n.ts`; the UI language
follows the selected label option (see "Dialect registry and the selector").
One JSON file per dialect in `src/locales/`, same keys in each:

- `de.json` — German UI strings (search placeholder, dialect label, "no
  results", the place card's row labels under `card.*`, the kind names under
  `kind.*` — both our own `frasch:kind` values and the OpenMapTiles `class`
  values a place outside the name list has — and the attribution text). This
  is the fallback language (`fallbackLng: 'de'`).
- `frr-x-mooring.json` — Mooring UI strings. Strings nobody has written yet
  (`attribution`, `dialect.local`, all of `card.*` and `kind.*`) are left as
  **empty strings — never invented** — so the UI falls back to German rather
  than showing blank text
  (`returnEmptyString: false` makes i18next treat an empty string as
  "missing" for fallback purposes). Fill them in once real Mooring wording
  exists.

## Not done / left as-is

- Mooring UI translations for the remaining keys (see i18n section above),
  including the name of the local-dialect view (`dialect.local`).
- Nothing in the *style* reads `frasch:dialect`/`frasch:variety`; the place
  card does.
- The `within`-polygon split of the label chain for non-German areas (see
  "Label chain").
