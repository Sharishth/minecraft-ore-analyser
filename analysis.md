# FlowMine ore analysis

World: FlowMine | Modpack: Better Adventures+ (Flowstate, latest) | Minecraft 1.21.11 | Dimension: Overworld
Scanned: 26 Oct 2026 with `scripts/ore_scan.py`

## Summary

- **Strip mining beats caves for every ore that could be measured.** For diamonds, strip mining at Y -58 gives 3.0x better odds per block
  than cave walls (1 in 481 against 1 in 1,437), because the game often skips diamonds that would touch air.
- **Ore placement follows vanilla 1.18+ rules, with one exception:** about 6.2% of coal spawns below Y 0, which
  vanilla never does.
- **Best overall layer:** Y -59 to -56 sits inside the best band for both diamond and redstone.
- **Peaks are lower than vanilla charts show.** Vanilla charts give the spawn chance per block; these numbers count
  ore that actually exists. The pack's terrain has less rock high up, so less ore exists there.
- **Mountains hold a lot of ore:** 12.6% of all iron and 10.5% of all coal are inside mountains, and all emerald is
  in mountain biomes.
- **The two scans agree closely:** ore per chunk is within 2.6% for every ore, and every median Y is within 1 block.
  34 of 36 stability checks pass.

## Scans

| | Test 1 | Test 2 |
|---|---|---|
| Command option `--max-chunks` | 4,000 | 20,000 |
| Seed | 42 | 7 |
| Full chunks scanned | 3,792 | 18,960 |
| Unfinished chunks skipped | 13,081 | 17,349 (rescan) |
| Region files in world | 1,382 | 1,382 |
| Ore blocks counted | 1,370,499 | 6,875,201 |
| Cross-section | not drawn | Z 2568, X 7168 to 8191 |

1,382 region files cover at most about 362 km2 of map (not every chunk inside them is generated).

## Where to mine (Test 2)

| Ore | Best 5-layer band | Best single layer | Median | 80% of it between | Found from / to | Ore blocks per chunk |
|---|---|---|---|---|---|---|
| Emerald | Y 162 to 166 | 155 | 171 | 91 to 220 | 16 to 286 | 0.23 |
| Coal | Y 40 to 44 | 41 | 57 | 10 to 137 | -35 to 298 | 119.32 |
| Copper | Y 35 to 39 | 39 | 33 | 3 to 65 | -19 to 170 | 66.16 |
| Iron | Y 12 to 16 | 15 | 12 | -25 to 111 | -63 to 293 | 74.41 |
| Lapis Lazuli | Y -5 to -1 | -3 | -5 | -46 to 31 | -63 to 242 | 21.39 |
| Gold | Y -19 to -15 | -17 | -19 | -51 to 11 | -63 to 222 | 24.94 |
| Diamond | Y -59 to -55 | -59 | -36 | -57 to -10 | -63 to 244 | 22.09 |
| Redstone | Y -60 to -56 | -59 | -45 | -59 to -2 | -63 to 290 | 34.08 |

How flat each band's top is (layers within 10% of the best layer, after smoothing):

| Ore | Flat top | Meaning |
|---|---|---|
| Copper | Y 21 to 45 | Very flat: any layer in this range is nearly as good |
| Coal | Y 29 to 52 | Very flat |
| Emerald | Y 157 to 175 | Wide, and the data is noisy because emerald is rare |
| Gold | Y -23 to -12 | Moderate |
| Lapis Lazuli | Y -9 to 2 | Moderate |
| Iron | Y 8 to 18 | Moderate |
| Diamond | Y -59 to -54 | Sharp: mine just above bedrock |
| Redstone | Y -59 to -55 | Sharp |

## Findings

### 1. Vanilla rules hold for most ores

| Check | Share outside vanilla range | Result |
|---|---|---|
| Redstone above Y 16 | 0.022% (141 blocks) | Matches vanilla |
| Lapis above Y 64 | 0.001% (4 blocks) | Matches vanilla |
| Diamond above Y 16 | 0.0005% (2 blocks) | Matches vanilla |
| Copper above Y 112 | 0.022% (280 blocks) | Matches vanilla |
| Iron in the Y 73 to 77 gap | 0.003% | Matches vanilla |
| Coal below Y 0 | 6.17% | **Differs from vanilla** |

The few blocks outside the vanilla ranges (for example diamond at Y 244 and redstone up to Y 290) are too rare to
mine for. They most likely come from structures or floating-island features, not normal ore generation.

### 2. Peaks are lower than published vanilla charts

Vanilla charts show the chance of ore per block of rock. This scan counts the ore that actually exists, so a layer
with more rock holds more ore. Above sea level much of each layer is air, which pulls the peaks down:

| Ore | Vanilla peak (spawn rule) | FlowMine best band |
|---|---|---|
| Coal (lower band) | about Y 96 | Y 40 to 44 |
| Copper | about Y 48 | Y 35 to 39 |
| Iron (mountain band) | about Y 232 | most of it Y 100 to 180 |
| Emerald | about Y 232 | Y 162 to 166 |

Deep ores (diamond, redstone, gold, lapis) are almost always surrounded by rock, so they match vanilla closely.

### 3. Mountains and badlands add ore high up

- 12.6% of iron is at Y 80 or higher (vanilla's mountain iron band).
- 10.5% of coal is at Y 136 or higher (vanilla's upper coal band).
- 3.7% of gold is above Y 32, the extra gold that badlands biomes add.
- The Test 2 cross-section shows a tall terracotta mountain reaching about Y 290, which explains how high these
  bands go.

### 4. The two scans agree

| Ore | Test 1 per chunk | Test 2 per chunk | Difference | Median diff | Best layer diff |
|---|---|---|---|---|---|
| Coal | 119.48 | 119.32 | 0.14% | 1 | 3 |
| Iron | 73.49 | 74.41 | 1.24% | 0 | 0 |
| Copper | 65.81 | 66.16 | 0.53% | 0 | **8** |
| Redstone | 33.89 | 34.08 | 0.56% | 0 | 0 |
| Gold | 25.08 | 24.94 | 0.55% | 0 | 0 |
| Diamond | 22.05 | 22.09 | 0.20% | 0 | 2 |
| Lapis Lazuli | 21.39 | 21.39 | 0.00% | 1 | 0 |
| Emerald | 0.22 | 0.23 | 2.64% | 1 | **27** |

The two failed checks are the best single layer for copper and emerald. Copper's band is flat across about 25
layers, so the top layer moves between samples. Emerald is rare (850 blocks in Test 1), so its single best layer
is noisy. Their medians, 80% bands and amounts all pass. Use the 5-layer band, not the single best layer, for
these two ores.

## Mining odds (strip mining vs caves)

Exact figures from the Test 2 rescan, which counted rock, cave-wall blocks and ore visible from caves on every
layer (the rescan's ore counts are identical to the first Test 2, as expected with the same seed). Pace: 20 tunnel
blocks a minute in stone, 12 in deepslate, and 150 cave-wall blocks looked at a minute in caves. A height only
counts if its window holds at least 30 ore blocks and 10% of the ore's best window.

| Ore | Strip: tunnel at Y (feet) | Strip: chance per block | Strip: ore per hour | Caves: best band from Y | Caves: chance per wall block | Caves: ore per hour | Visible from caves | Average chance per rock block |
|---|---|---|---|---|---|---|---|---|
| Emerald | 214 (inside mountains) | 1 in 2,886 | 3.3 | too few seen | - | - | 2.6% | 1 in 128,937 |
| Coal | 136 (inside mountains) | 1 in 53 | 181 | 141 | 1 in 205 | 44 | 2.0% | 1 in 249 |
| Copper | 43 | 1 in 137 | 70 | 37 | 1 in 255 | 35 | 3.2% | 1 in 448 |
| Iron | 14 | 1 in 155 | 62 | 12 | 1 in 252 | 36 | 3.2% | 1 in 399 |
| Lapis Lazuli | -3 | 1 in 611 | 9.4 | -5 | 1 in 1,327 | 6.8 | 1.9% | 1 in 1,387 |
| Gold | -18 | 1 in 496 | 11.6 | -21 | 1 in 961 | 9.4 | 2.1% | 1 in 1,189 |
| Diamond | -58 | 1 in 481 | 12.0 | -29 | 1 in 1,437 | 6.3 | 1.5% | 1 in 1,343 |
| Redstone | -59 | 1 in 194 | 29.6 | -58 | 1 in 330 | 27.3 | 2.5% | 1 in 870 |

What this shows:

- **Strip mining beats caves for every measured ore, per block looked at** (emerald is too rarely visible to measure). The gap is largest for diamond (3.0x) and lapis
  (2.2x). Vanilla skips some diamond and lapis placements that would touch air, and the data shows it: only 1.5% of
  diamonds are visible from a cave.
- **Coal and emerald are densest inside mountains.** Coal reaches 1 in 53 rock blocks at Y 136 to 139 in
  mountains, against about 1 in 129 at its main band (Y 40). There is less mountain rock, so the main band still
  holds more coal in total (see "Where to mine").
- **Strip-mine heights differ slightly from the "Where to mine" bands.** "Where to mine" finds where the most ore
  exists. The mining odds find where each block you dig is most likely to be ore. For deep ores the two agree
  within 1 to 2 blocks. For copper the odds favour Y 43, probably because there is less rock there (more caves and water), so each rock block is richer.
- **Ore per hour:** a steady strip mine at Y -58 gives about 12 diamond blocks an hour at the assumed pace. Caves
  give fewer diamonds per wall block, but exploring covers ground faster. Change the pace on the Mining Odds sheet
  to match how you play.
- **Ores come in veins,** so mining out each vein you find usually gives a little more than these figures.

## Test case results (42 checks)

| Result | Count |
|---|---|
| PASS | 34 |
| FAIL | 2 (best single layer: copper, emerald) |
| MATCHES VANILLA | 5 |
| DIFFERS FROM VANILLA | 1 (coal below Y 0) |

Full detail is on the Test Cases sheet of `example/FlowMine_Ore_Report.xlsx`.

## Scanner verification (tests/test_ore_scan.py)

All checks pass (40 at the time of writing), including:

- exact ore counts on two synthetic worlds with known ore placement
- unfinished chunks skipped
- modded ore names kept (`create:zinc_ore`)
- rock, cave-wall and visible-ore counts exact on a synthetic world with caves and water
- world files byte-for-byte unchanged after scanning
- output inside the world folder refused

## Limits

- Areas the player already mined have less ore, so per-chunk amounts are slightly low.
- No modded ore types were found. A mod ore whose block id does not end in `_ore` would be missed (see `--pattern`).
- Cave odds use visible ore per cave-wall block. Neighbours in other chunks are not checked, so visibility is very
  slightly under-counted at chunk edges.
- Per-hour figures depend on the assumed pace; they are a guide, not a guarantee.
