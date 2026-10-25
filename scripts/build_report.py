"""Build the ore report workbook (Excel) from two ore_scan.py result sets.

Usage (from the project folder):
    python scripts/build_report.py --test1 output/test1 --test2 output/test2 --chunks1 3792 --chunks2 18960

Every table and chart in the workbook is driven by formulas that read the raw CSV sheets,
so the workbook recalculates in Excel if the raw data is changed.
"""
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import ScatterChart, BarChart, Reference, Series
from openpyxl.chart.series import DataPoint
from openpyxl.formatting.rule import CellIsRule
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter as L
from openpyxl.comments import Comment

import common

A = common.parse_args("Build the Excel ore report")
S1, D1, S2, D2 = common.load(A)
F = common.facts(A, S1, S2, D2)

ORES = list(S2.ore)  # ordered by abundance in Test 2
NICE = {o: common.nice(o) for o in set(S1.ore) | set(S2.ore)}
COLOR = {o: common.color(o, i).lstrip("#").upper() for i, o in enumerate(ORES)}
DARK_TEXT = common.DARK_TEXT
TIPS = common.tips(F, S2)
DEPTH_ORDER = sorted(ORES, key=lambda o: F["best"][o])
FONT = "Arial"
f_norm = Font(name=FONT, size=10)
f_bold = Font(name=FONT, size=10, bold=True)
f_title = Font(name=FONT, size=16, bold=True)
f_sub = Font(name=FONT, size=11, italic=True, color="555555")
f_head = Font(name=FONT, size=10, bold=True, color="FFFFFF")
f_input = Font(name=FONT, size=10, color="0000FF")
f_link = Font(name=FONT, size=10, color="008000")
fill_head = PatternFill("solid", fgColor="3B4A5A")
fill_input = PatternFill("solid", fgColor="FFFF00")
fill_band = PatternFill("solid", fgColor="F2F4F7")
thin = Side(style="thin", color="C8CDD3")
box = Border(left=thin, right=thin, top=thin, bottom=thin)
center = Alignment(horizontal="center", vertical="center", wrap_text=True)
wrap = Alignment(vertical="top", wrap_text=True)

wb = Workbook()


def style_all(ws):
    for row in ws.iter_rows():
        for c in row:
            if c.font is None or c.font.name != FONT:
                c.font = Font(name=FONT, size=c.font.size if c.font else 10, bold=c.font.bold,
                              italic=c.font.italic, color=c.font.color)


def header(ws, row, labels, col=1):
    for i, t in enumerate(labels):
        c = ws.cell(row=row, column=col + i, value=t)
        c.font, c.fill, c.alignment, c.border = f_head, fill_head, center, box


def title(ws, text, sub=None):
    ws["A1"] = text
    ws["A1"].font = f_title
    if sub:
        ws["A2"] = sub
        ws["A2"].font = f_sub


def ore_cell(c, ore):
    c.value = NICE[ore]
    c.fill = PatternFill("solid", fgColor=COLOR[ore])
    c.font = Font(name=FONT, size=10, bold=True, color="000000" if ore in DARK_TEXT else "FFFFFF")
    c.border = box
    c.alignment = Alignment(vertical="center")


# ---------------- raw data sheets ----------------
def raw_sheets(tag, S, D):
    ws = wb.create_sheet(f"{tag} Summary")
    title(ws, f"{tag} raw summary", "Copied from ore_summary.csv produced by ore_scan.py. Blue = raw input.")
    cols = ["ore", "total", "per_chunk", "peak_y", "median_y", "p10_y", "p90_y", "min_y", "max_y"]
    header(ws, 4, cols)
    for r, rec in enumerate(S[cols].itertuples(index=False), start=5):
        for c, v in enumerate(rec, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font, cell.border = f_input, box
    for i, w in enumerate([16, 12, 11, 9, 10, 9, 9, 9, 9], start=1):
        ws.column_dimensions[L(i)].width = w
    ws.freeze_panes = "A5"
    wd = wb.create_sheet(f"{tag} Data")
    title(wd, f"{tag} ore count per Y level", "Copied from ore_by_y.csv. One row per ore per Y level. Blue = raw input.")
    dcols = ["ore", "y", "count", "exposed"]
    header(wd, 4, dcols)
    for r, rec in enumerate(D[dcols].itertuples(index=False), start=5):
        for c, v in enumerate(rec, start=1):
            cell = wd.cell(row=r, column=c, value=v)
            cell.font = f_input
    for i, w in enumerate([16, 8, 10, 10], start=1):
        wd.column_dimensions[L(i)].width = w
    wd.freeze_panes = "A5"
    return ws, wd, 5 + len(S) - 1, 5 + len(D) - 1


# Sheet order is set at the end
start = wb.active
start.title = "Start Here"
guide = wb.create_sheet("Mining Guide")
spawn = wb.create_sheet("Where Ore Spawns")
charts = wb.create_sheet("Ore Charts")
lookup = wb.create_sheet("Layer Lookup")
comp = wb.create_sheet("Test Comparison")
tests = wb.create_sheet("Test Cases")
world = wb.create_sheet("World Details")
t1s, t1d, t1s_end, t1d_end = raw_sheets("Test1", S1, D1)
t2s, t2d, t2s_end, t2d_end = raw_sheets("Test2", S2, D2)
T1S, T2S = "'Test1 Summary'", "'Test2 Summary'"
T1D, T2D = "'Test1 Data'", "'Test2 Data'"
S1R = f"$A$5:$A${t1s_end}"
S2R = f"$A$5:$A${t2s_end}"
D2A, D2B, D2C = f"{T2D}!$A$5:$A${t2d_end}", f"{T2D}!$B$5:$B${t2d_end}", f"{T2D}!$C$5:$C${t2d_end}"
D2E = f"{T2D}!$D$5:$D${t2d_end}"

# Rock and cave-wall counts per Y (exact from scanner v2, otherwise an estimate)
LAYERS, LAYERS_EXACT = common.load_layers(A, D2)
lay = wb.create_sheet("Test2 Layers")
title(lay, "Test2 rock and cave-wall blocks per Y level",
      "Copied from layers_by_y.csv. rock = blocks you can mine. wall = rock touching air or water (what you see "
      "in caves). Blue = raw input." if LAYERS_EXACT else
      "ESTIMATE: this scan has no layers_by_y.csv, so every sampled block position is treated as rock and cave "
      "walls are unknown. Rerun ore_scan.py (v2) on the world for exact values.")
header(lay, 4, ["y", "positions", "rock", "wall"])
for r, rec in enumerate(LAYERS[["y", "positions", "rock", "wall"]].itertuples(index=False), start=5):
    for c, v in enumerate(rec, start=1):
        lay.cell(row=r, column=c, value=int(v)).font = f_input
lay_end = 5 + len(LAYERS) - 1
for i, w in enumerate([8, 12, 12, 12], start=1):
    lay.column_dimensions[L(i)].width = w
lay.freeze_panes = "A5"
TL = "'Test2 Layers'"
LY, LP, LR, LW = (f"{TL}!${c}$5:${c}${lay_end}" for c in "ABCD")


def sum_lookup(sheet, col_letter, ore_ref, rng):
    return f"INDEX({sheet}!${col_letter}$5:${col_letter}${rng},MATCH({ore_ref},{sheet}!$A$5:$A${rng},0))"


# ---------------- World Details ----------------
title(world, "World details", "Facts about the world and the two scans. Blue cells are inputs you can change.")
header(world, 4, ["Item", "Value", "Notes"])
W = [
    ("World name", A.world, "Save folder name", True),
    ("Modpack", A.modpack, "Provided by the player", True),
    ("Minecraft version", A.mc_version, "Provided by the player", True),
    ("Dimension scanned", A.dimension, "", True),
    ("Region files in world", A.regions, "Printed by ore_scan.py. Each region file covers 512 x 512 blocks", True),
    ("Max area covered by region files (km2)", "=B9*512*512/1000000", "Upper bound: not every chunk inside a region file is generated", False),
    ("Test 1 chunks scanned", A.chunks1, f"Printed by ore_scan.py (run with --max-chunks {A.max1}, seed {A.seed1})", True),
    ("Test 1 unfinished chunks skipped", int(A.skipped1) if A.skipped1.isdigit() else A.skipped1, "Printed by ore_scan.py. Chunks the game had not finished generating", True),
    ("Test 2 chunks scanned", A.chunks2, f"Printed by ore_scan.py (run with --max-chunks {A.max2}, seed {A.seed2})", True),
    ("Test 2 unfinished chunks skipped", int(A.skipped2) if A.skipped2.isdigit() else A.skipped2, "Printed by ore_scan.py", True),
    ("Ore types found", f"=COUNTA({T2S}!{S2R})", "Distinct ores found in Test 2", False),
    ("Total ore blocks counted (Test 2)", f"=SUM({T2S}!$B$5:$B${t2s_end})", "", False),
    ("Ore blocks per chunk, all ores (Test 2)", "=B16/B13", "", False),
    ("Lowest ore found (Y)", f"=MIN({T2S}!$H$5:$H${t2s_end})", "Bottom of the world is Y -64 (bedrock)", False),
    ("Highest ore found (Y)", f"=MAX({T2S}!$I$5:$I${t2s_end})", "Top of the world is Y 319", False),
    ("Rock and cave-wall data", "Exact (layers_by_y.csv)" if common.load_layers(A, D2)[1] else
     "Estimate (no layers_by_y.csv)", "Needed for the Mining Odds sheet", False),
    ("Cross-section location", A.slice, "Slice drawn by ore_scan.py, shown in the infographic", True),
]
for r, (k, v, n, is_input) in enumerate(W, start=5):
    world.cell(row=r, column=1, value=k).font = f_bold
    c = world.cell(row=r, column=2, value=v)
    c.font = f_input if is_input else f_norm
    world.cell(row=r, column=3, value=n).font = f_norm
    for col in (1, 2, 3):
        world.cell(row=r, column=col).border = box
world["B10"].number_format = "#,##0"
world["B9"].number_format = world["B11"].number_format = world["B12"].number_format = world["B13"].number_format = "#,##0"
world["B16"].number_format = "#,##0"
world["B17"].number_format = "0.0"
world.column_dimensions["A"].width = 40
world.column_dimensions["B"].width = 36
world.column_dimensions["C"].width = 70
CH1, CH2 = "'World Details'!$B$11", "'World Details'!$B$13"

# ---------------- Where Ore Spawns (Test 2 by Y) ----------------
title(spawn, "Where ore spawns, layer by layer (Test 2)",
      "Count = ore blocks found at that Y in the sample. Share = that layer's share of the ore's total. "
      "5-layer = this Y plus the 4 layers above it.")
n = len(ORES)
Y0, Y1 = F["lo"], F["hi"]
R0 = 5
R1 = R0 + (Y1 - Y0)
TOT = R1 + 1
c_count = {o: 2 + i for i, o in enumerate(ORES)}
c_share = {o: 2 + n + i for i, o in enumerate(ORES)}
c_roll = {o: 2 + 2 * n + i for i, o in enumerate(ORES)}
spawn.cell(row=4, column=1, value="Y level")
for grp, cmap, label in [("count", c_count, "Count"), ("share", c_share, "Share"), ("roll", c_roll, "5-layer")]:
    sc = min(cmap.values())
    spawn.merge_cells(start_row=3, start_column=sc, end_row=3, end_column=sc + n - 1)
    c = spawn.cell(row=3, column=sc, value={"count": "Ore blocks at this Y",
                                            "share": "Share of that ore found at this Y",
                                            "roll": "Ore blocks in Y to Y+4 (used to find the best band)"}[grp])
    c.font, c.alignment = f_bold, center
    for o in ORES:
        spawn.cell(row=4, column=cmap[o], value=f"{NICE[o]} {label}")
header(spawn, 4, [spawn.cell(row=4, column=i).value for i in range(1, 2 + 3 * n)])
# hidden key row with block ids for SUMIFS
spawn.cell(row=2, column=1).value = spawn.cell(row=2, column=1).value
for o in ORES:
    spawn.cell(row=R0 - 1, column=c_count[o]).comment = Comment(f"Block id: {o}", "report")
key_row = TOT + 2
spawn.cell(row=key_row, column=1, value="Block id").font = f_bold
for o in ORES:
    spawn.cell(row=key_row, column=c_count[o], value=o).font = f_input
for i, y in enumerate(range(Y0, Y1 + 1)):
    r = R0 + i
    spawn.cell(row=r, column=1, value=y).font = f_bold
    for o in ORES:
        cc = L(c_count[o])
        spawn.cell(row=r, column=c_count[o],
                   value=f"=SUMIFS({D2C},{D2A},{cc}${key_row},{D2B},$A{r})")
        spawn.cell(row=r, column=c_share[o], value=f"=IF({cc}${TOT}=0,0,{cc}{r}/{cc}${TOT})").number_format = "0.00%"
        end = min(r + 4, R1)
        spawn.cell(row=r, column=c_roll[o], value=f"=SUM({cc}{r}:{cc}{end})")
spawn.cell(row=TOT, column=1, value="Total").font = f_bold
for o in ORES:
    for cmap in (c_count, c_share):
        cl = L(cmap[o])
        c = spawn.cell(row=TOT, column=cmap[o], value=f"=SUM({cl}{R0}:{cl}{R1})")
        c.font = f_bold
    spawn.cell(row=TOT, column=c_share[o]).number_format = "0.0%"
spawn.cell(row=key_row + 1, column=1,
           value="Block ids above drive the SUMIFS formulas. Data source: 'Test2 Data' sheet.").font = f_sub
spawn.freeze_panes = spawn.cell(row=R0, column=2)
spawn.column_dimensions["A"].width = 9
for col in range(2, 2 + 3 * n):
    spawn.column_dimensions[L(col)].width = 13
for r in range(R0, R1 + 1):
    for col in range(2, 2 + n):
        spawn.cell(row=r, column=col).number_format = "#,##0"
    for col in range(2 + 2 * n, 2 + 3 * n):
        spawn.cell(row=r, column=col).number_format = "#,##0"
spawn.row_dimensions[3].height = 30

# ---------------- Mining Calc (helper, one row per Y) ----------------
calc = wb.create_sheet("Mining Calc")
title(calc, "Mining calculations per Y level (Test 2)",
      "Chance = ore blocks / rock blocks at that Y. Strip = ore seen per block of a 1x2 tunnel with feet at that Y "
      "(3 x this layer + 3 x layer above + floor + ceiling). Cave = visible ore / cave-wall blocks over 5 layers.")
mc_d = {o: 4 + i for i, o in enumerate(ORES)}
mc_s = {o: 4 + n + i for i, o in enumerate(ORES)}
mc_e = {o: 4 + 2 * n + i for i, o in enumerate(ORES)}
mc_c = {o: 4 + 3 * n + i for i, o in enumerate(ORES)}
mc_ss = {o: 4 + 4 * n + i for i, o in enumerate(ORES)}
mc_cs = {o: 4 + 5 * n + i for i, o in enumerate(ORES)}
labels_mc = ["Y level", "Rock blocks", "Cave-wall blocks"]
for grp, lab in [(mc_d, "chance per rock block"), (mc_s, "strip: ore per tunnel block"),
                 (mc_e, "visible ore blocks"), (mc_c, "cave: chance per wall block (5 layers)"),
                 (mc_ss, "ore in tunnel window (Y-1 to Y+2)"), (mc_cs, "visible ore in cave window (Y to Y+4)")]:
    for o in ORES:
        labels_mc.append(f"{NICE[o]} {lab}")
header(calc, 4, labels_mc)
MT = R1 + 3
for i, y in enumerate(range(Y0, Y1 + 1)):
    r = R0 + i
    calc.cell(row=r, column=1, value=y).font = f_bold
    calc.cell(row=r, column=2, value=f"=SUMIFS({LR},{LY},$A{r})").number_format = "#,##0"
    calc.cell(row=r, column=3, value=f"=SUMIFS({LW},{LY},$A{r})").number_format = "#,##0"
    end = min(r + 4, R1)
    for o in ORES:
        dl, sl, el = L(mc_d[o]), L(mc_s[o]), L(mc_e[o])
        cnt = f"'Where Ore Spawns'!{L(c_count[o])}{r}"
        calc.cell(row=r, column=mc_d[o], value=f"=IF($B{r}=0,0,{cnt}/$B{r})").number_format = "0.0000%"
        ssl, csl = L(mc_ss[o]), L(mc_cs[o])
        cl_ = L(c_count[o])
        calc.cell(row=r, column=mc_ss[o],
                  value=f"=SUM('Where Ore Spawns'!{cl_}{max(r - 1, R0)}:{cl_}{min(r + 2, R1)})").number_format = "#,##0"
        calc.cell(row=r, column=mc_s[o],
                  value=f"=IF({ssl}{r}>={ssl}${MT + 1},3*{dl}{r}+3*N({dl}{r + 1})+N({dl}{r - 1})+N({dl}{r + 2}),0)"
                  ).number_format = "0.0000"
        key = f"'Where Ore Spawns'!{L(c_count[o])}${key_row}"
        calc.cell(row=r, column=mc_e[o], value=f"=SUMIFS({D2E},{D2A},{key},{D2B},$A{r})").number_format = "#,##0"
        calc.cell(row=r, column=mc_cs[o], value=f"=SUM({el}{r}:{el}{end})").number_format = "#,##0"
        calc.cell(row=r, column=mc_c[o],
                  value=f"=IF(OR(SUM($C{r}:$C{end})=0,{csl}{r}<{csl}${MT + 1}),0,{csl}{r}/SUM($C{r}:$C{end}))"
                  ).number_format = "0.0000%"
calc.cell(row=MT, column=1, value="Total").font = f_bold
calc.cell(row=MT, column=2, value=f"=SUM(B{R0}:B{R1})").number_format = "#,##0"
calc.cell(row=MT, column=3, value=f"=SUM(C{R0}:C{R1})").number_format = "#,##0"
for o in ORES:
    el = L(mc_e[o])
    calc.cell(row=MT, column=mc_e[o], value=f"=SUM({el}{R0}:{el}{R1})").number_format = "#,##0"
calc.cell(row=MT + 1, column=1, value="Minimum ore in window (smaller samples are ignored)").font = f_bold
for o in ORES:
    for grp in (mc_ss, mc_cs):
        g = L(grp[o])
        calc.cell(row=MT + 1, column=grp[o],
                  value=f"=MAX('Mining Odds'!$B$9,'Mining Odds'!$B$10*MAX({g}{R0}:{g}{R1}))").number_format = "#,##0"
calc.freeze_panes = calc.cell(row=R0, column=2)
calc.column_dimensions["A"].width = 9
for col in range(2, 4 + 6 * n):
    calc.column_dimensions[L(col)].width = 14
calc.row_dimensions[4].height = 45

# ---------------- Mining Odds ----------------
odds = wb.create_sheet("Mining Odds")
title(odds, "Mining odds: strip mining vs exploring caves",
      "Chance of ore per block, the best tunnel height, and ore per hour. Change the yellow cells to match how "
      "fast you mine.")
MM = common.MINING
inputs = [
    ("Tunnel blocks per minute in stone", MM["stone_steps_per_min"],
     "1x2 tunnel with an Efficiency pickaxe, including torches and walking"),
    ("Tunnel blocks per minute in deepslate (below Y 0)", MM["deepslate_steps_per_min"],
     "Deepslate takes about twice as long to mine as stone"),
    ("Cave wall blocks looked at per minute", MM["cave_wall_per_min"], "Rough guess for walking through caves"),
    ("Blocks checked per tunnel block", MM["blocks_checked_per_step"],
     "2 mined + 2 walls on each side + floor + ceiling"),
    ("Minimum ore blocks for a height to count", MM["min_support"], "Ignores heights with too few ore blocks"),
    ("...and at least this share of the ore's best height", MM["min_support_frac"],
     "Stops a mountain peak with 3 ore blocks from winning"),
]
odds["A4"] = "Your mining speed (inputs)"
odds["A4"].font = f_bold
for i, (k, v, note) in enumerate(inputs):
    r = 5 + i
    odds.cell(row=r, column=1, value=k).font = f_norm
    c = odds.cell(row=r, column=2, value=v)
    c.font, c.fill, c.border = f_input, fill_input, box
    odds.cell(row=r, column=3, value=note).font = f_sub
odds["B10"].number_format = "0%"
odds["A12"] = "Data status"
odds["A12"].font = f_bold
odds["B12"] = ("Exact: rock and cave walls counted by the scanner" if LAYERS_EXACT else
               "ESTIMATE: strip odds are a lower bound and cave odds need a rescan with ore_scan.py v2")
odds["B12"].font = Font(name=FONT, size=10, bold=True, color="1E8E3E" if LAYERS_EXACT else "B06000")
TOTW = f"'Mining Calc'!$C${MT}"
TOTR = f"'Mining Calc'!$B${MT}"
oh = ["Ore", "Strip mine: tunnel at Y (feet)", "Ore seen per tunnel block", "Chance per block checked",
      "1 in N blocks", "Ore per 100 tunnel blocks", "Ore per hour (strip)", "Caves: best band from Y",
      "Chance per cave-wall block", "1 in N wall blocks", "Ore per hour (caves)", "Share visible from caves",
      "Average chance per rock block (anywhere)", "Block id"]
OH = 14
header(odds, OH, oh)
ODD_ORDER = list(reversed(DEPTH_ORDER))
MCY = f"'Mining Calc'!$A${R0}:$A${R1}"
RS = "\"rescan needed\""
for i, o in enumerate(ODD_ORDER):
    r = OH + 1 + i
    ore_cell(odds.cell(row=r, column=1), o)
    odds.cell(row=r, column=14, value=o).font = f_input
    sc = f"'Mining Calc'!${L(mc_s[o])}${R0}:${L(mc_s[o])}${R1}"
    cc = f"'Mining Calc'!${L(mc_c[o])}${R0}:${L(mc_c[o])}${R1}"
    ex_tot = f"'Mining Calc'!${L(mc_e[o])}${MT}"
    ore_tot = f"'Where Ore Spawns'!${L(c_count[o])}${TOT}"
    vals = {
        2: f"=INDEX({MCY},MATCH(MAX({sc}),{sc},0))",
        3: f"=MAX({sc})",
        4: f"=C{r}/$B$8",
        5: f'=IF(D{r}=0,"",1/D{r})',
        6: f"=C{r}*100",
        7: f"=C{r}*IF(B{r}<0,$B$6,$B$5)*60",
        8: f"=IF({TOTW}=0,{RS},IF(MAX({cc})=0,\"too few seen\",INDEX({MCY},MATCH(MAX({cc}),{cc},0))))",
        9: f"=IF({TOTW}=0,{RS},MAX({cc}))",
        10: f'=IF(ISNUMBER(I{r}),IF(I{r}=0,"",1/I{r}),{RS})',
        11: f'=IF(ISNUMBER(I{r}),IF(I{r}=0,"",I{r}*$B$7*60),{RS})',
        12: f"=IF({TOTW}=0,{RS},IF({ore_tot}=0,0,{ex_tot}/{ore_tot}))",
        13: f'=IF({TOTW}=0,{RS},IF({TOTR}=0,"",1/({ore_tot}/{TOTR})))',
    }
    fmts = {3: "0.0000", 4: "0.000%", 5: '"1 in "#,##0', 6: "0.00", 7: "#,##0.0", 9: "0.000%",
            10: '"1 in "#,##0', 11: "#,##0.0", 12: "0.0%", 13: '"1 in "#,##0'}
    for col, v in vals.items():
        c = odds.cell(row=r, column=col, value=v)
        c.border, c.alignment = box, center
        c.font = f_norm
        if col in fmts:
            c.number_format = fmts[col]
ON = OH + n
br = ON + 2
odds.cell(row=br, column=1, value="Blocks mined per hour (2 per tunnel block)").font = f_bold
odds.cell(row=br + 1, column=1, value="In stone").font = f_norm
odds.cell(row=br + 1, column=2, value="=$B$5*2*60").number_format = "#,##0"
odds.cell(row=br + 2, column=1, value="In deepslate").font = f_norm
odds.cell(row=br + 2, column=2, value="=$B$6*2*60").number_format = "#,##0"
how = [
    "How to read this:",
    "Strip mine: dig a 1 wide, 2 tall tunnel with your feet at the given Y. Each block you move forward you mine 2 "
    "blocks and can see 6 more (walls, floor, ceiling), so 8 blocks are checked.",
    "Chance per block checked: the chance that one of those blocks is this ore. 1 in N says the same thing as a count.",
    "Ore per hour: ore blocks you can expect to see at your mining speed. Ores come in veins, so you often get a few "
    "more by mining out the whole vein.",
    "Caves: the chance that a cave-wall block you look at is this ore. Some ores (diamond, for example) are placed "
    "less often next to air, so caves can be worse than strip mining for them.",
    "Average chance: one random rock block anywhere in the world, from bedrock to the top of mountains.",
    "Small samples are ignored: a height only counts if it holds at least the minimum number of ore blocks set above "
    "(30 and 10% of the ore's best height). 'too few seen' means the ore is rarely visible from caves.",
    "A tunnel height of Y 100 or more means tunnelling inside mountains, where the rock is rich but there is less of it.",
]
for i, t in enumerate(how):
    c = odds.cell(row=br + 4 + i, column=1, value=t)
    c.font = f_bold if i == 0 else f_norm
    odds.merge_cells(start_row=br + 4 + i, start_column=1, end_row=br + 4 + i, end_column=13)
for i, w in enumerate([44, 13, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 14, 14], start=1):
    odds.column_dimensions[L(i)].width = w
odds.row_dimensions[OH].height = 58
for r in range(OH + 1, ON + 1):
    odds.row_dimensions[r].height = 30  # fixed, so wrapped "rescan needed" cannot shift the chart
ob = BarChart()
ob.type = "bar"
ob.title = "Ore per hour" + (": strip mining vs caves" if LAYERS_EXACT else ": strip mining (estimate)")
ob.add_data(Reference(odds, min_col=7, min_row=OH, max_row=ON), titles_from_data=True)
if LAYERS_EXACT:
    ob.add_data(Reference(odds, min_col=11, min_row=OH, max_row=ON), titles_from_data=True)
ob.set_categories(Reference(odds, min_col=1, min_row=OH + 1, max_row=ON))
ob.series[0].graphicalProperties.solidFill = "3B4A5A"
if LAYERS_EXACT:
    ob.series[1].graphicalProperties.solidFill = "9AA5B1"
    ob.legend.position = "b"
else:
    ob.legend = None
ob.x_axis.scaling.orientation = "maxMin"
ob.x_axis.delete = False
ob.y_axis.delete = False
ob.y_axis.majorGridlines = None
ob.y_axis.title = "Ore blocks per hour"
ob.height, ob.width = 9, 18
odds.add_chart(ob, f"A{br + 4 + len(how) + 1}")

# ---------------- Mining Guide ----------------
title(guide, f"{A.world} mining guide: the best Y level for every ore",
      f"{A.modpack} on Minecraft {A.mc_version}, {A.dimension}. Based on Test 2 ({A.chunks2:,} chunks). "
      "Y is the height shown on the F3 screen.")
gh = ["Ore", "Best single layer (Y)", "Best 5-layer band from (Y)", "to (Y)",
      "Most of it is between (Y)", "and (Y)", "Lowest found (Y)", "Highest found (Y)",
      "Ore blocks per chunk", "How common (1 = most)", "Tip", "Block id"]
header(guide, 4, gh)
G0 = 5
for i, o in enumerate(ORES):
    r = G0 + i
    ore_cell(guide.cell(row=r, column=1), o)
    key = f"$L{r}"
    guide.cell(row=r, column=12, value=o).font = f_input
    guide.cell(row=r, column=2, value="=" + sum_lookup(T2S, "D", key, t2s_end)).font = f_link
    rc = L(c_roll[o])
    band = (f"=INDEX('Where Ore Spawns'!$A${R0}:$A${R1},MATCH(MAX('Where Ore Spawns'!{rc}${R0}:{rc}${R1}),"
            f"'Where Ore Spawns'!{rc}${R0}:{rc}${R1},0))")
    guide.cell(row=r, column=3, value=band).font = f_link
    guide.cell(row=r, column=4, value=f"=C{r}+4")
    guide.cell(row=r, column=5, value="=" + sum_lookup(T2S, "F", key, t2s_end)).font = f_link
    guide.cell(row=r, column=6, value="=" + sum_lookup(T2S, "G", key, t2s_end)).font = f_link
    guide.cell(row=r, column=7, value="=" + sum_lookup(T2S, "H", key, t2s_end)).font = f_link
    guide.cell(row=r, column=8, value="=" + sum_lookup(T2S, "I", key, t2s_end)).font = f_link
    guide.cell(row=r, column=9, value="=" + sum_lookup(T2S, "B", key, t2s_end) + f"/{CH2}").number_format = "0.00"
    guide.cell(row=r, column=10, value=f"=RANK(I{r},$I${G0}:$I${G0 + n - 1})")
    guide.cell(row=r, column=11, value=TIPS[o]).alignment = wrap
    for col in range(2, 11):
        c = guide.cell(row=r, column=col)
        c.alignment = center
        c.border = box
        if c.font.color is None or c.font.color.rgb != "FF008000":
            c.font = f_norm
    for col in (11, 12):
        guide.cell(row=r, column=col).border = box
    guide.row_dimensions[r].height = 48
GN = G0 + n - 1
note_r = GN + 2
notes = [
    "How to read this:",
    "Best single layer = the one Y level with the most of that ore. Good for a quick answer, but it can move a few "
    "blocks between samples when the band has a flat top.",
    "Best 5-layer band = the 5 layers in a row with the most ore. This is the most reliable place for a branch mine.",
    "Most of it is between = the middle 80% of that ore (10th to 90th percentile).",
    "Ore blocks per chunk = average ore blocks in one 16 x 16 chunk column, top to bottom. Already-mined chunks lower this.",
    "Colours: green numbers come from other sheets, blue cells are raw inputs, black cells are calculated here.",
    (f"Best two-for-one layers: Y {F['combo'][0]} to {F['combo'][1]} (inside the best band for both diamond and redstone). "
     if F["combo"] else "") + "Check any layer on the 'Layer Lookup' sheet.",
]
for i, t in enumerate(notes):
    c = guide.cell(row=note_r + i, column=1, value=t)
    c.font = f_bold if i == 0 else f_norm
    guide.merge_cells(start_row=note_r + i, start_column=1, end_row=note_r + i, end_column=11)
widths = [14, 12, 13, 8, 13, 8, 11, 11, 12, 11, 70, 14]
for i, w in enumerate(widths, start=1):
    guide.column_dimensions[L(i)].width = w
guide.row_dimensions[4].height = 42
guide.freeze_panes = "B5"

bar = BarChart()
bar.type = "bar"
bar.title = "Ore blocks per chunk (Test 2)"
bar.y_axis.title = "Ore blocks per chunk"
bar.x_axis.title = None
data = Reference(guide, min_col=9, min_row=4, max_row=GN)
cats = Reference(guide, min_col=1, min_row=G0, max_row=GN)
bar.add_data(data, titles_from_data=True)
bar.set_categories(cats)
bar.legend = None
bar.gapWidth = 40
ser = bar.series[0]
for i, o in enumerate(ORES):
    pt = DataPoint(idx=i)
    pt.graphicalProperties.solidFill = COLOR[o]
    pt.graphicalProperties.line.solidFill = "FFFFFF"
    ser.dPt.append(pt)
bar.x_axis.scaling.orientation = "maxMin"
bar.x_axis.delete = False
bar.y_axis.delete = False
bar.y_axis.majorGridlines = None
bar.height, bar.width = 9, 18
from openpyxl.chart.label import DataLabelList
ser.dLbls = DataLabelList()
ser.dLbls.showVal = True
ser.dLbls.showSerName = False
ser.dLbls.showCatName = False
ser.dLbls.showLegendKey = False
ser.dLbls.numFmt = "0.0"
guide.add_chart(bar, f"A{note_r + len(notes) + 1}")

# ---------------- Ore Charts (small multiples, Y vertical like in game) ----------------
title(charts, "Where each ore spawns (Test 2)",
      "Height (Y) runs up the side, like in game. The further right the line goes, the more of that ore is at that "
      "height. Charts update from the 'Where Ore Spawns' sheet.")
for i, o in enumerate(ORES):
    ch = ScatterChart()
    ch.title = NICE[o]
    ch.style = 13
    xs = Reference(spawn, min_col=c_share[o], min_row=R0, max_row=R1)
    ys = Reference(spawn, min_col=1, min_row=R0, max_row=R1)
    s = Series(ys, xs, title=NICE[o])
    s.marker.symbol = "none"
    s.graphicalProperties.line.solidFill = COLOR[o] if o != "iron_ore" else "B07E5C"
    s.graphicalProperties.line.width = 22000
    s.smooth = False
    ch.series.append(s)
    ch.legend = None
    ch.y_axis.title = "Y level"
    ch.x_axis.title = "Share of this ore"
    ch.y_axis.scaling.min = -64
    ch.y_axis.scaling.max = 320
    ch.y_axis.majorUnit = 32
    ch.x_axis.scaling.min = 0
    ch.x_axis.number_format = "0.0%"
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    ch.x_axis.majorGridlines = None
    ch.x_axis.crosses = "min"
    ch.x_axis.number_format = "0%"
    ch.height, ch.width = 9.5, 8
    row = 4 + (i // 4) * 20
    col = 1 + (i % 4) * 6
    charts.add_chart(ch, f"{L(col)}{row}")
for col in range(1, 26):
    charts.column_dimensions[L(col)].width = 9

# ---------------- Layer Lookup ----------------
title(lookup, "Layer lookup: what will I find at this Y level?",
      "Type a Y level in the yellow cell (between -64 and 320). The table and chart update.")
lookup["A4"] = "Your Y level"
lookup["A4"].font = f_bold
lookup["B4"] = -59
lookup["B4"].font = Font(name=FONT, size=14, bold=True, color="0000FF")
lookup["B4"].fill = fill_input
lookup["B4"].alignment = center
lookup["B4"].border = box
dv = DataValidation(type="whole", operator="between", formula1="-64", formula2="320",
                    showErrorMessage=True, errorTitle="Y out of range",
                    error="Enter a whole number from -64 to 320.")
lookup.add_data_validation(dv)
dv.add("B4")
lookup["C4"] = "Example: -59 is the diamond layer. Try 15 for iron or 40 for coal."
lookup["C4"].font = f_sub
header(lookup, 6, ["Ore", "Ore blocks per chunk at this exact Y",
                   "Share of that ore at this exact Y", "Share of that ore within 2 layers (Y-2 to Y+2)",
                   "Block id"])
L0 = 7
for i, o in enumerate(ORES):
    r = L0 + i
    ore_cell(lookup.cell(row=r, column=1), o)
    lookup.cell(row=r, column=5, value=o).font = f_input
    lookup.cell(row=r, column=2,
                value=f"=SUMIFS({D2C},{D2A},$E{r},{D2B},$B$4)/{CH2}").number_format = "0.000"
    tot = "SUMIFS(" + D2C + "," + D2A + ",$E" + str(r) + ")"
    lookup.cell(row=r, column=3,
                value=f"=IF({tot}=0,0,SUMIFS({D2C},{D2A},$E{r},{D2B},$B$4)/{tot})").number_format = "0.00%"
    lookup.cell(row=r, column=4,
                value=f"=IF({tot}=0,0,SUMIFS({D2C},{D2A},$E{r},{D2B},\">=\"&($B$4-2),{D2B},\"<=\"&($B$4+2))/{tot})"
                ).number_format = "0.00%"
    for col in range(2, 6):
        lookup.cell(row=r, column=col).border = box
        lookup.cell(row=r, column=col).alignment = center
LN = L0 + n - 1
lookup.cell(row=LN + 1, column=1, value="All ores").font = f_bold
lookup.cell(row=LN + 1, column=2, value=f"=SUM(B{L0}:B{LN})").number_format = "0.000"
lookup.cell(row=LN + 1, column=2).font = f_bold
for i, w in enumerate([16, 20, 18, 22, 14], start=1):
    lookup.column_dimensions[L(i)].width = w
lookup.row_dimensions[6].height = 45
lb = BarChart()
lb.type = "bar"
lb.title = "Ore blocks per chunk at your Y level"
lb.add_data(Reference(lookup, min_col=2, min_row=6, max_row=LN), titles_from_data=True)
lb.set_categories(Reference(lookup, min_col=1, min_row=L0, max_row=LN))
lb.legend = None
lb.gapWidth = 40
for i, o in enumerate(ORES):
    pt = DataPoint(idx=i)
    pt.graphicalProperties.solidFill = COLOR[o]
    lb.series[0].dPt.append(pt)
lb.x_axis.scaling.orientation = "maxMin"
lb.x_axis.delete = False
lb.y_axis.delete = False
lb.y_axis.majorGridlines = None
lb.y_axis.number_format = "0.0"
lb.height, lb.width = 8, 16
lookup.add_chart(lb, f"A{LN + 3}")

# ---------------- Test Comparison ----------------
title(comp, "Test 1 vs Test 2: do the two scans agree?",
      f"Test 1 = {A.chunks1:,} chunks (seed {A.seed1}). Test 2 = {A.chunks2:,} chunks (seed {A.seed2}), a different random sample. "
      "Diff = Test 2 minus Test 1.")
ch_head = ["Ore", "Test 1 ore blocks", "Test 2 ore blocks", "Test 1 per chunk", "Test 2 per chunk", "Per chunk diff %",
           "Test 1 median Y", "Test 2 median Y", "Median diff", "Test 1 best Y", "Test 2 best Y", "Best Y diff",
           "Test 1 band low (Y)", "Test 2 band low (Y)", "Band low diff", "Test 1 band high (Y)",
           "Test 2 band high (Y)", "Band high diff", "Block id"]
header(comp, 4, ch_head)
C0 = 5
for i, o in enumerate(ORES):
    r = C0 + i
    ore_cell(comp.cell(row=r, column=1), o)
    comp.cell(row=r, column=19, value=o).font = f_input
    key = f"$S{r}"
    vals = {
        2: "=" + sum_lookup(T1S, "B", key, t1s_end), 3: "=" + sum_lookup(T2S, "B", key, t2s_end),
        4: f"=B{r}/{CH1}", 5: f"=C{r}/{CH2}", 6: f"=IF(D{r}=0,0,(E{r}-D{r})/D{r})",
        7: "=" + sum_lookup(T1S, "E", key, t1s_end), 8: "=" + sum_lookup(T2S, "E", key, t2s_end), 9: f"=H{r}-G{r}",
        10: "=" + sum_lookup(T1S, "D", key, t1s_end), 11: "=" + sum_lookup(T2S, "D", key, t2s_end), 12: f"=K{r}-J{r}",
        13: "=" + sum_lookup(T1S, "F", key, t1s_end), 14: "=" + sum_lookup(T2S, "F", key, t2s_end), 15: f"=N{r}-M{r}",
        16: "=" + sum_lookup(T1S, "G", key, t1s_end), 17: "=" + sum_lookup(T2S, "G", key, t2s_end), 18: f"=Q{r}-P{r}",
    }
    for col, v in vals.items():
        c = comp.cell(row=r, column=col, value=v)
        c.border, c.alignment = box, center
        c.font = f_link if "!" in v else f_norm
    comp.cell(row=r, column=2).number_format = comp.cell(row=r, column=3).number_format = "#,##0"
    comp.cell(row=r, column=4).number_format = comp.cell(row=r, column=5).number_format = "0.00"
    comp.cell(row=r, column=6).number_format = "+0.0%;-0.0%;0.0%"
    for col in (9, 12, 15, 18):
        comp.cell(row=r, column=col).number_format = "+0;-0;0"
CN = C0 + n - 1
comp.column_dimensions["A"].width = 14
for col in range(2, 20):
    comp.column_dimensions[L(col)].width = 11
comp.row_dimensions[4].height = 42
comp.freeze_panes = "B5"
cb = BarChart()
cb.type = "bar"
cb.title = "Ore blocks per chunk: Test 1 vs Test 2"
cb.add_data(Reference(comp, min_col=4, max_col=5, min_row=4, max_row=CN), titles_from_data=True)
cb.set_categories(Reference(comp, min_col=1, min_row=C0, max_row=CN))
cb.series[0].graphicalProperties.solidFill = "9AA5B1"
cb.series[1].graphicalProperties.solidFill = "2C4FD1"
cb.x_axis.scaling.orientation = "maxMin"
cb.x_axis.delete = False
cb.y_axis.delete = False
cb.y_axis.majorGridlines = None
cb.legend.position = "b"
cb.height, cb.width = 9, 16
comp.add_chart(cb, f"A{CN + 3}")
mb = BarChart()
mb.type = "bar"
mb.title = "Median Y: Test 1 vs Test 2"
mb.add_data(Reference(comp, min_col=7, max_col=8, min_row=4, max_row=CN), titles_from_data=True)
mb.set_categories(Reference(comp, min_col=1, min_row=C0, max_row=CN))
mb.series[0].graphicalProperties.solidFill = "9AA5B1"
mb.series[1].graphicalProperties.solidFill = "2C4FD1"
mb.x_axis.scaling.orientation = "maxMin"
mb.x_axis.delete = False
mb.y_axis.delete = False
mb.y_axis.majorGridlines = None
mb.y_axis.title = "Y level"
mb.x_axis.tickLblPos = "low"
mb.legend.position = "b"
mb.height, mb.width = 9, 16
comp.add_chart(mb, f"J{CN + 3}")

# ---------------- Test Cases ----------------
title(tests, "Test cases: can these numbers be trusted?",
      "Each row is one check with a clear pass rule. Change a yellow limit and the results update.")
tests["A4"] = "Limits (inputs)"
tests["A4"].font = f_bold
LM = common.LIMITS
limits = [
    ("Minimum chunks in Test 1", LM["min_chunks1"], "Enough for common ores"),
    ("Minimum chunks in Test 2", LM["min_chunks2"], "Enough for rare ores like emerald"),
    ("Test 2 at least this many times bigger", LM["min_ratio"], "Makes Test 2 a clearly bigger, separate sample"),
    ("Max per chunk difference between tests", LM["pc_diff"], "5% is normal sampling noise"),
    ("Max median Y difference (blocks)", LM["median"], ""),
    ("Max band edge difference (blocks)", LM["band"], "Band = middle 80% of the ore"),
    ("Max best-layer difference (blocks)", LM["peak"], "Strict: best single layer is noisy for flat or rare bands"),
    ("Max stray share for vanilla checks", LM["stray"], "0.1% allows a few blocks from structures"),
]
for i, (k, v, note) in enumerate(limits):
    r = 5 + i
    tests.cell(row=r, column=1, value=k).font = f_norm
    c = tests.cell(row=r, column=2, value=v)
    c.font, c.fill, c.border = f_input, fill_input, box
    tests.cell(row=r, column=3, value=note).font = f_sub
tests["B8"].number_format = "0%"
tests["B12"].number_format = "0.0%"
LIM_T1, LIM_T2, LIM_RATIO, LIM_PC, LIM_MED, LIM_BAND, LIM_PEAK, LIM_VAN = [f"$B${5 + i}" for i in range(8)]
sum_r = 14
tests.cell(row=sum_r, column=1, value="Results").font = f_bold
labels = ["PASS", "FAIL", "MATCHES VANILLA", "DIFFERS FROM VANILLA"]
TH = 20
for i, lab in enumerate(labels):
    tests.cell(row=sum_r + 1 + i, column=1, value=lab).font = f_norm
    tests.cell(row=sum_r + 1 + i, column=2, value=f'=COUNTIF($G${TH + 1}:$G$200,"{lab}")').font = f_bold
header(tests, TH, ["ID", "Group", "What is checked", "Ore", "Expected", "Actual", "Result", "What it means"])
rows = []
WD = "'World Details'"
rows.append(("Sample size", "Test 1 scanned enough chunks", "", f'=">= "&TEXT({LIM_T1},"#,##0")',
             f"={WD}!$B$11", f'=IF(F{{r}}>={LIM_T1},"PASS","FAIL")',
             "Small samples give noisy numbers. 3,000+ chunks is enough for common ores."))
rows.append(("Sample size", "Test 2 scanned enough chunks", "", f'=">= "&TEXT({LIM_T2},"#,##0")',
             f"={WD}!$B$13", f'=IF(F{{r}}>={LIM_T2},"PASS","FAIL")',
             "A bigger sample is needed for rare ores such as emerald."))
rows.append(("Sample size", "Test 2 is a different, larger sample", "", f'=">= "&{LIM_RATIO}&"x"',
             f"={WD}!$B$13/{WD}!$B$11", f'=IF(F{{r}}>={LIM_RATIO},"PASS","FAIL")',
             "Two independent samples let us check the numbers repeat."))
rows.append(("Coverage", "Both tests found the same ore types", "", f"=COUNTA({T2S}!{S2R})",
             f"=SUMPRODUCT(COUNTIF({T1S}!{S1R},{T2S}!{S2R}))", f'=IF(F{{r}}=E{{r}},"PASS","FAIL")',
             "If an ore appears in only one test, it is too rare to measure or the scan missed it."))
groups = [
    ("Stability", "Ore per chunk is the same in both tests", f'="within "&TEXT({LIM_PC},"0%")',
     "=ABS('Test Comparison'!$F{c})", LIM_PC, "0.0%",
     "How common the ore is does not depend on which chunks were sampled."),
    ("Stability", "Median Y is the same in both tests", f'="within "&{LIM_MED}&" blocks"',
     "=ABS('Test Comparison'!$I{c})", LIM_MED, "0",
     "The centre of the ore band is reliable."),
    ("Stability", "Main band (middle 80%) is the same in both tests", f'="within "&{LIM_BAND}&" blocks"',
     "=MAX(ABS('Test Comparison'!$O{c}),ABS('Test Comparison'!$R{c}))", LIM_BAND, "0",
     "The range you should mine in is reliable."),
    ("Stability", "Best single layer is the same in both tests", f'="within "&{LIM_PEAK}&" blocks"',
     "=ABS('Test Comparison'!$L{c})", LIM_PEAK, "0",
     "If FAIL: the band has a flat top or the ore is rare, so the single best layer moves around. "
     "Use the best 5-layer band from the Mining Guide instead."),
]
for grp, what, exp, act, lim, fmt, mean in groups:
    for i, o in enumerate(ORES):
        rows.append((grp, what, o, exp, act.format(c=C0 + i), f'=IF(F{{r}}<={lim},"PASS","FAIL")', mean, fmt))


def stray(o, cond, label):
    tot = f"SUMIFS({D2C},{D2A},\"{o}\")"
    part = f"SUMIFS({D2C},{D2A},\"{o}\",{D2B},{cond})" if not isinstance(cond, tuple) else \
        f"SUMIFS({D2C},{D2A},\"{o}\",{D2B},\"{cond[0]}\",{D2B},\"{cond[1]}\")"
    return f"={part}/{tot}"


coal_note = (f" For coal this is a real pack difference: about {F['coal_low']:.1f}% of coal is below Y 0."
             if F["coal_low"] > 0.1 else "")
for o, cond, what, _share in F["vanilla"]:
    rows.append(("Vanilla rules", what, o, f'="at most "&TEXT({LIM_VAN},"0.0%")', stray(o, cond, what),
                 f'=IF(F{{r}}<={LIM_VAN},"MATCHES VANILLA","DIFFERS FROM VANILLA")',
                 "MATCHES: this pack uses the normal vanilla rule for this ore. DIFFERS: the pack changes it."
                 + (coal_note if o == "coal_ore" else ""), "0.000%"))
for i, row in enumerate(rows, start=1):
    r = TH + i
    grp, what, o, exp, act, res, mean = row[:7]
    fmt = row[7] if len(row) > 7 else None
    tests.cell(row=r, column=1, value=f"TC-{i:02d}")
    tests.cell(row=r, column=2, value=grp)
    tests.cell(row=r, column=3, value=what)
    if o:
        ore_cell(tests.cell(row=r, column=4), o)
    tests.cell(row=r, column=5, value=exp)
    c = tests.cell(row=r, column=6, value=act)
    c.font = f_link
    if fmt:
        c.number_format = fmt
    elif "B$11" in act or "B$13" in act:
        c.number_format = "#,##0.0" if "/" in act else "#,##0"
    tests.cell(row=r, column=7, value=res.replace("{r}", str(r)))
    tests.cell(row=r, column=8, value=mean)
    for col in range(1, 9):
        cell = tests.cell(row=r, column=col)
        cell.border = box
        if col in (3, 8):
            cell.alignment = wrap
        elif col != 4:
            cell.alignment = center
        if col not in (4, 6):
            cell.font = f_bold if col == 7 else f_norm
TN = TH + len(rows)
green = PatternFill("solid", fgColor="C6EFCE")
red = PatternFill("solid", fgColor="FFC7CE")
amber = PatternFill("solid", fgColor="FFEB9C")
rng = f"G{TH + 1}:G{TN}"
tests.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"PASS"'], fill=green))
tests.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"MATCHES VANILLA"'], fill=green))
tests.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"FAIL"'], fill=red))
tests.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=['"DIFFERS FROM VANILLA"'], fill=amber))
for i, w in enumerate([8, 14, 40, 14, 16, 12, 22, 80], start=1):
    tests.column_dimensions[L(i)].width = w
tests.column_dimensions["A"].width = 40
tests.freeze_panes = f"A{TH + 1}"

# ---------------- Start Here ----------------
title(start, f"{A.world} ore report", f"Where to dig for every ore in your {A.modpack} world (Minecraft {A.mc_version})")
intro = [
    ("What is this?", f"A scan of the real blocks in the {A.world} save. A script read thousands of chunks and counted "
                      "every ore block at every height (Y level). Because it reads the actual world, it includes the "
                      "modpack's custom terrain, mountains and floating islands."),
    ("Quick answer", common.quick_answer(F, DEPTH_ORDER)),
    ("What is Y?", "Your height in the world. Press F3 in game and read the Y value. Bedrock is at Y -64, "
                   "sea level is Y 63."),
    ("What is a chunk?", "A 16 x 16 block column that goes from the bottom of the world to the top. "
                         "'Ore blocks per chunk' is how many ore blocks one chunk holds on average."),
    ("Two tests", f"Test 1 scanned {A.chunks1:,} chunks. Test 2 scanned {A.chunks2:,} different chunks. If both give the same "
                  "answer, the numbers are trustworthy. See 'Test Cases'."),
    ("Limits", "Chunks you already mined have less ore, so totals are slightly low. Unfinished chunks at the edge "
               "of explored land were skipped on purpose."),
]
r = 4
for k, v in intro:
    start.cell(row=r, column=1, value=k).font = f_bold
    c = start.cell(row=r, column=2, value=v)
    c.font, c.alignment = f_norm, wrap
    start.row_dimensions[r].height = 46
    r += 1
r += 1
start.cell(row=r, column=1, value="Sheets in this report").font = Font(name=FONT, size=12, bold=True)
r += 1
header(start, r, ["Sheet", "What you will find"])
sheets = [
    ("Mining Guide", "The best Y level for every ore, with tips and a chart of how common each ore is."),
    ("Where Ore Spawns", "Layer-by-layer ore counts from Y -64 to Y 320. Feeds the charts."),
    ("Ore Charts", "One chart per ore with height going up the side, like in game."),
    ("Layer Lookup", "Type any Y level and see what ores you will find there."),
    ("Mining Odds", "Strip mining vs caves: chance per block, best tunnel height, ore per hour. Edit your mining speed."),
    ("Test Comparison", "Test 1 and Test 2 side by side."),
    ("Test Cases", "Checks with PASS / FAIL results, plus checks against vanilla ore rules."),
    ("World Details", "Facts about the world and both scans."),
    ("Mining Calc", "Per-Y helper columns behind Mining Odds."),
    ("Test1 / Test2 sheets", "Raw data from the scanner. Everything else is calculated from these."),
]
for k, v in sheets:
    r += 1
    start.cell(row=r, column=1, value=k).font = f_bold
    start.cell(row=r, column=2, value=v).font = f_norm
    for col in (1, 2):
        start.cell(row=r, column=col).border = box
r += 2
start.cell(row=r, column=1, value="Colour key").font = Font(name=FONT, size=12, bold=True)
for k, v, font, fill in [("Blue text", "Raw input from the scanner or the player", f_input, None),
                         ("Green text", "Pulled from another sheet", f_link, None),
                         ("Black text", "Calculated on this sheet", f_norm, None),
                         ("Yellow cell", "You can change this", f_input, fill_input)]:
    r += 1
    c = start.cell(row=r, column=1, value=k)
    c.font = font
    if fill:
        c.fill = fill
    start.cell(row=r, column=2, value=v).font = f_norm
r += 2
start.cell(row=r, column=1, value="Source").font = f_bold
start.cell(row=r, column=2, value=f"ore_scan.py output for the {A.world} save, scanned on {A.scan_date}. "
                                  f"Test 1: {A.test1}. Test 2: {A.test2}.").font = f_norm
start.column_dimensions["A"].width = 24
start.column_dimensions["B"].width = 110

# order and finish
order = ["Start Here", "Mining Guide", "Mining Odds", "Layer Lookup", "Ore Charts", "Where Ore Spawns", "Mining Calc",
         "Test Cases",
         "Test Comparison", "World Details", "Test1 Summary", "Test1 Data", "Test2 Summary", "Test2 Data", "Test2 Layers"]
wb._sheets = [wb[s] for s in order]
for ws in wb.worksheets:
    ws.sheet_view.showGridLines = ws.title in ("Where Ore Spawns", "Mining Calc", "Test1 Data", "Test2 Data",
                                               "Test2 Layers")
for s in ("Test1 Summary", "Test1 Data", "Test2 Summary", "Test2 Data", "Test2 Layers"):
    wb[s].sheet_properties.tabColor = "9AA5B1"
for s in ("Mining Guide", "Mining Odds", "Layer Lookup", "Ore Charts"):
    wb[s].sheet_properties.tabColor = "18C346"
wb["Test Cases"].sheet_properties.tabColor = "2C4FD1"
from openpyxl.worksheet.properties import PageSetupProperties
for s in ("Start Here", "Mining Guide", "Mining Odds", "Layer Lookup", "Ore Charts", "Test Cases", "Test Comparison",
          "World Details"):
    ws = wb[s]
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0 if s == "Test Cases" else 1
wb.active = 0
wb.calculation.fullCalcOnLoad = True  # Excel computes every formula when the file is opened
out = os.path.join(A.out_dir, f"{A.world}_Ore_Report.xlsx")
wb.save(out)
print("saved", out, "with", len(rows), "test cases")
