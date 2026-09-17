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
Vite), `npx tsc --noEmit` (type-check only), `npm run lint` (oxlint).

The map is created with MapLibre's `hash: true` option, so the URL hash
reflects the current view (`#zoom/lat/lon`, e.g. `#13/54.52/8.65`) and an
initial view can be linked to or loaded directly, e.g.
`http://localhost:5173/#12/54.64/8.77`. Useful for sharing a view or for
scripted screenshots at a specific place/zoom.

## Tile hosting

The **only** place this frontend depends on how/where tiles are hosted is
`VITE_TILES_URL`, read in `src/config.ts`. Copy `.env.example` to `.env` to
override it (e.g. to point at a CDN-hosted PMTiles archive). Unset, it
defaults to a PMTiles file served by this site itself:

```
pmtiles:///tiles/schleswig-holstein.pmtiles
```

i.e. `web/public/tiles/schleswig-holstein.pmtiles`, resolved relative to the
site origin. That path is gitignored (`public/tiles/*.pmtiles`) — only
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

`nameExpression(tag)` in `src/style/localize.ts` produces the `text-field` of
every name-based symbol layer. Dialect view (`tag = "frr-x-mooring"`):

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
  e.g. `Foortuftinge`. Informational; nothing in the style reads it yet.
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
`public/data/names.json`, fetched once at startup. Schema (one entry per
place):

```jsonc
{
  "id": "string",                 // stable identifier, e.g. "node/240044177"
  "names": { "frr-x-mooring": "Naibel" },  // by registry tag; only non-empty ones
  "local": "string",              // omitted when unknown: the place's own name
  "dialect": "frr-x-fering",      // omitted outside the Frisian dialect areas
  "variety": "Foortuftinge",      // omitted: sub-dialect of the local name
  "name_de": "string",            // German name, shown alongside as a hint
  "lon": 0,
  "lat": 0,
  "kind": "string"                // e.g. "settlement", "island", "hallig"
}
```

Written by `names/export_search_index.py`; only non-empty values are
exported, so an absent field really means "no such name".

**All** of an entry's names (every dialect, the local one and the German one)
are flattened into one indexed string, so a place stays findable under any of
its names whichever view is selected — typing "Naibel" while the map is in
Fering still finds Niebüll. Which name a result *shows* follows the selected
option, mirroring the label chain above: dialect view `names[tag] ?? local ??
name_de`, local view `local ?? name_de`, with the German name on the second
line when it differs. Selecting a result flies the map to it.

## i18n

`i18next` + `react-i18next`, configured in `src/i18n.ts`; the UI language
follows the selected label option (see "Dialect registry and the selector").
One JSON file per dialect in `src/locales/`, same keys in each:

- `de.json` — German UI strings (search placeholder, dialect label, "no
  results", attribution text). This is the fallback language
  (`fallbackLng: 'de'`).
- `frr-x-mooring.json` — Mooring UI strings. Strings nobody has written yet
  (`attribution`, `dialect.local`) are left as **empty strings — never
  invented** — so the UI falls back to German rather than showing blank text
  (`returnEmptyString: false` makes i18next treat an empty string as
  "missing" for fallback purposes). Fill them in once real Mooring wording
  exists.

## Not done / left as-is

- Mooring UI translations for the remaining keys (see i18n section above),
  including the name of the local-dialect view (`dialect.local`).
- Nothing reads `frasch:dialect`/`frasch:variety` yet — they are exported so
  a later UI can say which dialect a label is in.
- The `within`-polygon split of the label chain for non-German areas (see
  "Label chain").
