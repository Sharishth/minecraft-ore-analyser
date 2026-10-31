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
  8. build_report.py and build_infographic.py run on the bundled example (example/) and on exact
     (rescanned) data, taking every scan fact from world_info.json
  9. Minecraft version and world seed are read from the save (both the 1.21 and the 26.x file layouts),
     a Minecraft 26.x world (dimensions/ folders, new palette formats) scans to the same counts,
     and the report shows the seed
 10. --mc-version forces a save format (and fails clearly when it does not match the save);
     mc_formats lists releases newest first and maps them to the right format family
 11. the desktop app's pipeline (ore_analyser_gui.run_pipeline) scans and builds without any UI
"""
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = os.path.join(ROOT, "scripts", "ore_scan.py")
EXAMPLE = os.path.join(ROOT, "example")
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
    legacy_totals = {k: v["total"] for k, v in s.items()}

    # 9. version and seed from level.dat, and a Minecraft 26.x world
    def world_info(out):
        with open(os.path.join(out, "world_info.json")) as f:
            return json.load(f)
    wi = world_info(out1)
    check("world_info.json: version and seed read from level.dat",
          wi["mc_version"] == "1.21.4" and wi["world_seed"] == "987654321" and wi["data_version"] == 3955, str(wi))
    check("scan prints the world version and seed", "Minecraft 1.21.4" in r.stdout and "seed 987654321" in r.stdout,
          r.stdout)
    w3 = os.path.join(tmp, "world_new")
    run(os.path.join(ROOT, "tests", "make_world.py"), w3, "--new")
    out3 = os.path.join(tmp, "out3")
    r3 = run(SCAN, w3, "--out", out3)  # default --dim overworld must find dimensions/minecraft/overworld/region
    check("26.x world: dimensions/ folder layout found with --dim overworld", r3.returncode == 0, r3.stdout + r3.stderr)
    check("26.x world: all three palette formats give the same counts as the 1.21 world",
          {k: v["total"] for k, v in summary(out3).items()} == legacy_totals if r3.returncode == 0 else False)
    wi3 = world_info(out3) if r3.returncode == 0 else {}
    check("26.x world: version and negative seed read (seed from world_gen_settings.dat)",
          wi3.get("mc_version") == "26.3" and wi3.get("world_seed") == "-1234567890123456789", str(wi3))
    w4 = os.path.join(tmp, "world_nolevel")
    shutil.copytree(w1, w4)
    os.remove(os.path.join(w4, "level.dat"))
    out4 = os.path.join(tmp, "out4")
    r4 = run(SCAN, w4, "--out", out4)
    wi4 = world_info(out4) if r4.returncode == 0 else {}
    check("save without level.dat still scans, version and seed unknown",
          r4.returncode == 0 and wi4.get("mc_version") is None and wi4.get("world_seed") is None, r4.stdout + r4.stderr)
    sc = wi.get("scan", {})
    check("world_info.json records the scan facts the builders need",
          sc.get("chunks") == 10 and sc.get("region_files") == 1 and sc.get("skipped_not_fully_generated") == 1
          and sc.get("sample_seed") == 42, str(sc))

    # 10. forcing the Minecraft version
    out5 = os.path.join(tmp, "out5")
    r5 = run(SCAN, w3, "--out", out5, "--mc-version", "26.1")
    wi5 = world_info(out5) if r5.returncode == 0 else {}
    check("--mc-version 26.1 on a 26.3 save: same format family layout, version recorded as forced",
          r5.returncode == 0 and wi5.get("mc_version") == "26.1" and wi5.get("detected_version") == "26.3"
          and wi5.get("version_source") == "--mc-version" and "using 26.1 as asked" in r5.stdout,
          r5.stdout + r5.stderr)
    r6 = run(SCAN, w3, "--out", os.path.join(tmp, "out6"), "--mc-version", "1.21.11")
    check("--mc-version 1.21.11 on a 26.x save stops with a clear message (old layout not there)",
          r6.returncode != 0 and "forced by --mc-version" in r6.stdout + r6.stderr, r6.stdout + r6.stderr)
    r7 = run(SCAN, w1, "--out", os.path.join(tmp, "out7"), "--mc-version", "1.20.4")
    check("--mc-version 1.20.4 on a 1.21 save scans (same format family)", r7.returncode == 0, r7.stderr[-300:])
    r8 = run(SCAN, w1, "--out", os.path.join(tmp, "out8"), "--mc-version", "1.17")
    check("--mc-version rejects versions without a supported format", r8.returncode != 0)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import mc_formats
    import ore_scan
    dates = {v: d for v, d, _ in mc_formats.RELEASES}
    vs = mc_formats.versions()
    check("version list is newest release first", vs[0] == "26.3" and vs[-1] == "1.18"
          and all(dates[a] >= dates[b] for a, b in zip(vs, vs[1:])))
    fam = lambda v: mc_formats.family_for_version(v).key
    check("versions map to their save-format family",
          (fam("1.18"), fam("1.21.11"), fam("26.1"), fam("26.2"), fam("26.3"), fam("26.4"))
          == ("anvil-1.18", "anvil-1.18", "dims-26.1", "dims-26.1", "ids-26.3", "ids-26.3"))
    check("chunk status read from Status and from 26.4's lowercase status",
          ore_scan.is_full({"Status": "minecraft:full"}) and ore_scan.is_full({"status": "minecraft:full"})
          and not ore_scan.is_full({"status": "minecraft:features"}))

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

    # 8. report builders: bundled example (estimate mode) and the rescanned terrain world (exact mode)
    rep_out = os.path.join(tmp, "reports")
    ex = ["--test1", os.path.join(EXAMPLE, "test1"), "--test2", os.path.join(EXAMPLE, "test2"), "--out-dir", rep_out]
    r = run(os.path.join(ROOT, "scripts", "build_report.py"), *ex)
    check("build_report.py runs on the bundled example", r.returncode == 0, r.stderr[-300:])
    r = run(os.path.join(ROOT, "scripts", "build_infographic.py"), *ex)
    check("build_infographic.py runs on the bundled example", r.returncode == 0, r.stderr[-300:])
    check("report files written", all(os.path.exists(os.path.join(rep_out, f)) for f in
                                      ("FlowMine_Ore_Report.xlsx", "FlowMine_Ore_Infographic.png")))
    # Only --world is given; chunk counts and the rest come from the scan's world_info.json.
    ex_args = ["--test1", out2, "--test2", out2, "--world", "Synth", "--out-dir", rep_out]
    r1 = run(os.path.join(ROOT, "scripts", "build_report.py"), *ex_args)
    r2 = run(os.path.join(ROOT, "scripts", "build_infographic.py"), *ex_args)
    check("builders run on exact data (with cave odds)", r1.returncode == 0 and r2.returncode == 0,
          (r1.stderr + r2.stderr)[-300:])
    from openpyxl import load_workbook
    wb = load_workbook(os.path.join(rep_out, "Synth_Ore_Report.xlsx"))
    cells = [c.value for row in wb["World Details"].iter_rows() for c in row]
    check("report shows the Minecraft version and world seed from the scan",
          "4242424242" in cells and "1.21.11" in cells, str([c for c in cells if c is not None][:40]))
    wd = wb["World Details"]
    check("report takes chunk and region counts from world_info.json",  # B9 regions, B11/B13 chunks
          (wd["B9"].value, wd["B11"].value, wd["B13"].value) == (1, 40, 40),
          str((wd["B9"].value, wd["B11"].value, wd["B13"].value)))

    # 11. desktop app pipeline, without opening a window
    sys.path.insert(0, ROOT)
    import contextlib
    import io
    import ore_analyser_gui as gui
    found, msg = gui.find_world(tmp)
    check("app: a folder with several worlds asks to pick one", found is None and "worlds" in msg, msg)
    check("app: a world folder is used as is", gui.find_world(w2)[0] == w2)
    app_out = os.path.join(tmp, "app_out")
    settings = {"world": w2, "out": app_out, "dim": "overworld", "mc_version": None, "modpack": "Test pack",
                "chunks1": 20, "chunks2": 40}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rep_path, png_path = gui.run_pipeline(settings, log=lambda _m: None)
        ok = os.path.exists(rep_path) and os.path.exists(png_path)
        err = ""
    except Exception as e:  # report the failure as a check, keep running the rest
        ok, err = False, repr(e)
    check("app: run_pipeline scans twice and writes report and infographic", ok, err)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            gui.run_pipeline({**settings, "mc_version": "1.21.11", "world": w3,
                              "out": os.path.join(tmp, "app_bad")}, log=lambda _m: None)
        stopped = ""
    except RuntimeError as e:
        stopped = str(e)
    check("app: a step that stops is reported as a readable error", "Test 1 scan stopped" in stopped, stopped)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
sys.exit(1 if failed else 0)
