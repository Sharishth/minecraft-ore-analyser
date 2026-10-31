"""Build a synthetic 1.18+ world with known ore placement to test ore_scan.py.

    python tests/make_world.py <world>              layout and palettes of Minecraft 1.18 to 1.21
    python tests/make_world.py <world> --new        layout and palettes of Minecraft 26.x
"""
import io, os, sys, struct, zlib
import numpy as np
from nbtlib import File, Compound, List, String, Byte, Int, Long, LongArray

FILLER = [f"minecraft:filler_{i}" for i in range(20)]  # forces bits=5 palette


def pack(vals, bits):
    per = 64 // bits
    n = -(-len(vals) // per)
    out = []
    for i in range(n):
        v = 0
        for j, x in enumerate(vals[i * per:(i + 1) * per]):
            v |= int(x) << (j * bits)
        if v >= 1 << 63:
            v -= 1 << 64
        out.append(v)
    return LongArray(out)


def section(sy, placements, big_palette):
    """placements: list of (block_id, local_y, count)."""
    palette = ["minecraft:stone"] + (FILLER if big_palette else [])
    vals = np.zeros(4096, dtype=np.int64)
    for bid, ly, cnt in placements:
        if bid not in palette:
            palette.append(bid)
        pi = palette.index(bid)
        start = ly * 256
        vals[start:start + cnt] = pi
    bits = max(4, (len(palette) - 1).bit_length())
    bs = Compound({"palette": palette_tag(sy, palette)})
    if len(palette) > 1:
        bs["data"] = pack(vals, bits)
    return Compound({"Y": Byte(sy), "block_states": bs})


NEW_FORMAT = False


def palette_tag(sy, palette):
    """Palette list. Minecraft 26.x writes a plain id, {"": id} or {"id": id, "properties": ...} per section."""
    if not NEW_FORMAT:
        return List[Compound]([Compound({"Name": String(p)}) for p in palette])
    kind = sy % 3
    if kind == 0:
        return List[String]([String(p) for p in palette])
    if kind == 1:
        return List[Compound]([Compound({"": String(p)}) for p in palette])
    return List[Compound]([Compound({"id": String(p), "properties": Compound({"generated": String("true")})})
                           for p in palette])


def write_level(world, name, version, data_version, seed, new_format):
    """level.dat, plus the world seed where this Minecraft version keeps it."""
    os.makedirs(world, exist_ok=True)
    data = Compound({"LevelName": String(name), "DataVersion": Int(data_version),
                     "Version": Compound({"Name": String(version), "Id": Int(data_version)})})
    if new_format:
        os.makedirs(os.path.join(world, "data", "minecraft"), exist_ok=True)
        File({"data": Compound({"seed": Long(seed)}), "DataVersion": Int(data_version)}, gzipped=True).save(
            os.path.join(world, "data", "minecraft", "world_gen_settings.dat"))
    else:
        data["WorldGenSettings"] = Compound({"seed": Long(seed)})
    File({"Data": data}, gzipped=True).save(os.path.join(world, "level.dat"))


def chunk(status, big_palette):
    plan = {
        -4: [("minecraft:deepslate_diamond_ore", 6, 3)],   # y = -58
        1: [("minecraft:iron_ore", 0, 5)],                  # y = 16
        12: [("create:zinc_ore", 8, 7)],                    # y = 200 floating island
    }
    secs = [section(sy, plan.get(sy, []), big_palette) for sy in range(-4, 20)]
    return File({"Status": String(status), "DataVersion": Int(3955),
                 "sections": List[Compound](secs)})


def write_region(path, chunks):
    header = bytearray(8192)
    body = bytearray()
    sector = 2
    for idx, c in chunks:
        buf = io.BytesIO()
        c.write(buf)
        data = zlib.compress(buf.getvalue())
        payload = struct.pack(">IB", len(data) + 1, 2) + data
        payload += b"\0" * (-len(payload) % 4096)
        n = len(payload) // 4096
        struct.pack_into(">I", header, idx * 4, (sector << 8) | n)
        body += payload
        sector += n
    with open(path, "wb") as f:
        f.write(header + body)


if __name__ == "__main__":
    world = sys.argv[1]
    NEW_FORMAT = "--new" in sys.argv[2:]
    if NEW_FORMAT:
        region = os.path.join(world, "dimensions", "minecraft", "overworld", "region")
        write_level(world, "SynthNew", "26.3", 5023, -1234567890123456789, True)
    else:
        region = os.path.join(world, "region")
        write_level(world, "SynthOld", "1.21.4", 3955, 987654321, False)
    os.makedirs(region, exist_ok=True)
    full = [(i, chunk("minecraft:full", i % 2 == 0)) for i in range(10)]
    proto = [(500, chunk("minecraft:features", False))]
    write_region(os.path.join(region, "r.0.0.mca"), full + proto)
    print("expected (10 full chunks): diamond y=-58 -> 30, iron y=16 -> 50, create:zinc y=200 -> 70")
