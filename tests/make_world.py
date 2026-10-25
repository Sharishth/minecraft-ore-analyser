"""Build a synthetic 1.18+ world with known ore placement to test ore_scan.py."""
import io, os, sys, struct, zlib
import numpy as np
from nbtlib import File, Compound, List, String, Byte, Int, LongArray

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
    bs = Compound({"palette": List[Compound]([Compound({"Name": String(p)}) for p in palette])})
    if len(palette) > 1:
        bs["data"] = pack(vals, bits)
    return Compound({"Y": Byte(sy), "block_states": bs})


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
    os.makedirs(os.path.join(world, "region"), exist_ok=True)
    full = [(i, chunk("minecraft:full", i % 2 == 0)) for i in range(10)]
    proto = [(500, chunk("minecraft:features", False))]
    write_region(os.path.join(world, "region", "r.0.0.mca"), full + proto)
    print("expected (10 full chunks): diamond y=-58 -> 30, iron y=16 -> 50, create:zinc y=200 -> 70")
