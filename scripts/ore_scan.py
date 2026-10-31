"""
Scan a Minecraft world (1.18+ chunk format) and chart ore count per Y level.
Reads the real blocks in your region files, so modded ores, custom terrain
and floating islands are all counted as they actually generated.

The chart background is a real vertical slice (cross-section) of your world,
also saved on its own as cross_section.png.

The world is only ever opened read-only. Nothing in the save is modified.

Install:  pip install -r requirements.txt
Run:      python scripts/ore_scan.py "path/to/world" --dim overworld --out output/scan
Output:   ore_by_y.csv, ore_summary.csv, layers_by_y.csv, world_info.json, ore_chart.png, cross_section.png

Tips:
- Close the world (or copy the save folder) before scanning.
- Chunks you have mined in are missing ore. For clean numbers, pregenerate a
  fresh area with the same seed (for example with the Chunky mod) and scan that.
- Pick the slice location with --slice-x / --slice-z (block coordinates,
  as shown on the F3 screen). Without them the script picks a well-generated area.
- The Minecraft version is read from level.dat. If that is wrong or missing, force it with
  --mc-version (see mc_formats.py for the save formats behind each version).

Use from Python: ore_scan.main([world, "--out", folder, ...]) returns the world_info dict.
"""
import argparse, datetime, io, json, os, re, zlib, gzip, struct, glob, random
from collections import defaultdict, Counter
import numpy as np
import nbtlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba

import mc_formats

DEFAULT_PATTERN = r"(_ore$|^minecraft:ancient_debris$)"
# Host-rock variants merged into one ore name (deepslate_iron_ore -> iron_ore).
PREFIX_RE = re.compile(r"^(deepslate|nether|end|end_stone|netherrack|blackstone|basalt)_")
SUFFIX_RE = re.compile(r"_(deepslate|nether|end)(?=_ore$)")
FULL_STATUS = {"minecraft:full", "full"}  # chunk generation finished: every ore is placed
COMP_NAMES = {4: "LZ4", 127: "custom"}

ORE_COLORS = {
    "coal_ore": "#1c1c1c", "iron_ore": "#d8af93", "copper_ore": "#e2793f",
    "gold_ore": "#f6d33c", "redstone_ore": "#e3141b", "lapis_ore": "#2c4fd1",
    "diamond_ore": "#4ee6de", "emerald_ore": "#18c346", "quartz_ore": "#ece4d6",
    "ancient_debris": "#6b4a3a",
}
AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
# First substring match wins, so specific names come before general ones.
BLOCK_RULES = [
    ("bedrock", "#2b2b2b"), ("lava", "#e8641c"), ("water", "#3f76e4"),
    ("kelp", "#3f76e4"), ("seagrass", "#3f76e4"), ("bubble_column", "#3f76e4"),
    ("packed_ice", "#8fb4ef"), ("blue_ice", "#74a8f0"), ("ice", "#a5c8f5"),
    ("snow", "#f4f8fb"), ("deepslate", "#4b4b52"), ("tuff", "#62645c"),
    ("grass_block", "#6aa84f"), ("moss", "#5c7a2e"), ("leaves", "#3a7326"),
    ("log", "#6b5233"), ("wood", "#6b5233"), ("grass", "#7cb35c"), ("fern", "#7cb35c"),
    ("red_sand", "#b9682e"), ("sandstone", "#d6c88f"), ("sand", "#dccf9c"),
    ("terracotta", "#a65e3c"), ("podzol", "#6b4b2a"), ("mud", "#3c3837"),
    ("dirt", "#8b6a46"), ("clay", "#9fa4b0"), ("gravel", "#857f7a"),
    ("granite", "#9a6b57"), ("diorite", "#c6c6c6"), ("andesite", "#8a8a8a"),
    ("calcite", "#e0e0dc"), ("dripstone", "#86684f"), ("amethyst", "#8a64c4"),
    ("obsidian", "#1b1426"), ("netherrack", "#6e2a2a"), ("end_stone", "#dbdea0"),
    ("stone", "#7d7d7d"),
]
DEFAULT_BLOCK = "#808080"
SKY = "#9ec5f8"
CAVE = to_rgba("#26262b")
MISSING = to_rgba("#d9d9d9", 0.6)


def ore_name(block_id, merge):
    ns, _, n = block_id.partition(":")
    if not n:
        ns, n = "minecraft", ns
    if merge:
        n = SUFFIX_RE.sub("", PREFIX_RE.sub("", n))
    return n if ns == "minecraft" else f"{ns}:{n}"


VANILLA_DIMS = {"overworld": "minecraft:overworld", "nether": "minecraft:the_nether", "end": "minecraft:the_end"}
LEGACY_FOLDERS = {"minecraft:overworld": "", "minecraft:the_nether": "DIM-1", "minecraft:the_end": "DIM1"}


def region_dir(world, dim, family=None):
    """Region folder of a dimension.

    Minecraft 26.1+ keeps every dimension under dimensions/<namespace>/<name>; older saves use region, DIM-1
    and DIM1 for the three vanilla dimensions. With a forced format family that layout is used as is;
    otherwise the new layout wins when its folder exists.
    """
    dim = VANILLA_DIMS.get(dim, dim)
    new = os.path.join(world, "dimensions", *dim.split(":"), "region")
    old = LEGACY_FOLDERS.get(dim)
    if old is None:  # modded dimension: dimensions/<namespace>/<name> in every version
        return new
    if family is not None:
        return new if family.layout == "dimensions" else os.path.join(world, old, "region")
    return new if os.path.isdir(new) else os.path.join(world, old, "region")


def list_dimensions(world):
    """Dimensions of a save that have region files, as --dim values (vanilla ones first)."""
    found = [short for short in VANILLA_DIMS if glob.glob(os.path.join(region_dir(world, short), "r.*.mca"))]
    for d in sorted(glob.glob(os.path.join(world, "dimensions", "*", "*", "region"))):
        ns, name = os.path.normpath(d).split(os.sep)[-3:-1]
        if f"{ns}:{name}" not in VANILLA_DIMS.values() and glob.glob(os.path.join(d, "r.*.mca")):
            found.append(f"{ns}:{name}")
    return found


def _load_nbt(path):
    try:
        return nbtlib.load(path)  # opens the file read-only; gzip is detected automatically
    except Exception:
        return None


def read_world_info(world, family=None):
    """Version and seed of a save. Fields that cannot be found stay None.

    The seed is in data/minecraft/world_gen_settings.dat from 26.1, in level.dat Data.WorldGenSettings.seed
    from 1.16, and in level.dat Data.RandomSeed before that. A forced family only looks in its own place.
    """
    info = {"level_name": None, "mc_version": None, "data_version": None, "world_seed": None}
    lvl = _load_nbt(os.path.join(world, "level.dat"))
    data = lvl.get("Data") if lvl is not None else None
    if data is None:
        data = {}
    if "LevelName" in data:
        info["level_name"] = str(data["LevelName"])
    if "Name" in data.get("Version", {}):
        info["mc_version"] = str(data["Version"]["Name"])
    if "DataVersion" in data:
        info["data_version"] = int(data["DataVersion"])
    seed = None
    if family is None or family.seed_file == "world_gen_settings.dat":
        gen = _load_nbt(os.path.join(world, "data", "minecraft", "world_gen_settings.dat"))
        if gen is not None and "seed" in gen.get("data", {}):
            seed = gen["data"]["seed"]
    if seed is None and (family is None or family.seed_file == "level.dat"):
        if "seed" in data.get("WorldGenSettings", {}):
            seed = data["WorldGenSettings"]["seed"]
        elif "RandomSeed" in data:
            seed = data["RandomSeed"]
    if seed is not None:
        info["world_seed"] = str(int(seed))  # text, so Excel never rounds a 19-digit seed
    return info


def version_warning(info):
    dv = info["data_version"]
    if dv is None:
        return "no version in level.dat; the folder layout is detected and chunks are decoded by shape"
    if dv < mc_formats.FIRST_SUPPORTED_DATA_VERSION:
        return "this world is older than Minecraft 1.18; its chunk format is not supported"
    if dv > mc_formats.NEWEST_TESTED_DATA_VERSION:
        return ("this world is newer than the newest version tested "
                f"(data version {mc_formats.NEWEST_TESTED_DATA_VERSION}); check the results")
    return None


def palette_name(entry):
    """Block id of a palette entry.

    Up to 1.21 an entry is {"Name": id, "Properties": ...}. Minecraft 26.x writes a plain id string, or an
    object holding {"": id} or {"id": id, "properties": ...}.
    """
    if isinstance(entry, dict):
        for key in ("Name", "id", ""):
            if key in entry:
                return str(entry[key])
    return str(entry)


def decompress(comp, raw, stats):
    try:
        if comp == 1:
            return gzip.decompress(raw)
        if comp == 2:
            return zlib.decompress(raw)
        if comp == 3:
            return raw
    except Exception:
        stats["corrupt"] += 1
        return None
    stats[f"skipped_{COMP_NAMES.get(comp, comp)}_compression"] += 1
    return None


def chunk_payload(buf_or_file, off, stats):
    """Read one chunk payload at sector offset. Works on bytes or an open file."""
    if isinstance(buf_or_file, (bytes, bytearray)):
        hdr = buf_or_file[off * 4096:off * 4096 + 5]
    else:
        buf_or_file.seek(off * 4096)
        hdr = buf_or_file.read(5)
    if len(hdr) < 5:
        stats["corrupt"] += 1
        return None
    length, comp = struct.unpack(">IB", hdr)
    if length < 2 or comp & 0x80:  # empty, or stored in an external .mcc file
        stats["skipped_external_or_empty"] += 1
        return None
    if isinstance(buf_or_file, (bytes, bytearray)):
        raw = buf_or_file[off * 4096 + 5:off * 4096 + 4 + length]
    else:
        raw = buf_or_file.read(length - 1)
    return decompress(comp, raw, stats)


def read_chunks(path, rng, stats):
    """Yield decompressed chunk NBT bytes, in random order within the file."""
    with open(path, "rb") as f:  # read-only
        header = f.read(8192)
        if len(header) < 8192:
            return
        order = list(range(1024))
        rng.shuffle(order)  # avoid sampling only the first rows of each region
        for i in order:
            off = struct.unpack(">I", header[i * 4:i * 4 + 4])[0] >> 8
            if off < 2:
                continue
            raw = chunk_payload(f, off, stats)
            if raw is not None:
                yield raw


def unpack_states(data_tag, n_palette):
    """Unpack a block_states data long array into 4096 palette indices."""
    data = np.asarray(data_tag, dtype=np.int64).view(np.uint64)
    bits = max(4, (n_palette - 1).bit_length())
    per = 64 // bits
    if len(data) < -(-4096 // per):
        raise ValueError("short block_states data")
    idx = np.arange(4096)
    mask = np.uint64((1 << bits) - 1)
    shift = ((idx % per) * bits).astype(np.uint64)
    return ((data[idx // per] >> shift) & mask).astype(np.int64)


def is_full(nbt):
    # 26.4 renames the field from Status to status
    return str(nbt.get("Status", nbt.get("status", ""))) in FULL_STATUS


SEE_THROUGH = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:water",
               "minecraft:bubble_column"}
NOT_ROCK = {"minecraft:lava"}  # open, but you cannot see ore through it


class Acc:
    """Accumulates per-Y counts across chunks.

    counts[ore][y]   ore blocks
    exposed[ore][y]  ore blocks touching air or water (visible from a cave, ravine or cliff)
    layers[y]        [positions, rock, wall]: block positions sampled, rock blocks (anything you can mine),
                     wall blocks (rock touching air or water, what you see while exploring caves)
    """

    def __init__(self):
        self.counts = defaultdict(lambda: defaultdict(int))
        self.exposed = defaultdict(lambda: defaultdict(int))
        self.layers = defaultdict(lambda: np.zeros(3, dtype=np.int64))
        self.ore_names = []
        self.ore_ids = {}

    def ore_id(self, name):
        if name not in self.ore_ids:
            self.ore_ids[name] = len(self.ore_names)
            self.ore_names.append(name)
        return self.ore_ids[name]


def scan_chunk(raw, acc, ore_re, merge, stats):
    nbt = nbtlib.File.parse(io.BytesIO(raw))
    sections = nbt.get("sections")
    if sections is None:
        stats["skipped_pre_1.18_format"] += 1
        return False
    if not is_full(nbt):
        stats["skipped_not_fully_generated"] += 1  # ores not placed yet
        return False
    secs = []
    for sec in sections:
        bs = sec.get("block_states")
        if bs is not None and "palette" in bs:
            secs.append((int(sec["Y"]), bs))
    if not secs:
        return True
    smin = min(sy for sy, _ in secs)
    smax = max(sy for sy, _ in secs)
    # Block class per position: 0 rock, 1 see-through (air/water), 2 lava, 3+ ore (3 + ore id).
    # A missing section counts as air. Array axes: [y, z, x], block index = y*256 + z*16 + x.
    cls = np.ones(((smax - smin + 1) * 16, 16, 16), dtype=np.int32)
    for sy, bs in secs:
        palette = [palette_name(p) for p in bs["palette"]]
        pc = np.zeros(len(palette), dtype=np.int32)
        for i, n in enumerate(palette):
            if ore_re.search(n):
                pc[i] = 3 + acc.ore_id(ore_name(n, merge))
            elif n in SEE_THROUGH:
                pc[i] = 1
            elif n in NOT_ROCK:
                pc[i] = 2
        k = (sy - smin) * 16
        if "data" not in bs:  # single-block section, all 4096 blocks are palette[0]
            cls[k:k + 16] = pc[0]
            continue
        try:
            vals = unpack_states(bs["data"], len(palette))
        except ValueError:
            stats["corrupt_sections"] += 1
            cls[k:k + 16] = 0  # unreadable section: counted as plain rock, so it adds no ore
            continue
        cls[k:k + 16] = pc[vals].reshape(16, 16, 16)
    see = cls == 1
    # Neighbour of a see-through block (6 faces). Neighbours in other chunks are unknown and
    # count as not see-through, so exposure is very slightly under-counted at chunk edges.
    nb = np.zeros_like(see)
    nb[1:] |= see[:-1]
    nb[:-1] |= see[1:]
    nb[:, 1:] |= see[:, :-1]
    nb[:, :-1] |= see[:, 1:]
    nb[:, :, 1:] |= see[:, :, :-1]
    nb[:, :, :-1] |= see[:, :, 1:]
    rock = (cls == 0) | (cls >= 3)
    y0 = smin * 16
    rock_y = rock.sum(axis=(1, 2))
    wall_y = (rock & nb).sum(axis=(1, 2))
    for i in range(cls.shape[0]):
        lay = acc.layers[y0 + i]
        lay[0] += 256
        lay[1] += rock_y[i]
        lay[2] += wall_y[i]
    ore = cls >= 3
    if ore.any():
        H = cls.shape[0]
        n_ore = len(acc.ore_names)
        yy = np.nonzero(ore)[0]
        ids = cls[ore] - 3
        c = np.bincount(ids * H + yy, minlength=n_ore * H).reshape(n_ore, H)
        exp_mask = nb[ore]
        e = np.bincount(ids[exp_mask] * H + yy[exp_mask], minlength=n_ore * H).reshape(n_ore, H)
        for oi, yi in zip(*np.nonzero(c)):
            name = acc.ore_names[oi]
            acc.counts[name][y0 + int(yi)] += int(c[oi, yi])
            if e[oi, yi]:
                acc.exposed[name][y0 + int(yi)] += int(e[oi, yi])
    return True


# ---------------- cross-section ----------------

class RegionReader:
    """Random access to chunks by chunk coordinate. Region files opened read-only."""

    def __init__(self, rdir):
        self.rdir = rdir
        self.cache = {}
        self.stats = Counter()

    def _region(self, rx, rz):
        key = (rx, rz)
        if key not in self.cache:
            path = os.path.join(self.rdir, f"r.{rx}.{rz}.mca")
            buf = None
            if os.path.exists(path):
                with open(path, "rb") as f:  # read-only
                    buf = f.read()
            self.cache[key] = buf if buf and len(buf) >= 8192 else None
        return self.cache[key]

    def present(self, rx, rz):
        buf = self._region(rx, rz)
        if buf is None:
            return np.zeros(1024, dtype=bool)
        ents = np.frombuffer(buf[:4096], dtype=">u4")
        return (ents >> 8) >= 2

    def chunk(self, cx, cz):
        buf = self._region(cx >> 5, cz >> 5)
        if buf is None:
            return None
        i = (cx & 31) + (cz & 31) * 32
        off = struct.unpack_from(">I", buf, i * 4)[0] >> 8
        if off < 2:
            return None
        raw = chunk_payload(buf, off, self.stats)
        if raw is None:
            return None
        try:
            nbt = nbtlib.File.parse(io.BytesIO(raw))
        except Exception:
            return None
        if nbt.get("sections") is None or not is_full(nbt):
            return None
        return nbt


def block_color(name, ore_re, merge, cache):
    if name in cache:
        return cache[name]
    if name in AIR:
        col = None
    elif ore_re.search(name):
        col = to_rgba(ORE_COLORS.get(ore_name(name, merge), "#ff00ff"))
    else:
        short = name.partition(":")[2] or name
        col = to_rgba(next((c for key, c in BLOCK_RULES if key in short), DEFAULT_BLOCK))
    cache[name] = col
    return col


def pick_slice(reader, files, rng):
    """Choose a chunk row with many fully generated chunks. Returns (z, x0) in blocks."""
    files = sorted(files, key=os.path.getsize, reverse=True)[:3]
    best = None
    for fp in files:
        m = re.search(r"r\.(-?\d+)\.(-?\d+)\.mca$", fp)
        if not m:
            continue
        rx, rz = int(m.group(1)), int(m.group(2))
        pres = reader.present(rx, rz).reshape(32, 32)  # [row z][col x]
        rows = np.argsort(-pres.sum(axis=1))[:3]
        for r in rows:
            cz = rz * 32 + int(r)
            full = sum(reader.chunk(rx * 32 + c, cz) is not None for c in range(32))
            if best is None or full > best[0]:
                best = (full, cz * 16 + 8, rx * 512)
    if best is None:
        return None
    return best[1], best[2]


def build_section(reader, z, x0, width, ore_re, merge):
    """Return (rgba image [H, W, 4] with row 0 = lowest Y, y_low, missing_columns)."""
    cache = {}
    cols = {}
    ylo, yhi = None, None
    for cx in range(x0 >> 4, ((x0 + width - 1) >> 4) + 1):
        nbt = reader.chunk(cx, z >> 4)
        if nbt is None:
            continue
        lz = z & 15
        for sec in nbt["sections"]:
            bs = sec.get("block_states")
            if bs is None or "palette" not in bs:
                continue
            palette = [palette_name(p) for p in bs["palette"]]
            base = int(sec["Y"]) * 16
            ylo = base if ylo is None else min(ylo, base)
            yhi = base + 16 if yhi is None else max(yhi, base + 16)
            if "data" in bs:
                try:
                    vals = unpack_states(bs["data"], len(palette)).reshape(16, 16, 16)  # y, z, x
                except ValueError:
                    continue
                plane = vals[:, lz, :]  # [y, x]
            else:
                plane = np.zeros((16, 16), dtype=np.int64)
            pcols = [block_color(n, ore_re, merge, cache) for n in palette]
            for lx in range(16):
                bx = cx * 16 + lx
                if not x0 <= bx < x0 + width:
                    continue
                col = cols.setdefault(bx, {})
                for k in range(16):
                    col[base + k] = pcols[plane[k, lx]]
    if not cols:
        return None, None, width
    H = yhi - ylo
    img = np.zeros((H, width, 4))
    missing = 0
    for i in range(width):
        col = cols.get(x0 + i)
        if col is None:
            img[:, i] = MISSING
            missing += 1
            continue
        solid = np.zeros(H, dtype=bool)
        for y, c in col.items():
            if c is not None:
                img[y - ylo, i] = c
                solid[y - ylo] = True
        top = np.nonzero(solid)[0]
        if len(top) == 0:
            continue
        # Air under the top block: short gaps or anything below sea level is cave,
        # long gaps high up (under floating islands or overhangs) stay sky.
        j = top[-1]
        while j >= 0:
            if solid[j]:
                j -= 1
                continue
            end = j
            while j >= 0 and not solid[j]:
                j -= 1
            start = j + 1
            run_top_y = ylo + end
            if not (run_top_y > 63 and end - start + 1 > 20):
                img[start:end + 1, i] = CAVE
    return img, ylo, missing


def save_cross_section(img, ylo, z, x0, path, dim):
    H, W = img.shape[:2]
    fig, ax = plt.subplots(figsize=(min(24, max(8, W / 40)), min(14, max(5, H / 40))))
    ax.set_facecolor(SKY)
    ax.imshow(img, origin="lower", extent=[x0, x0 + W, ylo, ylo + H],
              interpolation="nearest", aspect="equal")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title(f"Cross-section of {dim} at Z = {z}, X {x0} to {x0 + W - 1}")
    ax.set_yticks(range((ylo // 32) * 32, ylo + H + 1, 32))
    ax.grid(axis="y", alpha=0.25, color="white")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------- main ----------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Count every ore block per Y level in a Minecraft world (read-only).")
    ap.add_argument("world")
    ap.add_argument("--dim", default="overworld", help="overworld | nether | end | modid:name")
    ap.add_argument("--max-chunks", type=int, default=4000)
    ap.add_argument("--pattern", default=DEFAULT_PATTERN, help="regex on block id to count as ore")
    ap.add_argument("--no-merge", action="store_true", help="keep deepslate/nether variants separate")
    ap.add_argument("--scale", choices=["per-ore", "global"], default="per-ore",
                    help="per-ore: each violin scaled to its own peak (rare ores visible); "
                         "global: widths comparable across ores")
    ap.add_argument("--log", action="store_true", help="log scale widths")
    ap.add_argument("--top", type=int, default=14, help="max ores to plot")
    ap.add_argument("--seed", type=int, default=42,
                    help="random seed for picking chunks, so a scan can be repeated (not the world seed)")
    ap.add_argument("--mc-version", choices=mc_formats.versions(), metavar="VERSION",
                    help="treat the save as this Minecraft release instead of reading level.dat, e.g. 1.21.11 "
                         "or 26.3. Picks the folder layout and seed location of that version's save format")
    ap.add_argument("--out", default=os.path.join("output", "scan"), help="output folder (default output/scan)")
    ap.add_argument("--slice-x", type=int, help="block X at the centre of the cross-section")
    ap.add_argument("--slice-z", type=int, help="block Z of the cross-section")
    ap.add_argument("--slice-width", type=int, default=512, help="cross-section width in blocks")
    ap.add_argument("--no-section", action="store_true", help="skip the cross-section")
    a = ap.parse_args(argv)

    ore_re = re.compile(a.pattern)
    merge = not a.no_merge
    rng = random.Random(a.seed)
    world_abs = os.path.realpath(a.world)
    out_abs = os.path.realpath(a.out)
    if os.path.commonpath([world_abs, out_abs]) == world_abs:
        raise SystemExit(f"--out ({out_abs}) is inside the world folder. "
                         "Pick an output folder outside the save, e.g. --out output/scan")
    os.makedirs(a.out, exist_ok=True)

    family = mc_formats.family_for_version(a.mc_version) if a.mc_version else None
    rdir = region_dir(a.world, a.dim, family)
    files = glob.glob(os.path.join(rdir, "r.*.mca"))
    if not files:
        hint = " (layout forced by --mc-version; try without it)" if family else ""
        raise SystemExit(f"no region files in {rdir}{hint}")
    info = read_world_info(a.world, family)
    info["detected_version"] = info["mc_version"]
    if family:
        if info["mc_version"] and info["mc_version"] != a.mc_version:
            print(f"  note: level.dat says Minecraft {info['mc_version']}; using {a.mc_version} as asked")
        info["mc_version"] = a.mc_version
    info["version_source"] = "--mc-version" if family else ("level.dat" if info["mc_version"] else None)
    seed_txt = f", seed {info['world_seed']}" if info["world_seed"] else ", world seed not found"
    print(f"world: Minecraft {info['mc_version'] or 'version unknown'}"
          f" (data version {info['data_version'] or '?'}){seed_txt}")
    warn = None if family else version_warning(info)
    if warn:
        print(f"  warning: {warn}")
    scan_files = files[:]
    rng.shuffle(scan_files)
    per_file = max(1, -(-a.max_chunks // len(scan_files)))
    acc = Acc()
    stats = Counter()
    done = 0
    first_error = None
    for fp in scan_files:
        n = 0
        for raw in read_chunks(fp, rng, stats):
            try:
                ok = scan_chunk(raw, acc, ore_re, merge, stats)
            except Exception as e:  # one bad chunk must not stop the scan, but keep the reason
                stats["corrupt"] += 1
                first_error = first_error or f"{os.path.basename(fp)}: {type(e).__name__}: {e}"
                continue
            if not ok:
                continue
            n += 1
            done += 1
            if n >= per_file or done >= a.max_chunks:
                break
        if done >= a.max_chunks:
            break
    print(f"scanned {done} full chunks from {len(files)} region files")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    if first_error:
        print(f"  first unreadable chunk: {first_error}")
    if stats.get("skipped_pre_1.18_format") and not done:
        raise SystemExit("world uses pre-1.18 chunk format, not supported")
    counts = acc.counts
    if not counts:
        raise SystemExit("no ore blocks found; check --dim and --pattern")

    # CSVs
    with open(os.path.join(a.out, "ore_by_y.csv"), "w", newline="") as f:
        f.write("ore,y,count,exposed\n")
        for o, d in sorted(counts.items()):
            for y in sorted(d):
                f.write(f"{o},{y},{d[y]},{acc.exposed[o].get(y, 0)}\n")
    with open(os.path.join(a.out, "layers_by_y.csv"), "w", newline="") as f:
        f.write("y,positions,rock,wall\n")
        for y in sorted(acc.layers):
            p, r, w = acc.layers[y]
            f.write(f"{y},{p},{r},{w}\n")
    summary = []
    for o, d in counts.items():
        ys = np.array(sorted(d))
        w = np.array([d[y] for y in ys], dtype=float)
        cum = np.cumsum(w) / w.sum()
        summary.append(dict(ore=o, total=int(w.sum()),
                            per_chunk=round(w.sum() / done, 2),
                            peak_y=int(ys[w.argmax()]),
                            median_y=int(ys[np.searchsorted(cum, 0.5)]),
                            p10_y=int(ys[np.searchsorted(cum, 0.1)]),
                            p90_y=int(ys[min(np.searchsorted(cum, 0.9), len(ys) - 1)]),
                            min_y=int(ys.min()), max_y=int(ys.max()),
                            exposed_pct=round(100 * sum(acc.exposed[o].values()) / w.sum(), 2)))
    summary.sort(key=lambda r: -r["total"])
    with open(os.path.join(a.out, "ore_summary.csv"), "w", newline="") as f:
        f.write(",".join(summary[0].keys()) + "\n")
        for r in summary:
            f.write(",".join(str(v) for v in r.values()) + "\n")

    # Cross-section
    img = None
    sec_label = ""
    slice_text = None
    if not a.no_section:
        reader = RegionReader(rdir)
        if a.slice_z is not None:
            z = a.slice_z
            cx = a.slice_x if a.slice_x is not None else 0
            x0 = cx - a.slice_width // 2
        else:
            picked = pick_slice(reader, files, rng)
            z, x0 = picked if picked else (0, -a.slice_width // 2)
            if a.slice_x is not None:
                x0 = a.slice_x - a.slice_width // 2
        img, ylo, missing = build_section(reader, z, x0, a.slice_width, ore_re, merge)
        if img is None:
            print(f"cross-section: no fully generated chunks at Z={z}, X {x0}..{x0 + a.slice_width - 1}")
        else:
            save_cross_section(img, ylo, z, x0, os.path.join(a.out, "cross_section.png"), a.dim)
            sec_label = f"Background: slice at Z={z}, X {x0} to {x0 + a.slice_width - 1}"
            slice_text = f"Z {z}, X {x0} to {x0 + a.slice_width - 1}"
            print(f"cross-section: Z={z}, X {x0}..{x0 + a.slice_width - 1}"
                  f" ({missing} of {a.slice_width} columns not generated)")

    # Chart
    top = summary[:a.top]
    ymin = min(r["min_y"] for r in top) - 4
    ymax = max(r["max_y"] for r in top) + 4
    if img is not None:
        ymin = min(ymin, ylo)
        ymax = max(ymax, ylo + img.shape[0])
    ys_all = np.arange(ymin, ymax + 1)
    gmax = max(max(counts[r["ore"]].values()) for r in top)
    fig, ax = plt.subplots(figsize=(max(10, len(top) * 1.2), 10))
    ax.set_facecolor(SKY)
    x_lo, x_hi = -0.6, len(top) - 0.2
    if img is not None:
        ax.imshow(img, origin="lower", extent=[x_lo, x_hi, ylo, ylo + img.shape[0]],
                  interpolation="nearest", aspect="auto", alpha=0.7, zorder=0)
    cmap = plt.get_cmap("tab20")
    for i, r in enumerate(top):
        d = counts[r["ore"]]
        w = np.array([d.get(int(y), 0) for y in ys_all], dtype=float)
        w = np.convolve(w, np.ones(3) / 3, mode="same")
        ref = w.max() if a.scale == "per-ore" else gmax
        w = np.log1p(w) / np.log1p(ref) if a.log else w / ref
        w *= 0.45
        color = ORE_COLORS.get(r["ore"], cmap(i % 20))
        ax.fill_betweenx(ys_all, i - w, i + w, where=w > 0, color=color, alpha=0.95,
                         edgecolor="black", linewidth=0.5, zorder=2)
        ax.plot([i - 0.45, i + 0.45], [r["peak_y"]] * 2, color="white", lw=2.2, zorder=3)
        ax.plot([i - 0.45, i + 0.45], [r["peak_y"]] * 2, color="black", lw=0.9, zorder=4)
        ax.annotate(f"Y {r['peak_y']}", (i + 0.47, r["peak_y"]), ha="left", va="center",
                    fontsize=7, fontweight="bold", zorder=5,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    ax.set_xticks(range(len(top)))
    ax.set_xticklabels([f"{r['ore']}\nmed {r['median_y']} | {r['per_chunk']}/chunk" for r in top],
                       rotation=40, ha="right", fontsize=8)
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(ymin, ymax)
    ax.set_ylabel("Y level")
    ax.set_title(f"Ore distribution by Y ({a.dim}, {done} chunks, width = {a.scale} count). "
                 "Line = peak Y")
    if sec_label:
        ax.text(0.01, 0.99, sec_label, transform=ax.transAxes, ha="left", va="top", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85), zorder=6)
    ax.grid(axis="y", alpha=0.35, color="white", zorder=1)
    ax.set_axisbelow(False)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "ore_chart.png"), dpi=150)
    plt.close(fig)

    # Everything the report builders need besides the CSVs, so nobody copies numbers from the console.
    today = datetime.date.today()
    info.update({
        "world_folder": os.path.basename(world_abs), "dimension": a.dim,
        "scan": {"chunks": done, "region_files": len(files),
                 "skipped_not_fully_generated": stats.get("skipped_not_fully_generated", 0),
                 "sample_seed": a.seed, "max_chunks": a.max_chunks,
                 "date": f"{today.day} {today:%b %Y}", "slice": slice_text},
    })
    with open(os.path.join(a.out, "world_info.json"), "w") as f:
        json.dump(info, f, indent=2)
    print(f"wrote outputs to {os.path.abspath(a.out)}")
    return info


if __name__ == "__main__":
    main()
