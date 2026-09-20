# Dialect-area review checklist (issue #2)

The 58 mainland rows of `names/dialect_areas.csv` were assigned from German
Wikipedia by a research agent; the 25 island/Hallig rows are older and were not
part of that run. Nothing here is owner-verified yet, and a wrong row is
invisible in the data: a place is joined to a dialect area by point-in-polygon
at build time, never by name, so a bad assignment only ever shows up as a wrong
label on the map.

Rows are listed by **name**. The line number is the fast path for
`?areas&area=<line>` and shifts whenever a row is added or removed.

## How to check a row

```bash
.venv/bin/python names/build_dialect_areas.py tiles/data/schleswig-holstein-latest.osm.pbf
cd web && npm run dev      # then open http://localhost:5173/?areas
```

Click a municipality, or a row in the list: the panel shows its name, the
assigned dialect and the full `note` from the CSV. Wrong? Edit
`names/dialect_areas.csv` by hand, re-run the build, press **Reload** in the
panel. Nothing writes the CSV from the browser.

When an assignment changes, say so in the `note` — the next reader needs the
reason more than the verdict.

### Relabelling, removing, adding

- **Relabel**: change the `dialect` cell. The build validates the tag against
  `names/dialects.csv` and refuses an unknown one.
- **Remove**: delete the row. Everything inside that municipality then has *no*
  dialect area, so places there lose their area-derived local name. The grey
  "not assigned" polygons in the review view are exactly this state.
- **Add**: the review view draws every Kreis Nordfriesland municipality that no
  row claims in grey. Click one — the detail block gives its
  `relation/<id>` with a copy button. Paste it into a new row, re-run the
  build, press Reload; the polygon takes the dialect's colour.

## Priority 0 — 23 municipalities lost their rows

`names/dialect_areas.geojson` (committed, and what the tiles and the search
index actually use) still covers 23 municipalities that **no CSV row claims any
more**. They show up grey in the review view. Either the rows were dropped by
mistake and should come back, or they were dropped on purpose and the committed
geojson is stale — until this is settled, `dialect_areas.csv` and
`dialect_areas.geojson` disagree about who speaks what.

Karrharde: Ladelund, Westre, Bramstedtlund, Ellhöft.
Nordergoesharde: Löwenstedt, Joldelund, Viöl, Behrendorf, Haselund, Goldelund,
Sollwitt, Goldebek, Bondelum, Kolkerheide.
Südergoesharde: Ostenfeld (Husum), Schwabstedt, Wester-Ohrstedt, Schwesing,
Immenstedt, Rantrum, Oster-Ohrstedt, Olderup, Mildstedt.

Note that the CSV's own notes cite several of these as settled: Westre is named
as a "confirmed Karrharde village" in Lexgaard's note, and Schwabstedt and
Mildstedt are the Kirchspielslandgemeinden that justify six Südergoesharde
rows. That points to rows having gone missing rather than been retired.

- [ ] Decide: restore the 23 rows, or accept the smaller areas and rebuild
      `names/dialect_areas.geojson`.

## Priority 1 — the Gotteskoog border villages

| ✓ | name | assigned | line | what to decide |
|---|---|---|---|---|
| [ ] | Holm | Mooring (Bökingharde) | 35 | on the Bökingharde/Karrharde boundary; note says best guess |
| [ ] | Uphusum | Karrharder | 52 | Karrharde/Bökingharde/Wiedingharde tripoint; note says best guess. The row already carries a **Wiedingharder** name (`Äphüsem`) in `places.csv` |
| [ ] | Lexgaard | Karrharder | 46 | enclosed by Karrharde villages, no direct source; no `karrhard` name in `places.csv` |
| [ ] | Braderup | Karrharder | 40 | no direct source, proximity only — but `places.csv` already has the Karrharder name `Braarep`. Not the Braderup on Sylt |
| [ ] | Galmsbüll | Mooring | 33 | historic Horsbüllharde = old Wiedingharde; later Amt Bökingharde. The committed geojson still has it as **Wiedingharder** |

## Priority 2 — Stedesand / Klixbüll / Bosbüll → Karrharde

| ✓ | name | assigned | line | what to decide |
|---|---|---|---|---|
| [ ] | Stedesand | Karrharder | 49 | `medium`. ISFAS sources put the living Karrharder dialect here; its hamlet **Trollebüll** has a `karrhard` name and no Mooring one — the strongest evidence in the repo. Stedesand itself has no `karrhard` name |
| [ ] | Klixbüll | Karrharder | 44 | already `high`; listed because it is the same boundary question. `places.csv` has the Karrharder `Kläsbel` |
| [ ] | Bosbüll | Karrharder | 39 | already `high`; same. No `karrhard` name in `places.csv` |

## Priority 3 — the remaining `medium` rows

The three Mittelgoesharde rows justified by "confirmed **Norder**goesharde" are
worth a second look: decision #8/#9 in `project-decisions.md` says Bohmstedt,
Drelsdorf and Ahrenshöft deliberately follow the documented Mittelgoesharder
dialect rather than historic Harde membership — check the same reasoning holds
for Almdorf, Struckum and Vollstedt.

| ✓ | name | assigned | line | note says |
|---|---|---|---|---|
| [ ] | Achtrup | Karrharder | 38 | *(bare `medium`, no reason given)* |
| [ ] | Sprakebüll | Karrharder | 47 | *(bare `medium`)* |
| [ ] | Stadum | Karrharder | 48 | *(bare `medium`)* |
| [ ] | Tinningstedt | Karrharder | 51 | *(bare `medium`)* |
| [ ] | Niebüll | Mooring | 36 | town; historic centre of the Bökingharde and of Westermooring |
| [ ] | Vollstedt | Mittelgoesharder | 61 | via former Kirchspielslandgemeinde Breklum, confirmed Nordergoesharde |
| [ ] | Struckum | Mittelgoesharder | 64 | same Breklum reason |
| [ ] | Almdorf | Mittelgoesharder | 66 | same Breklum reason |
| [ ] | Ahrenshöft | Mittelgoesharder | 67 | historic Nordergoesharde; one Kirchspiel with Bohmstedt and Drelsdorf |
| [ ] | Ahrenviölfeld | Südergoesharder | 71 | split off from Ahrenviöl / Kirchspielslandgemeinde Schwesing |
| [ ] | Fresendelf | Südergoesharder | 73 | via Kirchspielslandgemeinde Schwabstedt |
| [ ] | Hude | Südergoesharder | 77 | same Schwabstedt reason |
| [ ] | Oldersbek | Südergoesharder | 78 | via Kirchspielslandgemeinde Mildstedt |
| [ ] | Ramstedt | Südergoesharder | 79 | same Schwabstedt reason |
| [ ] | Süderhöft | Südergoesharder | 80 | Schwabstedt; sits at the transition toward Stapelholm |
| [ ] | Wisch | Südergoesharder | 83 | same Schwabstedt reason |

Five of these notes had been truncated mid-word at ~180 characters by the
research run (Galmsbüll, Holm, Stedesand, Ahrenshöft, Süderhöft) and were
trimmed back to their last complete clause on 2026-09-20. Nothing was added,
so the cut-off reasoning is simply gone — re-derive it if the row turns out to
be contentious.

## Priority 4 — the 36 `high` rows and the 25 island rows

No checklist. The overlay draws them all, so a block in the wrong colour is
visible at a glance; spot-check the Goesharde boundaries and the Hallig rows.
