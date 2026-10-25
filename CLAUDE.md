# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only scanner for Minecraft 1.18+ world saves that counts every ore block at every Y level, plus two builders
that turn two scan results into an Excel workbook and a one-page infographic. Built for the FlowMine world
(Better Adventures+, MC 1.21.11). `plan.md` is the authoritative design doc (maths, test-case rules, sheet layout);
`analysis.md` holds the FlowMine findings. Keep both in sync when behaviour or numbers change.

## Commands

Run everything from the repo root: default paths (`output/test1`, `output/test2`, `output`) are relative to it.

```
python -m pip install -r requirements.txt
python tests/test_ore_scan.py          # full suite; expect "20 of 20 checks passed"
python scripts/ore_scan.py <world> --max-chunks 4000 --seed 42 --out output/test1
python scripts/build_report.py         # no args = rebuild FlowMine report from output/test1, output/test2
python scripts/build_infographic.py
python scripts/build_report.py --help  # all builder options (shared via common.parse_args)
```

There is no pytest, linter or build step. `tests/test_ore_scan.py` is a plain script that runs sequential `check()`
calls and exits non-zero on failure; there is no way to run a single check other than editing/commenting the script.
It generates synthetic worlds in a temp dir (`tests/make_world.py`, `tests/make_terrain.py`), invokes the scripts as
subprocesses, and also runs both builders against the bundled `output/` data, writing to a temp `--out-dir`.

## Architecture

Pipeline: `ore_scan.py` (run twice, different seeds/sizes) → CSVs in `output/test1`, `output/test2` →
`build_report.py` and `build_infographic.py`, both importing `scripts/common.py`.

- **`ore_scan.py`** decodes region files (`r.X.Z.mca`) and packed palette sections itself (via `nbtlib`), samples
  chunks evenly per region file, counts only `minecraft:full` chunks, merges host-rock variants
  (`deepslate_iron_ore` → `iron_ore`) unless `--no-merge`, and keeps modded namespaces (`create:zinc_ore`).
  Outputs `ore_summary.csv`, `ore_by_y.csv` (with `exposed` column), `layers_by_y.csv` (rock / cave-wall per Y),
  `ore_chart.png`, `cross_section.png`. Safety invariants enforced by tests: region files opened read-only, and
  `--out` inside the world folder is refused.
- **`common.py`** is the single source for shared facts: `MINING` (mining-speed assumptions), `LIMITS` (test-case
  pass limits), ore names/colours, CLI args, CSV loading, and derived facts/tips (`facts`, `tips`, `mining`). All
  numbers that appear in text are computed here so the workbook and infographic always agree — put new derived
  values here, not in one builder.
- **Builders are top-level scripts** (no `main()`); they parse args and do all work at import time. Their CLI
  defaults hard-code the FlowMine scan values (chunk counts, regions, skipped, slice, date).
- **`build_report.py`** writes a formula-driven workbook (~29k formulas): raw CSVs go into input sheets, every other
  sheet computes via SUMIFS / INDEX-MATCH. Don't paste computed values into cells. Colour convention: blue = raw
  input, green = cross-sheet link, black = calculated, yellow = editable (`MINING` and `LIMITS` appear as yellow
  cells). The file stores no cached results; Excel calculates on open.
- **Estimate vs exact mode:** if `output/test2/layers_by_y.csv` is missing (old scanner), `common.load_layers`
  treats every block position as rock and cave odds show "rescan needed". `output/test1` was made by the old
  scanner, so it has no `layers_by_y.csv`; this is expected. Both modes must keep working (tested).

## Conventions

- `output/test1`, `output/test2` and the FlowMine report/infographic are committed deliverables; `output/scan/`
  (the scanner's default `--out`) is gitignored scratch.
- User-facing text (README, plan, workbook, infographic) is written in plain language for non-technical players.
- README carries an AI-generated-project disclosure; keep it.
