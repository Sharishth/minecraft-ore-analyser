"""Automated checks for ore_scan.py and the report builders.

Run from the project folder:
    python tests/test_ore_scan.py

Builds two synthetic worlds with known ore placement, scans them, and checks:
  1. ore counts and Y levels are exact (4-bit and 5-bit block palettes)
  2. unfinished (proto) chunks are skipped
  3. modded ores keep their namespace, deepslate variants merge (and stay separate with --no-merge)
  4. the cross-section is drawn
  5. the world files are byte-for-byte unchanged after a scan (read-only)
  6. writing output inside the world folder is refused
  7. rock, cave-wall and visible-ore counts (layers_by_y.csv, exposed column) match the generator exactly
  8. build_report.py and build_infographic.py run on the bundled data and on exact (rescanned) data
"""
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = os.path.join(ROOT, "scripts", "ore_scan.py")
PY = sys.executable
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))


def run(*args, cwd=ROOT):
    return subprocess.run([PY, *args], cwd=cwd, capture_output=True, text=True)


def summary(path):
    with open(os.path.join(path, "ore_summary.csv")) as f:
        return {r["ore"]: r for r in csv.DictReader(f)}


def tree_hash(folder):
    h = {}
    for dp, _, fs in os.walk(folder):
        for fn in fs:
            p = os.path.join(dp, fn)
            with open(p, "rb") as f:
                h[os.path.relpath(p, folder)] = (hashlib.sha256(f.read()).hexdigest(), os.path.getmtime(p))
    return h


tmp = tempfile.mkdtemp(prefix="ore_scan_test_")
try:
    w1, w2 = os.path.join(tmp, "world_simple"), os.path.join(tmp, "world_terrain")
    run(os.path.join(ROOT, "tests", "make_world.py"), w1)
    run(os.path.join(ROOT, "tests", "make_terrain.py"), w2)

    # 1-2. exact counts on the simple world (10 full chunks + 1 proto chunk)
    before = tree_hash(w1)
    out1 = os.path.join(tmp, "out1")
    r = run(SCAN, w1, "--out", out1)
    check("scan of simple world runs", r.returncode == 0, r.stderr[-300:])
    s = summary(out1)
    check("diamond: 30 blocks at Y -58", s["diamond_ore"]["total"] == "30" and s["diamond_ore"]["peak_y"] == "-58")
    check("iron: 50 blocks at Y 16", s["iron_ore"]["total"] == "50" and s["iron_ore"]["peak_y"] == "16")
    check("modded ore keeps namespace (create:zinc_ore, 70 at Y 200)",
          s.get("create:zinc_ore", {}).get("total") == "70" and s["create:zinc_ore"]["peak_y"] == "200")
    check("unfinished chunk skipped", "skipped_not_fully_generated: 1" in r.stdout, r.stdout)
    check("deepslate variant merged into diamond_ore", "deepslate_diamond_ore" not in s)

    # 3. --no-merge keeps the deepslate name
    out1b = os.path.join(tmp, "out1b")
    run(SCAN, w1, "--out", out1b, "--no-merge")
    check("--no-merge keeps deepslate_diamond_ore", "deepslate_diamond_ore" in summary(out1b))

    # 5. read-only
    check("world files unchanged after scans", tree_hash(w1) == before)

    # 6. refuse output inside the world
    r = run(SCAN, w1, "--out", os.path.join(w1, "results"))
    check("output inside world folder refused", r.returncode != 0 and "inside the world folder" in (r.stdout + r.stderr))
    check("nothing written into the world", tree_hash(w1) == before)

    # terrain world: compare with a direct count from the generator
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import numpy as np
    import make_terrain as mt
    rng = np.random.default_rng(1)
    expected = {}
    for cz, xs in [(4, range(32)), (10, range(0, 32, 4))]:
        for cx in xs:
            for lz in range(16):
                for lx in range(16):
                    col = mt.column_blocks(cx * 16 + lx, cz * 16 + lz, rng)
                    for v in col:
                        n = mt.NAMES[v]
                        if n.endswith("_ore"):
                            key = n.split(":")[1].replace("deepslate_", "")
                            expected[key] = expected.get(key, 0) + 1
    out2 = os.path.join(tmp, "out2")
    r = run(SCAN, w2, "--out", out2)
    s2 = summary(out2)
    got = {k: int(v["total"]) for k, v in s2.items()}
    check("terrain world counts match generator exactly", got == expected, f"{got} vs {expected}")
    # 4. cross-section
    check("cross-section picked the generated row (Z=72)", "cross-section: Z=72" in r.stdout, r.stdout)
    check("cross_section.png and ore_chart.png written",
          all(os.path.exists(os.path.join(out2, f)) for f in ("cross_section.png", "ore_chart.png")))

    # 7. rock, cave walls and visible ore
    see_ids = {mt.NAMES.index(n) for n in ("minecraft:air", "minecraft:cave_air", "minecraft:water")}
    rng = np.random.default_rng(1)
    rock_exp, wall_exp, vis_exp = np.zeros(384, int), np.zeros(384, int), {}
    for cz, xs in [(4, range(32)), (10, range(0, 32, 4))]:
        for cx in xs:
            vol = np.zeros((384, 16, 16), int)
            for lz in range(16):
                for lx in range(16):
                    vol[:, lz, lx] = mt.column_blocks(cx * 16 + lx, cz * 16 + lz, rng)
            see = np.isin(vol, list(see_ids))
            nb = np.zeros_like(see)
            nb[1:] |= see[:-1]; nb[:-1] |= see[1:]
            nb[:, 1:] |= see[:, :-1]; nb[:, :-1] |= see[:, 1:]
            nb[:, :, 1:] |= see[:, :, :-1]; nb[:, :, :-1] |= see[:, :, 1:]
            rock_exp += (~see).sum(axis=(1, 2))
            wall_exp += (~see & nb).sum(axis=(1, 2))
            for i, n in enumerate(mt.NAMES):
                if n.endswith("_ore"):
                    k = n.split(":")[1].replace("deepslate_", "")
                    vis_exp[k] = vis_exp.get(k, 0) + int(((vol == i) & nb).sum())
    with open(os.path.join(out2, "layers_by_y.csv")) as f:
        lay = {int(r["y"]): r for r in csv.DictReader(f)}
    rock_got = np.array([int(lay[y]["rock"]) for y in range(-64, 320)])
    wall_got = np.array([int(lay[y]["wall"]) for y in range(-64, 320)])
    check("rock blocks per Y match generator", (rock_got == rock_exp).all())
    check("cave-wall blocks per Y match generator", (wall_got == wall_exp).all())
    vis_got = {}
    with open(os.path.join(out2, "ore_by_y.csv")) as f:
        for r in csv.DictReader(f):
            vis_got[r["ore"]] = vis_got.get(r["ore"], 0) + int(r["exposed"])
    check("ore visible from caves matches generator", vis_got == vis_exp, f"{vis_got} vs {vis_exp}")

    # 8. report builders: bundled data (estimate mode) and the rescanned terrain world (exact mode)
    rep_out = os.path.join(tmp, "reports")
    r = run(os.path.join(ROOT, "scripts", "build_report.py"), "--out-dir", rep_out)
    check("build_report.py runs on bundled data", r.returncode == 0, r.stderr[-300:])
    r = run(os.path.join(ROOT, "scripts", "build_infographic.py"), "--out-dir", rep_out)
    check("build_infographic.py runs on bundled data", r.returncode == 0, r.stderr[-300:])
    check("report files written", all(os.path.exists(os.path.join(rep_out, f)) for f in
                                      ("FlowMine_Ore_Report.xlsx", "FlowMine_Ore_Infographic.png")))
    ex_args = ["--test1", out2, "--test2", out2, "--chunks1", "40", "--chunks2", "40", "--world", "Synth",
               "--out-dir", rep_out]
    r1 = run(os.path.join(ROOT, "scripts", "build_report.py"), *ex_args)
    r2 = run(os.path.join(ROOT, "scripts", "build_infographic.py"), *ex_args)
    check("builders run on exact data (with cave odds)", r1.returncode == 0 and r2.returncode == 0,
          (r1.stderr + r2.stderr)[-300:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
sys.exit(1 if failed else 0)
