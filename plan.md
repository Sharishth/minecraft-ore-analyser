# Minecraft Ore Analyser: plan and how it works

Measures where ores actually spawn in a modded Minecraft world by reading the save's real blocks, then turns the
results into an Excel report and a one-page infographic that any player can read.

Built for the **FlowMine** world (Better Adventures+ by Flowstate, Minecraft 1.21.11), where published ore charts
don't apply because the pack uses custom terrain and floating islands.

## 1. Goal

| Question | Answer produced |
|---|---|
| What is the best Y level to mine each ore in *this* world? | Best 5-layer band per ore |
| How common is each ore? | Ore blocks per chunk |
| Does the pack change vanilla ore rules? | Vanilla-rule test cases |
| What are my odds strip mining vs exploring caves, and how much per hour? | Mining Odds sheet and infographic panel |
| Can the numbers be trusted? | Two independent scans compared by 36 stability test cases |

## 2. Pipeline

```
Minecraft save (read-only)
   |
   |  scripts/ore_scan.py   (run twice: Test 1 small sample, Test 2 large sample)
   v
output/test1/  ore_summary.csv, ore_by_y.csv, layers_by_y.csv, ore_chart.png, cross_section.png
output/test2/  ore_summary.csv, ore_by_y.csv, layers_by_y.csv, ore_chart.png, cross_section.png
   |
   |  scripts/build_report.py        scripts/build_infographic.py
   |        (both use scripts/common.py for shared rules and text)
   v
output/FlowMine_Ore_Report.xlsx     output/FlowMine_Ore_Infographic.png
```

## 3. Folder layout

```
minecraft-ore-analyser/
  README.md                overview, quick start, AI disclosure
  .gitignore
  plan.md                  this file
  analysis.md              findings for FlowMine
  requirements.txt         Python packages
  scripts/
    ore_scan.py            world scanner (reads region files, never writes to the save)
    common.py              shared settings, test limits, mining assumptions, derived facts, tip text
    build_report.py        Excel workbook builder
    build_infographic.py   infographic builder
  tests/
    test_ore_scan.py       automated checks (20 checks)
    make_world.py          synthetic world: simple, known ore counts
    make_terrain.py        synthetic world: terrain, caves, water, floating island
  output/                  everything generated lives here
    test1/                 Test 1 scan output (3,792 chunks, seed 42)
    test2/                 Test 2 scan output (18,960 chunks, seed 7)
    FlowMine_Ore_Report.xlsx
    FlowMine_Ore_Infographic.png
```

## 4. How to run (Windows PowerShell)

### 4.1 Install

```
python -m pip install -r requirements.txt
```

Python 3.9 or newer.

### 4.2 Scan the world

Close the world in Minecraft first (or copy the save folder and scan the copy).

```
$WORLD = "C:\Users\Shari\AppData\Roaming\ModrinthApp\profiles\Better Adventures+\saves\FlowMine"

# Test 1: quick sample
python scripts/ore_scan.py $WORLD --dim overworld --max-chunks 4000 --seed 42 --out output/test1

# Test 2: large, independent sample with a wider cross-section
python scripts/ore_scan.py $WORLD --dim overworld --max-chunks 20000 --seed 7 --slice-width 1024 --out output/test2
```

Write down the console lines `scanned N full chunks from R region files` and `skipped_not_fully_generated: S`
for both runs. They feed the report.

Other dimensions: `--dim nether`, `--dim end`, or a modded `--dim modid:name`.
Pick the cross-section yourself with `--slice-x` and `--slice-z` (F3 coordinates).

### 4.3 Build the report and infographic

```
python scripts/build_report.py --chunks1 3792 --chunks2 18960 --regions 1382 --skipped1 13081 --skipped2 17349
python scripts/build_infographic.py --chunks1 3792 --chunks2 18960 --regions 1382
```

The defaults already hold the FlowMine values, so for this world both commands also work with no options.
For another world, also pass `--world`, `--modpack`, `--mc-version`, `--slice` and `--scan-date`.
Run `python scripts/build_report.py --help` for the full list.

### 4.4 Run the tests

```
python tests/test_ore_scan.py
```

Expected result: `20 of 20 checks passed`.

## 5. How the scanner works (`ore_scan.py`)

1. **Find region files.** Each `r.X.Z.mca` file holds up to 32 x 32 chunks (512 x 512 blocks).
2. **Sample chunks evenly.** It takes `max-chunks / region files` chunks from each file, in random order inside the
   file, so the sample spreads over the whole world instead of one area. `--seed` makes the sample repeatable.
3. **Skip unfinished chunks.** Only chunks with status `minecraft:full` are counted. Unfinished chunks have no ores
   placed yet and would make ore look rarer.
4. **Decode blocks.** Each 16 x 16 x 16 section stores a palette plus packed indices. With `b` bits per block,
   one 64-bit number holds `64 / b` blocks (rounded down). Block `i` is in number `i / per`, slot `i mod per`.
   Height inside the section is `i / 256`.
5. **Count ores per Y.** Any block id ending in `_ore` (plus ancient debris) counts. Deepslate and other rock
   variants merge into one name (`deepslate_iron_ore` becomes `iron_ore`). Modded ores keep their namespace.
6. **Summarise.** For each ore: total, per chunk, peak Y, median Y, 10th and 90th percentile Y, min and max Y.
7. **Rock, cave walls, visible ore.** Every chunk is decoded into a full block grid. Per Y it counts rock (anything
   you can mine), cave-wall blocks (rock touching air or water) and ore blocks touching air or water (visible from
   a cave, ravine or cliff). Neighbours in other chunks are not checked, so exposure is very slightly under-counted
   at chunk edges. Written to `layers_by_y.csv` and the `exposed` column of `ore_by_y.csv`.
8. **Cross-section.** Reads one row of full chunks and colours every block by type to draw a real slice of the world.

**Safety:** region files are only opened in read-only mode, and the script refuses an `--out` folder inside the
world. The tests confirm both: they hash every world file before and after a scan.

## 6. Maths used in the report

| Measure | Definition | Why |
|---|---|---|
| Ore blocks per chunk | total / chunks scanned | Compares runs of different sizes |
| Peak (best single layer) | Y with the highest count | Quick answer, but noisy for flat or rare bands |
| Best 5-layer band | 5 consecutive Y levels with the highest total | Most reliable place for a branch mine |
| Median Y | Y with half the ore below and half above (running total reaches 50%) | Robust centre of the band |
| Main band (p10 to p90) | Running total reaches 10% and 90% | Where 80% of the ore is |
| Share of ore at Y | count at Y / ore total | Shape of each ore's distribution |
| Flat top | Layers within 10% of the best layer after 5-layer smoothing | Shows when any of several layers works |
| Stray share | Share of an ore outside its vanilla height range | Detects pack changes vs structures |
| Chance per rock block at Y | ore at Y / rock at Y | Odds for one block you mine |
| Strip value at feet Y | 3 x chance(Y) + 3 x chance(Y+1) + chance(Y-1) + chance(Y+2) | Ore seen per block of a 1x2 tunnel |
| Cave chance (5 layers) | visible ore / cave-wall blocks over Y to Y+4 | Odds for one cave-wall block you look at |
| Ore per hour | value per step x pace per minute x 60 | Expected haul at your mining speed |

## 7. Mining odds model

**Strip mining.** A 1 wide, 2 tall tunnel with your feet at Y. Each block forward you mine 2 blocks (Y and Y+1) and
can see 6 more: 2 wall blocks on each side, the floor (Y-1) and the ceiling (Y+2). That is 8 blocks checked per
step. Ore seen per step is the sum of the ore chance over those 8 blocks. The best tunnel height is the Y with the
highest value.

**Caves.** While exploring you see cave-wall blocks. The chance that a wall block is an ore comes from the scanner's
visible-ore and wall counts, over the best 5-layer band. Some ores are placed less often next to air (vanilla
"air exposure" rules), so caves can be worse than strip mining for them. The data shows this directly.

**Per hour.** Assumptions in `common.MINING`, editable on the Mining Odds sheet:

| Setting | Default | Meaning |
|---|---|---|
| Tunnel blocks per minute in stone | 20 | Efficiency pickaxe, including torches and walking |
| Tunnel blocks per minute in deepslate | 12 | Deepslate takes about twice as long |
| Cave wall blocks looked at per minute | 150 | Rough guess |
| Blocks checked per tunnel block | 8 | From the tunnel shape above |

**Minimum sample.** A height only counts if its window (Y-1 to Y+2 for strip mining, Y to Y+4 for caves) holds at
least 30 ore blocks and at least 10% of that ore's best window. Without this, a mountain peak with 3 ore blocks in
a few hundred rock blocks would "win". Both limits are inputs on the Mining Odds sheet (`common.MINING`).

**Estimate mode.** Scans made before the scanner counted rock (no `layers_by_y.csv`) still work: every sampled block
position is treated as rock, which gives a lower bound for the strip odds, and cave odds show "rescan needed".

## 8. Test cases

Two scans with different seeds and sizes act as independent samples. If they agree, the numbers are trustworthy.
All pass limits live in `common.LIMITS` and appear as yellow, editable cells on the Test Cases sheet.

| Group | Rule | Limit |
|---|---|---|
| Sample size | Test 1 chunks | at least 3,000 |
| Sample size | Test 2 chunks | at least 15,000 |
| Sample size | Test 2 / Test 1 | at least 4x |
| Coverage | Same ore types in both tests | equal |
| Stability (per ore) | Ore per chunk difference | within 5% |
| Stability (per ore) | Median Y difference | within 3 blocks |
| Stability (per ore) | p10 and p90 difference | within 5 blocks |
| Stability (per ore) | Best single layer difference | within 5 blocks |
| Vanilla rules | Share outside vanilla range (redstone, lapis, diamond, copper, iron gap, coal) | at most 0.1% |

Result labels: PASS / FAIL for stability, MATCHES VANILLA / DIFFERS FROM VANILLA for vanilla rules.

## 9. Excel workbook design (`build_report.py`)

| Sheet | Purpose | Driven by |
|---|---|---|
| Start Here | Plain-language guide, quick answer, colour key | Text from `common.py` |
| Mining Guide | Best Y per ore, tips, bar chart | Formulas on Test2 Summary and Where Ore Spawns |
| Mining Odds | Strip vs cave chance, best tunnel Y, ore per hour, editable pace, chart | Mining Calc |
| Layer Lookup | Type a Y level, see ores at that layer, chart updates | SUMIFS on Test2 Data |
| Ore Charts | One chart per ore, Y vertical like in game | Where Ore Spawns |
| Where Ore Spawns | Count, share and 5-layer sum for every Y | SUMIFS on Test2 Data |
| Mining Calc | Chance, strip value, visible ore and cave chance for every Y | Where Ore Spawns, Test2 Layers |
| Test Cases | 42 checks with editable limits | Formulas on Test Comparison and Test2 Data |
| Test Comparison | Test 1 vs Test 2 side by side, two charts | INDEX/MATCH on both summaries |
| World Details | World facts and scan settings | Inputs plus formulas |
| Test1/Test2 Summary, Data, Test2 Layers | Raw scanner CSVs | Inputs (blue text) |

Rules followed: formulas instead of pasted results (about 29,000 formulas, zero errors), blue = raw input,
green = linked from another sheet, black = calculated, yellow = editable. The file is set to recalculate fully when
opened in Excel.

## 10. Infographic design (`build_infographic.py`)

- Header with world, modpack, version and dimension.
- Five headline tiles: chunks scanned, ore blocks counted, ore per chunk, region files, ore types.
- Main panel: each ore's spawn shape drawn over the real cross-section of the world, with the best band marked.
- Ore cards ordered by height (highest at top, like the world): best band, 80% range, ore per chunk bar.
- Pro tips chosen from the data (two-for-one layer, mountains, badlands gold, pack differences, rarest ore).
- Mining odds table: strip mine vs caves, chance per block, ore per 100 tunnel blocks, ore per hour.
- Trust panel with the test results.
- Ore colours match the in-game ore colours so players recognise them, and every colour also has a text label.

## 11. Known limits

- Chunks the player has mined contain less ore, so totals are slightly low. For clean data, pregenerate a fresh area
  (for example with the Chunky mod) on a copy of the world.
- Only block ids ending in `_ore` count by default. Use `--pattern` for mods that name ores differently.
- LZ4-compressed region files (an optional 1.20.5+ server setting) are skipped and reported.
- "Where to mine" uses total ore per layer. The Mining Odds use ore per rock block, which is exact only after a
  rescan with the current scanner (see estimate mode).
- Test 1 was made with the first scanner version, so it has no rock or cave-wall counts (Test 2 does).

## 12. Possible next steps

1. Rescan Test 1 with the current scanner too, so its rock and cave numbers can be compared with Test 2.
2. Scan the Nether and End and add them as extra sheets.
3. Add a per-biome breakdown (needs biome data from the chunk NBT).
4. Measure vein sizes, so "ore per hour" can count whole veins instead of visible blocks.
