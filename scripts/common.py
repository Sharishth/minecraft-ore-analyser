"""Shared settings, data loading and derived facts for build_report.py and build_infographic.py.

Every number used in text (tips, quick answers, infographic) is computed here from the
scanner CSVs, so the workbook and the infographic always agree.
"""
import argparse
import os
import numpy as np
import pandas as pd

NICE = {"coal_ore": "Coal", "iron_ore": "Iron", "copper_ore": "Copper", "redstone_ore": "Redstone",
        "gold_ore": "Gold", "diamond_ore": "Diamond", "lapis_ore": "Lapis Lazuli", "emerald_ore": "Emerald",
        "quartz_ore": "Nether Quartz", "ancient_debris": "Ancient Debris"}
COLOR = {"coal_ore": "#2b2b2b", "iron_ore": "#d8af93", "copper_ore": "#e2793f", "redstone_ore": "#e3141b",
         "gold_ore": "#f6d33c", "diamond_ore": "#4ee6de", "lapis_ore": "#2c4fd1", "emerald_ore": "#18c346",
         "quartz_ore": "#ece4d6", "ancient_debris": "#6b4a3a"}
FALLBACK_COLORS = ["#8a64c4", "#3c9d9b", "#b5651d", "#7a7a7a", "#c94f7c", "#4f7cc9"]
DARK_TEXT = {"iron_ore", "gold_ore", "diamond_ore", "quartz_ore"}

# Mining-speed assumptions for "ore per hour". Editable on the Mining Odds sheet of the workbook.
MINING = {
    "stone_steps_per_min": 20,      # 1x2 tunnel blocks per minute in stone (Efficiency pickaxe, incl. torches and walking)
    "deepslate_steps_per_min": 12,  # deepslate takes about twice as long to mine
    "cave_wall_per_min": 150,       # cave wall blocks you look at per minute while exploring (rough guess)
    "blocks_checked_per_step": 8,   # 1x2 tunnel: 2 mined + 2 walls on each side (4) + floor + ceiling
    "min_support": 30,              # a height only counts if its window holds at least this many ore blocks...
    "min_support_frac": 0.10,       # ...and at least this share of the ore's best window (filters tiny samples)
}

# Pass rules for the test cases. The workbook shows these as editable yellow cells.
LIMITS = {
    "min_chunks1": 3000,   # Test 1 sample size
    "min_chunks2": 15000,  # Test 2 sample size
    "min_ratio": 4,        # Test 2 must be at least this many times larger than Test 1
    "pc_diff": 0.05,       # max difference in ore per chunk between tests (fraction)
    "median": 3,           # max median Y difference (blocks)
    "band": 5,             # max difference of the 10th/90th percentile Y (blocks)
    "peak": 5,             # max best-single-layer difference (blocks)
    "stray": 0.001,        # max share of an ore outside its vanilla range (fraction)
}


def nice(ore):
    return NICE.get(ore, ore.split(":")[-1].replace("_ore", "").replace("_", " ").title())


def color(ore, i=0):
    return COLOR.get(ore, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])


def parse_args(description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--test1", default="output/test1", help="folder with Test 1 ore_summary.csv and ore_by_y.csv")
    ap.add_argument("--test2", default="output/test2", help="folder with Test 2 CSVs (and cross_section.png)")
    ap.add_argument("--chunks1", type=int, default=3792, help="chunks scanned in Test 1 (console output)")
    ap.add_argument("--chunks2", type=int, default=18960, help="chunks scanned in Test 2 (console output)")
    ap.add_argument("--seed1", type=int, default=42)
    ap.add_argument("--seed2", type=int, default=7)
    ap.add_argument("--max1", type=int, default=4000, help="--max-chunks used for Test 1")
    ap.add_argument("--max2", type=int, default=20000, help="--max-chunks used for Test 2")
    ap.add_argument("--regions", type=int, default=1382, help="region files in the world (console output)")
    ap.add_argument("--skipped1", default="13081", help="unfinished chunks skipped in Test 1")
    ap.add_argument("--skipped2", default="17349", help="unfinished chunks skipped in Test 2")
    ap.add_argument("--world", default="FlowMine")
    ap.add_argument("--modpack", default="Better Adventures+ (Flowstate, latest)")
    ap.add_argument("--mc-version", default="1.21.11")
    ap.add_argument("--dimension", default="Overworld")
    ap.add_argument("--slice", default="Z 2568, X 7168 to 8191", help="cross-section location text")
    ap.add_argument("--scan-date", default="26 Oct 2026")
    ap.add_argument("--out-dir", default="output")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    return a


def load(a):
    S1 = pd.read_csv(os.path.join(a.test1, "ore_summary.csv"))
    D1 = pd.read_csv(os.path.join(a.test1, "ore_by_y.csv"))
    S2 = pd.read_csv(os.path.join(a.test2, "ore_summary.csv"))
    D2 = pd.read_csv(os.path.join(a.test2, "ore_by_y.csv"))
    for D in (D1, D2):
        if "exposed" not in D.columns:
            D["exposed"] = 0
    return S1, D1, S2, D2


def load_layers(a, D2):
    """Rock and cave-wall counts per Y from layers_by_y.csv (scanner v2).

    Returns (layers DataFrame, exact). Older scans have no layer file: then every sampled block position
    is assumed to be rock (an under-estimate of the chance per rock block) and cave walls are unknown.
    """
    path = os.path.join(a.test2, "layers_by_y.csv")
    if os.path.exists(path):
        return pd.read_csv(path), True
    lo, hi = y_range(D2)
    ys = np.arange(lo, hi + 1)
    pos = np.full(len(ys), a.chunks2 * 256)
    return pd.DataFrame({"y": ys, "positions": pos, "rock": pos, "wall": 0}), False


def y_range(*dfs):
    lo = min([-64] + [int(d.y.min()) for d in dfs])
    hi = max([320] + [int(d.y.max()) for d in dfs])
    return lo, hi


def distributions(D, lo, hi):
    ys = np.arange(lo, hi + 1)
    return {o: g.set_index("y")["count"].reindex(ys, fill_value=0).astype(float) for o, g in D.groupby("ore")}


def best_band(series, width=5):
    """Start Y of the `width` consecutive layers holding the most ore (ties: lowest Y)."""
    roll = series.rolling(width).sum().shift(-(width - 1))
    return int(roll.idxmax())


def share(series, mask_fn):
    return 100.0 * series[mask_fn(series.index)].sum() / series.sum()


def facts(a, S1, S2, D2):
    lo, hi = y_range(D2)
    dist = distributions(D2, lo, hi)
    f = {"dist": dist, "lo": lo, "hi": hi}
    f["best"] = {o: best_band(s) for o, s in dist.items()}
    get = lambda o, fn: share(dist[o], fn) if o in dist else 0.0
    f["iron_high"] = get("iron_ore", lambda y: y >= 80)
    f["coal_high"] = get("coal_ore", lambda y: y >= 136)
    f["gold_high"] = get("gold_ore", lambda y: y > 32)
    f["coal_low"] = get("coal_ore", lambda y: y < 0)
    f["vanilla"] = [
        ("redstone_ore", '">16"', "Vanilla redstone stops at Y 15", get("redstone_ore", lambda y: y > 16)),
        ("lapis_ore", '">64"', "Vanilla lapis stops at Y 64", get("lapis_ore", lambda y: y > 64)),
        ("diamond_ore", '">16"', "Vanilla diamond stops at Y 16", get("diamond_ore", lambda y: y > 16)),
        ("copper_ore", '">112"', "Vanilla copper stops at Y 112", get("copper_ore", lambda y: y > 112)),
        ("iron_ore", (">=73", "<=77"), "Vanilla iron has an empty gap at Y 73 to 77",
         get("iron_ore", lambda y: (y >= 73) & (y <= 77))),
        ("coal_ore", '"<0"', "Vanilla coal starts at Y 0", get("coal_ore", lambda y: y < 0)),
    ]
    f["vanilla"] = [v for v in f["vanilla"] if v[0] in dist]
    s1, s2 = S1.set_index("ore"), S2.set_index("ore")
    f["pc1"], f["pc2"] = s1.total / a.chunks1, s2.total / a.chunks2
    common = s1.index.intersection(s2.index)
    f["pc_diff"] = ((f["pc2"][common] - f["pc1"][common]) / f["pc1"][common]).abs()
    f["med_diff"] = (s2.median_y[common] - s1.median_y[common]).abs()
    f["band_diff"] = pd.concat([(s2.p10_y[common] - s1.p10_y[common]).abs(),
                                (s2.p90_y[common] - s1.p90_y[common]).abs()], axis=1).max(axis=1)
    f["peak_diff"] = (s2.peak_y[common] - s1.peak_y[common]).abs()
    f["same_ores"] = set(s1.index) == set(s2.index)
    # Overlap of the diamond and redstone best bands (the "two-for-one" layer)
    f["combo"] = None
    if "diamond_ore" in f["best"] and "redstone_ore" in f["best"]:
        d, r = f["best"]["diamond_ore"], f["best"]["redstone_ore"]
        lo2, hi2 = max(d, r), min(d, r) + 4
        if lo2 <= hi2:
            f["combo"] = (lo2, hi2)
    # Layers within 10% of the best layer, after 5-layer smoothing (how flat the top is)
    f["flat_top"] = {}
    for o, s in dist.items():
        sm = s.rolling(5, center=True, min_periods=1).mean()
        top = sm[sm >= 0.9 * sm.max()].index
        f["flat_top"][o] = (int(top.min()), int(top.max()))
    return f


def tips(f, S2):
    s2 = S2.set_index("ore")
    b = f["best"]
    out = {}
    combo = f["combo"]
    combo_txt = (f"Y {combo[0]} to {combo[1]} is inside the best band for both diamond and redstone, so one tunnel "
                 "finds both.") if combo else ""
    for o in s2.index:
        t = ""
        if o == "coal_ore":
            t = (f"Easiest ore to find. About {f['coal_high']:.0f}% of coal forms a second band inside mountains "
                 "above Y 136.")
            if f["coal_low"] > 0.1:
                t += f" In this pack {f['coal_low']:.1f}% of coal is below Y 0, which vanilla does not do."
        elif o == "iron_ore":
            t = (f"Branch mine around Y {b[o] + 2}. About {f['iron_high']:.1f}% of all iron sits inside mountains "
                 "above Y 80, so tall mountains are worth tunnelling into.")
        elif o == "copper_ore":
            a_, z_ = f["flat_top"][o]
            t = (f"The band has a flat top: every layer from Y {a_} to Y {z_} is within 10% of the best, "
                 "so any of them works well.")
        elif o == "redstone_ore":
            t = "Sits at the very bottom of the world. " + (combo_txt or "Mine it just above bedrock.")
        elif o == "gold_ore":
            t = (f"Best around Y {b[o] + 2}. Badlands biomes (orange terracotta) add extra gold high up: "
                 f"about {f['gold_high']:.1f}% of all gold is above Y 32.")
        elif o == "diamond_ore":
            t = "Mine just above bedrock. " + (combo_txt or "")
        elif o == "lapis_ore":
            t = f"Centred near Y {int(s2.median_y[o])}, so a tunnel just under the deepslate line finds it."
        elif o == "emerald_ore":
            t = ("Mountain biomes only and very rare (less than 1 per chunk). Tunnel into tall mountains rather "
                 "than branch mining. Its single best layer moves a lot between samples because it is so rare.")
        else:
            t = f"Most of it is between Y {int(s2.p10_y[o])} and Y {int(s2.p90_y[o])}."
        out[o] = t.strip()
    return out


def quick_answer(f, order):
    return "   ".join(f"{nice(o)}: Y {f['best'][o]} to {f['best'][o] + 4}." for o in order)


def mining(f, D2, layers, exact, M=MINING):
    """Strip-mining and cave odds per ore. Same rules as the Mining Calc / Mining Odds sheets."""
    lo, hi = f["lo"], f["hi"]
    ys = np.arange(lo, hi + 1)
    L = layers.set_index("y").reindex(ys, fill_value=0)
    rock, wall = L["rock"].astype(float), L["wall"].astype(float)
    exp = {o: g.set_index("y")["exposed"].reindex(ys, fill_value=0).astype(float) for o, g in D2.groupby("ore")}
    rows = []
    for o, cnt in f["dist"].items():
        d = (cnt / rock.replace(0, np.nan)).fillna(0)
        dm1, dp1, dp2 = d.shift(1, fill_value=0), d.shift(-1, fill_value=0), d.shift(-2, fill_value=0)
        strip = 3 * d + 3 * dp1 + dm1 + dp2          # ore blocks seen per tunnel block, feet at Y
        sup_s = cnt.shift(1, fill_value=0) + cnt + cnt.shift(-1, fill_value=0) + cnt.shift(-2, fill_value=0)
        th_s = max(M["min_support"], M["min_support_frac"] * sup_s.max())
        strip = strip.where(sup_s >= th_s, 0)
        y_strip = int(strip.idxmax())
        s_best = float(strip.max())
        pace = M["stone_steps_per_min"] if y_strip >= 0 else M["deepslate_steps_per_min"]
        e5 = sum(exp[o].shift(-k, fill_value=0) for k in range(5))
        w5 = sum(wall.shift(-k, fill_value=0) for k in range(5))
        th_c = max(M["min_support"], M["min_support_frac"] * e5.max())
        cave = (e5 / w5.replace(0, np.nan)).fillna(0).where(e5 >= th_c, 0)
        has_cave = exact and wall.sum() > 0
        y_cave = int(cave.idxmax()) if has_cave and cave.max() > 0 else None
        c_best = float(cave.max()) if has_cave else None
        rows.append(dict(
            ore=o,
            strip_y=y_strip,
            strip_per_step=s_best,
            strip_chance=s_best / M["blocks_checked_per_step"],
            strip_per_100=100 * s_best,
            strip_per_hour=s_best * pace * 60,
            cave_y=y_cave,
            cave_chance=c_best,
            cave_per_hour=c_best * M["cave_wall_per_min"] * 60 if has_cave else None,
            avg_chance=float(cnt.sum() / rock.sum()) if exact else None,
            visible_pct=100 * float(exp[o].sum() / cnt.sum()) if exact else None,
        ))
    return pd.DataFrame(rows).set_index("ore")
