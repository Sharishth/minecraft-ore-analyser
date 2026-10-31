"""One-page ore infographic (PNG) from two ore_scan.py result sets.

Usage (from the project folder):
    python scripts/build_infographic.py --test1 output/test1 --test2 output/test2 --chunks1 3792 --chunks2 18960

Uses output/test2/cross_section.png (made by ore_scan.py) as the background slice when present.
"""
import os
import textwrap
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch, Rectangle

from matplotlib import font_manager

import common


def main(argv=None):
    """Build the infographic; argv as on the command line (None = sys.argv). Returns the saved file path."""
    # Same look everywhere: Inter if installed (free from Google Fonts), else Segoe UI (Windows), else DejaVu Sans.
    # A family only counts if a bold face is installed too (a variable-font-only Inter has none, and matplotlib
    # would then draw every heading in regular weight).
    def _weight(entry):
        return entry.weight if isinstance(entry.weight, int) else font_manager.weight_dict.get(entry.weight, 400)
    _bold = {f.name for f in font_manager.fontManager.ttflist if _weight(f) >= 600}
    FONT = next((f for f in ("Inter", "Segoe UI", "DejaVu Sans") if f in _bold), "DejaVu Sans")
    matplotlib.rcParams["font.family"] = FONT

    A = common.parse_args("Build the ore infographic", argv)
    S1df, D1, S2df, D2 = common.load(A)
    F = common.facts(A, S1df, S2df, D2)
    LAYERS, EXACT = common.load_layers(A, D2)
    MO = common.mining(F, D2, LAYERS, EXACT)
    MM = common.MINING
    S1, S2 = S1df.set_index("ore"), S2df.set_index("ore")
    CH1, CH2, REGIONS = A.chunks1, A.chunks2, A.regions
    LIM = common.LIMITS
    CO = {o: common.color(o, i) for i, o in enumerate(S2.index)}
    nice = common.nice

    INK, MUTED, BG, PANEL, LINE = "#1d2733", "#5b6774", "#eef1f5", "#ffffff", "#d5dbe2"
    DARK = "#1f2a36"

    # ---------- numbers (all from the CSVs, same rules as the workbook) ----------
    dist, best = F["dist"], F["best"]
    ys = dist[S2.index[0]].index.values
    iron_high, coal_high, gold_high, coal_low = F["iron_high"], F["coal_high"], F["gold_high"], F["coal_low"]
    pc1, pc2 = F["pc1"], F["pc2"]
    pc_diff, med_diff, band_diff, peak_diff = F["pc_diff"], F["med_diff"], F["band_diff"], F["peak_diff"]
    # Same 36 stability checks as the Test Cases sheet, as (passed, kind, ore or description).
    checks = [(CH1 >= LIM["min_chunks1"], "size", f"Test 1 has fewer than {LIM['min_chunks1']:,} chunks"),
              (CH2 >= LIM["min_chunks2"], "size", f"Test 2 has fewer than {LIM['min_chunks2']:,} chunks"),
              (CH2 / CH1 >= LIM["min_ratio"], "size", f"Test 2 is less than {LIM['min_ratio']}x Test 1"),
              (F["same_ores"], "size", "the tests found different ore types")]
    for kind, diff, lim in (("amount", pc_diff, LIM["pc_diff"]), ("median", med_diff, LIM["median"]),
                            ("range", band_diff, LIM["band"]), ("peak", peak_diff, LIM["peak"])):
        checks += [(bool(diff[o] <= lim), kind, o) for o in diff.index]
    n_pass = sum(ok for ok, _, _ in checks)
    n_fail = len(checks) - n_pass
    van = [v[3] for v in F["vanilla"]]
    n_match = sum(v <= 100 * LIM["stray"] for v in van)
    n_diff = len(van) - n_match
    total_blocks = int(S2.total.sum())
    per_chunk_all = total_blocks / CH2
    area = REGIONS * 512 * 512 / 1e6
    modded = [o for o in S2.index if ":" in o]

    # order by height (deepest first)
    ORDER = sorted(S2.index, key=lambda o: best[o])


    def plot_area(img):
        """Crop the cross_section.png made by ore_scan.py to its plot area (sky bbox + bottom spine)."""
        rgb = img[..., :3]
        sky = np.all(np.abs(rgb - np.array([0x9E, 0xC5, 0xF8]) / 255) < 0.03, axis=2)
        if not sky.any():
            return img
        rows, cols = np.nonzero(sky.any(axis=1))[0], np.nonzero(sky.any(axis=0))[0]
        top, left, right = rows.min(), cols.min(), cols.max()
        dark = rgb[:, left:right + 1].sum(axis=2) < 0.6
        spine = [r for r in range(top, rgb.shape[0]) if dark[r].mean() > 0.9]
        bottom = spine[-1] if spine else rgb.shape[0] - 1
        return img[top:bottom + 1, left:right + 1]


    # ---------- figure ----------
    # Sections are laid out on a 22.5 in tall base grid (y as a fraction of that grid). The mining odds panel is
    # inserted as an extra band of MINING_IN inches between the tips and the trust panel.
    W, H0 = 16, 22.5
    MINING_IN = 7.4
    SPLIT = 0.215          # base-grid y where the mining band is inserted
    H = H0 + MINING_IN
    fig = plt.figure(figsize=(W, H), dpi=120)
    fig.patch.set_facecolor(BG)


    def fy(f):
        """Base-grid y fraction -> figure fraction."""
        return (f * H0 + (MINING_IN if f >= SPLIT else 0)) / H


    def fh(h):
        return h * H0 / H


    def band(v):
        """Mining band local y (0 bottom, 1 top) -> figure fraction."""
        return (SPLIT * H0 + v * MINING_IN) / H


    def _box(x, y, w, h, fc, ec, r, lw, z):
        p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", transform=fig.transFigure,
                           fc=fc, ec=ec, lw=lw, zorder=z)
        fig.patches.append(p)
        return p


    def box(x, y, w, h, fc=PANEL, ec=LINE, r=0.006, lw=1.0, z=0):
        return _box(x, fy(y), w, fh(h), fc, ec, r, lw, z)


    def rect(x, y, w, h, **kw):
        fig.patches.append(Rectangle((x, fy(y)), w, fh(h), transform=fig.transFigure, **kw))


    def fit(t, maxw):
        """Shrink a text's font until it is at most `maxw` (figure fraction) wide, so any installed font fits."""
        if not maxw:
            return t
        r = fig.canvas.get_renderer()
        fw = fig.get_window_extent(r).width
        while t.get_window_extent(r).width > maxw * fw and t.get_fontsize() > 7:
            t.set_fontsize(t.get_fontsize() - 0.5)
        return t


    def text(x, y, s, maxw=None, **kw):
        kw.setdefault("color", INK)
        kw.setdefault("transform", fig.transFigure)
        return fit(fig.text(x, fy(y), s, **kw), maxw)


    def btext(x, v, s, maxw=None, **kw):
        kw.setdefault("color", INK)
        kw.setdefault("transform", fig.transFigure)
        return fit(fig.text(x, band(v), s, **kw), maxw)


    # header
    rect(0, 0.915, 1, 0.085, fc=DARK, ec="none")
    text(0.04, 0.962, f"{A.world.upper()} ORE GUIDE", fontsize=40, fontweight="bold", color="white", va="center")
    sub = ["Where to dig for every ore"] + ([A.modpack.split(" (")[0]] if A.modpack else [])
    text(0.04, 0.932, "  |  ".join(sub + [f"Minecraft {A.mc_version}", A.dimension]),
         fontsize=16, color="#c9d3de", va="center", maxw=0.68)
    text(0.96, 0.962, f"World seed: {A.world_seed}" if A.world_seed else "Scanned from the real save",
         fontsize=13, color="#c9d3de", ha="right", va="center")
    text(0.96, 0.937, "Y = height on the F3 screen", fontsize=13, color="#c9d3de", ha="right", va="center")

    # KPI tiles
    kpis = [
        (f"{CH2:,}", "chunks scanned", "Test 2 sample"),
        (f"{total_blocks / 1e6:.2f} M", "ore blocks counted", "in those chunks"),
        (f"{per_chunk_all:.0f}", "ore blocks per chunk", "all ores together"),
        (f"{REGIONS:,}", "region files", f"up to {area:.0f} sq km of map"),
        (f"{len(S2)}", "ore types found", f"{len(modded)} from mods" if modded else "no modded ores"),
    ]
    tw, gap, x0 = 0.172, 0.0125, 0.04
    for i, (big, lab, sub) in enumerate(kpis):
        x = x0 + i * (tw + gap)
        box(x, 0.835, tw, 0.065)
        text(x + 0.012, 0.876, big, fontsize=30, fontweight="bold", va="center")
        text(x + 0.012, 0.852, lab, fontsize=13, color=INK, va="center")
        text(x + 0.012, 0.842, sub, fontsize=10.5, color=MUTED, va="center")

    # main panel: real cross-section with ore lanes
    box(0.04, 0.385, 0.535, 0.435)
    text(0.055, 0.806, "Where each ore spawns", fontsize=20, fontweight="bold", va="center")
    text(0.055, 0.790, "Wider shape = more ore at that height. White line = best 5-layer band. "
         f"Background: a real slice of {A.world}.", fontsize=11, color=MUTED, va="center", maxw=0.505)
    ax = fig.add_axes([0.085, fy(0.425), 0.475, fh(0.355)])
    ax.set_zorder(5)
    sec_path = os.path.join(A.test2, "cross_section.png")
    if os.path.exists(sec_path):
        img = plot_area(mpimg.imread(sec_path))
        ax.imshow(img, extent=[0, len(ORDER), -64, 320], aspect="auto", alpha=0.55, zorder=0)
    else:
        ax.set_facecolor("#9ec5f8")
    for i, o in enumerate(ORDER):
        s = dist[o].rolling(5, center=True, min_periods=1).mean()
        w = 0.44 * s.values / s.values.max()
        cx = i + 0.5
        ax.fill_betweenx(ys, cx - w, cx + w, where=w > 0.004, color=CO[o], ec="white", lw=1.2, zorder=2)
        b = best[o] + 2
        ax.plot([cx - 0.47, cx + 0.47], [b, b], color="white", lw=4, zorder=3, solid_capstyle="round")
        ax.plot([cx - 0.47, cx + 0.47], [b, b], color=INK, lw=1.3, zorder=4)
        ax.text(cx, b + 9 if o != "emerald_ore" else b + 14, f"Y {best[o]}..{best[o] + 4}", ha="center",
                va="bottom", fontsize=10.5, fontweight="bold", color=INK, zorder=5,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.92))
    for yv, lab in [(63, "sea level 63"), (0, "deepslate starts ~0"), (-64, "bedrock -64")]:
        ax.axhline(yv, color="white", lw=1, ls=(0, (4, 3)), alpha=0.9, zorder=1)
    ax.set_xlim(0, len(ORDER))
    ax.set_ylim(F["lo"], F["hi"])
    ax.set_xticks([i + 0.5 for i in range(len(ORDER))])
    ax.set_xticklabels([nice(o) for o in ORDER], fontsize=11.5, fontweight="bold", color=INK)
    ax.set_yticks([-64, -32, 0, 32, 63, 96, 128, 160, 192, 224, 256, 288, 320])
    ax.set_yticklabels(["-64\nbedrock", "-32", "0", "32", "63\nsea", "96", "128", "160", "192", "224", "256",
                        "288", "320"], fontsize=10, color=MUTED)
    ax.set_ylabel("Y level (height)", fontsize=12, color=INK)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_color(LINE)

    # ore cards (highest at top, like the world)
    text(0.595, 0.806, "Mine here", fontsize=20, fontweight="bold", va="center")
    text(0.595, 0.790, "Best 5-layer band for each ore, highest first", fontsize=11, color=MUTED, va="center", maxw=0.36)
    card_h, card_gap, top = 0.0455, 0.0045, 0.778
    max_pc = pc2.max()
    for k, o in enumerate(reversed(ORDER)):
        y = top - (k + 1) * card_h - k * card_gap
        box(0.595, y, 0.365, card_h)
        # pixel-style ore icon
        ix, iy, isz = 0.603, y + 0.0095, 0.026
        rect(ix, iy, isz * H0 / W, isz, fc="#8a8a8a" if best[o] >= 0 else "#4b4b52", ec="#3a3a3a", lw=1, zorder=2)
        rng = np.random.default_rng(len(o))
        for _ in range(6):
            px, py = rng.uniform(0.15, 0.7, 2)
            rect(ix + px * isz * H0 / W, iy + py * isz, 0.25 * isz * H0 / W, 0.25 * isz, fc=CO[o], ec="none", zorder=3)
        text(0.645, y + card_h - 0.012, nice(o), fontsize=15, fontweight="bold", va="center", maxw=0.12)
        p10, p90 = int(S2.p10_y[o]), int(S2.p90_y[o])
        text(0.645, y + 0.012, f"80% of it: Y {p10} to {p90}", fontsize=10, color=MUTED, va="center", maxw=0.115)
        text(0.80, y + card_h / 2, f"Y {best[o]} to {best[o] + 4}", fontsize=17, fontweight="bold",
             va="center", ha="center", maxw=0.105)
        # abundance bar
        bx, bw = 0.868, 0.082
        rect(bx, y + 0.021, bw, 0.006, fc="#e3e7ec", ec="none", zorder=2)
        rect(bx, y + 0.021, max(bw * pc2[o] / max_pc, 0.0015), 0.006, fc=CO[o], ec="none", zorder=3)
        text(bx, y + 0.034, f"{pc2[o]:.1f} per chunk" if pc2[o] >= 1 else f"{pc2[o]:.2f} per chunk",
             fontsize=10.5, fontweight="bold", va="center")
        text(bx, y + 0.011, "rarest" if o == pc2.idxmin() else ("most common" if o == pc2.idxmax() else ""),
             fontsize=9.5, color=MUTED, va="center")

    # tips
    text(0.04, 0.362, "Pro tips from this world", fontsize=20, fontweight="bold", va="center")
    cands = []
    if F["combo"]:
        a_, z_ = F["combo"]
        cands.append((f"Y {a_} to {z_} is two-for-one",
                      f"The best bands for diamond (Y {best['diamond_ore']} to {best['diamond_ore'] + 4}) and redstone "
                      f"(Y {best['redstone_ore']} to {best['redstone_ore'] + 4}) overlap. One tunnel, two ores.",
                      CO["diamond_ore"]))
    if iron_high > 1 or coal_high > 1:
        cands.append(("Tunnel into mountains", f"{iron_high:.1f}% of all iron and {coal_high:.1f}% of coal sit high "
                      "inside mountains." + (" Emerald only spawns in mountain biomes." if "emerald_ore" in S2.index
                                             else ""), CO.get("emerald_ore", "#18c346")))
    if gold_high > 0.5:
        cands.append(("Badlands bonus gold", f"{gold_high:.1f}% of gold is above Y 32. That extra gold comes from "
                      "badlands (orange terracotta) biomes.", CO["gold_ore"]))
    if coal_low > 100 * LIM["stray"]:
        cands.append(("This pack is different", f"{coal_low:.1f}% of coal is below Y 0. In vanilla Minecraft coal "
                      "never spawns below Y 0.", CO["coal_ore"]))
    rare = S2.index[pc2[S2.index].argmin()]
    cands.append((f"{nice(rare)} is the rarest", f"Only {pc2[rare]:.2f} blocks per chunk. Its best band is "
                  f"Y {best[rare]} to {best[rare] + 4}.", CO[rare]))
    common_o = S2.index[pc2[S2.index].argmax()]
    cands.append((f"{nice(common_o)} is everywhere", f"{pc2[common_o]:.0f} blocks per chunk, best at "
                  f"Y {best[common_o]} to {best[common_o] + 4}.", CO[common_o]))
    tips = cands[:4]
    g2 = 0.0117
    tw2 = (0.92 - (len(tips) - 1) * g2) / len(tips)
    for i, (head, body, col) in enumerate(tips):
        x = 0.04 + i * (tw2 + g2)
        box(x, 0.225, tw2, 0.122)
        rect(x, 0.341, tw2, 0.006, fc=col, ec="none", zorder=2)
        text(x + 0.012, 0.322, head, fontsize=14.5, fontweight="bold", va="center")
        text(x + 0.012, 0.305, textwrap.fill(body, 36), fontsize=11.5, color=INK, va="top", linespacing=1.45)

    # mining odds panel (its own band between the tips and the trust panel)
    _box(0.04, band(0.03), 0.92, band(0.985) - band(0.03), PANEL, LINE, 0.006, 1.0, 0)
    btext(0.055, 0.935, "Mining odds: strip mine vs caves", fontsize=20, fontweight="bold", va="center")
    btext(0.055, 0.885,
          f"Strip mine = 1 wide, 2 tall tunnel; each block forward checks {MM['blocks_checked_per_step']} blocks. "
          f"Per hour assumes {MM['stone_steps_per_min']} tunnel blocks a minute in stone and "
          f"{MM['deepslate_steps_per_min']} in deepslate"
          + (f", and {MM['cave_wall_per_min']} cave-wall blocks looked at a minute in caves." if EXACT else "."),
          fontsize=11, color=MUTED, va="center", maxw=0.885)
    if not EXACT:
        _box(0.055, band(0.80), 0.89, band(0.855) - band(0.80), "#fef7e0", "#fef7e0", 0.004, 1.0, 1)
        btext(0.065, 0.8275, "Estimate: this scan did not count rock or cave walls. Strip odds below are a lower bound "
              "(every block position counted as rock). Cave odds need a rescan with the new ore_scan.py.",
              fontsize=11, color="#b06000", fontweight="bold", va="center", zorder=2, maxw=0.87)
    else:
        dm = MO.loc["diamond_ore"] if "diamond_ore" in MO.index else None
        if dm is not None and dm.cave_chance:
            ratio = dm.strip_chance / dm.cave_chance
            finding = (f"Key finding: for diamonds, strip mining gives {ratio:.1f}x better odds per block than looking at "
                       "cave walls, because the game often skips diamonds that would touch air.")
            _box(0.055, band(0.80), 0.89, band(0.855) - band(0.80), "#e6f4ea", "#e6f4ea", 0.004, 1.0, 1)
            btext(0.065, 0.8275, finding, fontsize=11.5, color="#1e6b34", fontweight="bold", va="center", zorder=2,
                  maxw=0.87)
    cols = [(0.065, "Ore", "left"), (0.215, "Tunnel at Y\n(feet)", "center"), (0.315, "Chance per\nblock checked", "center"),
            (0.425, "Ore per 100\ntunnel blocks", "center"), (0.555, "Ore per hour\n(strip mine)", "left"),
            (0.715, "Caves: best\nband from Y", "center"), (0.805, "Caves: chance\nper wall block", "center"),
            (0.905, "Ore per hour\n(caves)", "center")]
    hy = 0.735
    for x, lab, ha in cols:
        btext(x, hy, lab, fontsize=10.5, fontweight="bold", color=MUTED, ha=ha, va="center", linespacing=1.2)
    _box(0.055, band(0.69), 0.89, 0.0008, LINE, LINE, 0, 0.5, 1)
    order_hi = list(reversed(ORDER))
    row_h = 0.072
    max_ph = max(MO.strip_per_hour.max(), 1e-9)
    fmt_n = lambda p: f"1 in {1 / p:,.0f}" if p and p > 0 else "-"
    for k, o in enumerate(order_hi):
        v = 0.655 - k * row_h
        m = MO.loc[o]
        if k % 2 == 0:
            _box(0.055, band(v - row_h / 2), 0.89, band(v + row_h / 2) - band(v - row_h / 2), "#f6f8fa", "#f6f8fa",
                 0.003, 0.5, 0)
        fig.patches.append(Rectangle((0.065, band(v) - 0.0045), 0.0085 * H / W * 0.79, 0.009, transform=fig.transFigure,
                                     fc=CO[o], ec="#3a3a3a", lw=0.8, zorder=2))
        btext(0.082, v, nice(o), fontsize=13, fontweight="bold", va="center")
        btext(0.215, v, f"Y {int(m.strip_y)}", fontsize=13, fontweight="bold", ha="center", va="center")
        if m.strip_y >= 100:
            btext(0.215, v - 0.024, "inside mountains", fontsize=9, color=MUTED, ha="center", va="center")
        btext(0.315, v, fmt_n(m.strip_chance), fontsize=12, ha="center", va="center")
        btext(0.425, v, f"{m.strip_per_100:.2f}" if m.strip_per_100 < 10 else f"{m.strip_per_100:.1f}",
              fontsize=12, ha="center", va="center")
        bw = 0.085 * m.strip_per_hour / max_ph
        fig.patches.append(Rectangle((0.555, band(v) - 0.0035), max(bw, 0.001), 0.007, transform=fig.transFigure,
                                     fc=CO[o], ec="none", zorder=2))
        ph = m.strip_per_hour
        btext(0.555 + max(bw, 0.001) + 0.006, v, f"{ph:.1f}" if ph < 10 else f"{ph:.0f}", fontsize=12,
              fontweight="bold", va="center")
        if EXACT:
            btext(0.715, v, f"Y {int(m.cave_y)}" if m.cave_y is not None and m.cave_y == m.cave_y else "too few seen",
                  fontsize=12, ha="center", va="center")
            if m.cave_y is not None and m.cave_y == m.cave_y:
                btext(0.805, v, fmt_n(m.cave_chance), fontsize=12, ha="center", va="center")
                btext(0.905, v, f"{m.cave_per_hour:.1f}" if m.cave_per_hour < 10 else f"{m.cave_per_hour:.0f}",
                      fontsize=12, fontweight="bold", ha="center", va="center")
            else:
                for x in (0.805, 0.905):
                    btext(x, v, "-", fontsize=12, color=MUTED, ha="center", va="center")
        else:
            for x in (0.715, 0.805, 0.905):
                btext(x, v, "rescan", fontsize=11, color=MUTED, ha="center", va="center")
    btext(0.055, 0.065, "Ore per hour = ore blocks you can expect to see in one hour at that pace. Ores come in veins, "
          "so mining out the whole vein usually gives a little more. Edit the pace on the Mining Odds sheet.",
          fontsize=10.5, color=MUTED, va="center", maxw=0.885)

    # trust panel
    box(0.04, 0.075, 0.92, 0.13)
    text(0.055, 0.187, "Can you trust these numbers?", fontsize=20, fontweight="bold", va="center")
    md = int(med_diff.max())
    spread = f"ore amounts {100 * pc_diff.max():.1f}%, ore centres {md} block{'' if md == 1 else 's'}"
    agree = pc_diff.max() <= LIM["pc_diff"] and md <= LIM["median"]
    text(0.055, 0.166,
         f"Two separate random scans: Test 1 ({CH1:,} chunks) and Test 2 ({CH2:,} chunks). "
         + (f"They agree closely, at most: {spread}." if agree else
            f"Largest differences: {spread} (limits {100 * LIM['pc_diff']:.0f}% and {LIM['median']} blocks)."),
         fontsize=12, color=INK, va="center", maxw=0.89)
    tiles = [(n_pass, "PASS", "#1e8e3e", "#e6f4ea"), (n_fail, "FAIL", "#c5221f", "#fce8e6"),
             (n_match, "MATCH VANILLA", "#1e8e3e", "#e6f4ea"), (n_diff, "DIFFERS FROM VANILLA", "#b06000", "#fef7e0")]
    for i, (num, lab, fg, bgc) in enumerate(tiles):
        x = 0.055 + i * 0.118
        box(x, 0.09, 0.108, 0.056, fc=bgc, ec=bgc)
        text(x + 0.054, 0.126, f"{num}", fontsize=24, fontweight="bold", color=fg, ha="center", va="center")
        text(x + 0.054, 0.1, lab, fontsize=9.5, fontweight="bold", color=fg, ha="center", va="center")
    expl = f"{len(checks)} stability checks and {len(van)} vanilla-rule checks. "
    if n_fail:
        # Name every failed check by kind, so the text never blames the wrong one.
        def ores(kind):
            names = [nice(o) for ok, k, o in checks if k == kind and not ok]
            return ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
        labels = {"amount": "ore amount", "median": "centre (median)", "range": "80% range",
                  "peak": "best single layer"}
        parts = [d for ok, k, d in checks if k == "size" and not ok]
        parts += [f"{labels[k]} for {ores(k)}" for k in labels if ores(k)]
        expl += f"The {n_fail} fail{'s' if n_fail > 1 else ''}: {'; '.join(parts)}. "
        failed_ores = {o for ok, k, o in checks if k != "size" and not ok}
        rare = [nice(o) for o in failed_ores if pc2.get(o, 0) < 1]
        causes = (["small samples"] if any(k == "size" and not ok for ok, k, _ in checks) else []) + \
                 ([f"{', '.join(rare)} {'is' if len(rare) == 1 else 'are'} rare"] if rare else [])
        if any(k == "peak" and not ok and pc2.get(o, 0) >= 1 for ok, k, o in checks):
            causes.append("flat-topped bands move the single best layer")
        if causes:
            expl += f"Likely causes: {', '.join(causes)}. "
        expl += "Mine by the 5-layer bands rather than single layers. "
    differs = [nice(v[0]) for v in F["vanilla"] if v[3] > 100 * LIM["stray"]]
    expl += (f"Ores this pack changes from vanilla: {', '.join(differs)}." if differs
             else "Every ore follows the vanilla height rules.")
    # The panel holds 7 lines at 11.5 pt; a long list of fails steps down in size until it fits the box.
    for size, width in ((11.5, 62), (10.5, 68), (9.5, 76), (8.5, 85)):
        wrapped = textwrap.fill(expl, width)
        if len(wrapped.splitlines()) <= int(7 * 11.5 / size):
            break
    text(0.535, 0.146, wrapped, fontsize=size, color=INK, va="top", linespacing=1.45)

    # footer
    text(0.04, 0.045, "Limits: chunks you have already mined have less ore, and unfinished chunks at the edge of "
         "explored land were skipped. Amounts are per 16 x 16 chunk column.", fontsize=10.5, color=MUTED, maxw=0.92)
    text(0.04, 0.028, f"Source: ore_scan.py on the {A.world} save, {A.scan_date}. Full tables and test cases in "
         f"{A.world}_Ore_Report.xlsx.", fontsize=10.5, color=MUTED, maxw=0.92)

    out = os.path.join(A.out_dir, f"{A.world}_Ore_Infographic.png")
    fig.savefig(out, dpi=120, facecolor=BG)
    plt.close(fig)  # main() can run many times in one process (the GUI)
    print("saved", out, "| font", FONT, "| pass", n_pass, "fail", n_fail, "match", n_match, "differs", n_diff)
    return out


if __name__ == "__main__":
    main()
