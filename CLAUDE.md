# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only scanner for Minecraft 1.18+ world saves that counts every ore block at every Y level, plus two builders
that turn two scan results into an Excel workbook and a one-page infographic, and a desktop app that runs all of it.
Built for the FlowMine world (Better Adventures+, MC 1.21.11), now also checked on Minecraft 26.3 saves.
`plan.md` is the authoritative design doc (maths, test-case rules, sheet layout); `analysis.md` holds the FlowMine
findings. Keep both in sync when behaviour or numbers change.

## Commands

Run everything from the repo root: default paths (`output/test1`, `output/test2`, `output`) are relative to it.

```
python -m pip install -r requirements.txt
python tests/test_ore_scan.py          # full suite; expect "40 of 40 checks passed"
python ore_analyser_gui.py             # desktop app (CustomTkinter)
python scripts/ore_scan.py <world> --max-chunks 4000 --seed 42 --out output/test1
python scripts/build_report.py         # reads output/test1, output/test2 (+ their world_info.json)
python scripts/build_infographic.py
python scripts/build_report.py --test1 example/test1 --test2 example/test2 --out-dir example   # rebuild sample
```

There is no pytest, linter or build step. `tests/test_ore_scan.py` is a plain script that runs sequential `check()`
calls and exits non-zero on failure; there is no way to run a single check other than editing/commenting the script.
It generates synthetic worlds in a temp dir (`tests/make_world.py`, `tests/make_terrain.py`; `make_world.py --new`
writes a Minecraft 26.x save), runs the scripts as subprocesses, runs both builders on `example/`, and calls the
app's `run_pipeline` without opening a window.

## Architecture

Pipeline: `ore_scan.py` (run twice, different seeds/sizes) → CSVs + `world_info.json` in `output/test1`,
`output/test2` → `build_report.py` and `build_infographic.py`, both importing `scripts/common.py`.
`ore_analyser_gui.py` imports these scripts as modules and calls their `main(argv)` with the same arguments as the
command line; its `plan()` / `run_pipeline()` hold all non-UI logic and write to `output/<world name>/`.

- **`ore_scan.py`** decodes region files (`r.X.Z.mca`) and packed palette sections itself (via `nbtlib`), samples
  chunks evenly per region file, counts only full chunks (`Status`, or `status` from 26.4), merges host-rock
  variants (`deepslate_iron_ore` → `iron_ore`) unless `--no-merge`, and keeps modded namespaces (`create:zinc_ore`).
  Outputs `ore_summary.csv`, `ore_by_y.csv` (with `exposed` column), `layers_by_y.csv` (rock / cave-wall per Y),
  `world_info.json`, `ore_chart.png`, `cross_section.png`. Safety invariants enforced by tests: save files opened
  read-only, and `--out` inside the world folder is refused.
- **`mc_formats.py`** groups releases into save-format families (`anvil-1.18`, `dims-26.1`, `ids-26.3`): folder
  layout and seed location. Palettes are decoded by entry shape (`ore_scan.palette_name`) for every family, so
  don't branch on version numbers for decoding. `--mc-version` forces a family; otherwise the layout is detected.
  `RELEASES` is newest-first by release date and feeds both `--mc-version` choices and the app's dropdown; add new
  releases there.
- **`world_info.json`** carries the Minecraft version (and `version_source`), world seed (as text: Excel would round
  19 digits), and a `scan` block (chunks, region files, skipped, sample seed, max chunks, date, slice).
  `common.parse_args` fills every builder option from it; CLI options override. There is deliberately no seed
  option. `example/test*/world_info.json` were written by hand for scans older than this file.
- **`common.py`** is the single source for shared facts: `MINING` (mining-speed assumptions), `LIMITS` (test-case
  pass limits), ore names/colours, CLI args, CSV loading, and derived facts/tips (`facts`, `tips`, `mining`). All
  numbers that appear in text are computed here so the workbook and infographic always agree — put new derived
  values here, not in one builder.
- **Builders** keep all code inside `main(argv=None)`, which returns the saved path; helpers are nested functions
  (closures over the parsed args). Close matplotlib figures: `main()` runs repeatedly inside the app.
- **`build_report.py`** writes a formula-driven workbook (~29k formulas): raw CSVs go into input sheets, every other
  sheet computes via SUMIFS / INDEX-MATCH. Don't paste computed values into cells. Colour convention: blue = raw
  input, green = cross-sheet link, black = calculated, yellow = editable (`MINING` and `LIMITS` appear as yellow
  cells). World Details rows are referenced by address (`B9`, `B11`, `B13`, ...): append new rows at the end. The
  file stores no cached results; Excel calculates on open.
- **Estimate vs exact mode:** if `layers_by_y.csv` is missing (old scanner), `common.load_layers` treats every block
  position as rock and cave odds show "rescan needed". `example/test1` was made by the old scanner; this is
  expected. Both modes must keep working (tested).

## Conventions

- `output/` is gitignored (local results). The committed FlowMine sample, also used by the README image and the
  tests, is in `example/`.
- User-facing text (README, plan, workbook, infographic, app) is written in plain language for non-technical players.
- README carries an AI-generated-project disclosure; keep it.
