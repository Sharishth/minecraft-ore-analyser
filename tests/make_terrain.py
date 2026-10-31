"""Synthetic 1.18+ world with terrain, caves, water, a floating island and ores."""
import io, os, sys, struct, zlib
import numpy as np
from nbtlib import File, Compound, List, String, Byte, Int, LongArray

NAMES = ["minecraft:air", "minecraft:stone", "minecraft:deepslate", "minecraft:bedrock",
         "minecraft:dirt", "minecraft:grass_block", "minecraft:water", "minecraft:sand",
         "minecraft:coal_ore", "minecraft:iron_ore", "minecraft:deepslate_diamond_ore",
         "minecraft:deepslate_redstone_ore", "minecraft:emerald_ore", "minecraft:cave_air",
         "minecraft:oak_leaves", "minecraft:oak_log"]
ID = {n: i for i, n in enumerate(NAMES)}


def pack(vals, bits):
    per = 64 // bits
    n = -(-len(vals) // per)
    pad = np.zeros(n * per, dtype=np.uint64)
    pad[:len(vals)] = vals.astype(np.uint64)
    pad = pad.reshape(n, per)
    shifts = (np.arange(per, dtype=np.uint64) * np.uint64(bits))
    longs = np.bitwise_or.reduce(pad << shifts, axis=1)
    return LongArray(longs.view(np.int64))


def column_blocks(bx, bz, rng):
    """Return array of block ids for Y -64..319 at world column (bx, bz)."""
    ys = np.arange(-64, 320)
    h = int(72 + 22 * np.sin(bx / 37.0) + 8 * np.cos(bz / 23.0))
    col = np.full(len(ys), ID["minecraft:air"])
    col[ys <= h] = ID["minecraft:stone"]
    col[ys < 0] = ID["minecraft:deepslate"]
    col[(ys > h - 4) & (ys < h)] = ID["minecraft:dirt"]
    col[ys == h] = ID["minecraft:grass_block"] if h >= 63 else ID["minecraft:sand"]
    col[(ys > h) & (ys <= 62)] = ID["minecraft:water"]
    col[ys == -64] = ID["minecraft:bedrock"]
    # caves: a tunnel band
    cave_c = 20 + 10 * np.sin(bx / 15.0)
    col[(np.abs(ys - cave_c) < 4) & (ys < h - 8)] = ID["minecraft:cave_air"]
    # floating island between x 120 and 220
    if 120 <= bx < 220:
        thick = int(12 * np.sin(np.pi * (bx - 120) / 100))
        col[(ys >= 200 - thick) & (ys <= 200)] = ID["minecraft:stone"]
        col[ys == 201] = ID["minecraft:grass_block"]
    # tree
    if bx % 40 == 5 and h >= 63:
        col[(ys > h) & (ys <= h + 5)] = ID["minecraft:oak_log"]
        col[(ys > h + 3) & (ys <= h + 7) & (col == ID["minecraft:air"])] = ID["minecraft:oak_leaves"]
    # ores
    for y, ore, p, host in [(-58, "minecraft:deepslate_diamond_ore", 0.15, "minecraft:deepslate"),
                            (-59, "minecraft:deepslate_redstone_ore", 0.25, "minecraft:deepslate"),
                            (15, "minecraft:iron_ore", 0.2, "minecraft:stone"),
                            (40, "minecraft:coal_ore", 0.3, "minecraft:stone"),
                            (195, "minecraft:emerald_ore", 0.3, "minecraft:stone")]:
        k = y + 64
        if col[k] == ID[host] and rng.random() < p:
            col[k] = ID[ore]
    return col


def chunk(cx, cz, rng):
    vol = np.zeros((384, 16, 16), dtype=np.int64)  # y, z, x
    for lz in range(16):
        for lx in range(16):
            vol[:, lz, lx] = column_blocks(cx * 16 + lx, cz * 16 + lz, rng)
    secs = []
    for s in range(24):
        block = vol[s * 16:(s + 1) * 16].reshape(-1)
        uniq = np.unique(block)
        palette = [NAMES[u] for u in uniq]
        remap = {u: i for i, u in enumerate(uniq)}
        bs = Compound({"palette": List[Compound]([Compound({"Name": String(p)}) for p in palette])})
        if len(palette) > 1:
            vals = np.vectorize(remap.get)(block)
            bs["data"] = pack(vals, max(4, (len(palette) - 1).bit_length()))
        secs.append(Compound({"Y": Byte(s - 4), "block_states": bs}))
    return File({"Status": String("minecraft:full"), "DataVersion": Int(4671),
                 "xPos": Int(cx), "zPos": Int(cz), "sections": List[Compound](secs)})


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
    from make_world import write_level
    write_level(world, "SynthTerrain", "1.21.11", 4671, 4242424242, False)
    rng = np.random.default_rng(1)
    row = 4
    chunks = [(cx + row * 32, chunk(cx, row, rng)) for cx in range(32)]
    chunks += [(cx + 10 * 32, chunk(cx, 10, rng)) for cx in range(0, 32, 4)]
    write_region(os.path.join(world, "region", "r.0.0.mca"), chunks)
    print("built", len(chunks), "chunks; slice row z = 4*16+8 = 72")
