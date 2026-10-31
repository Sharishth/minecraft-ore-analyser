"""Minecraft Java Edition save formats that ore_scan.py understands.

Many releases share one save format, so the scanner works with format families, not single versions.
Only three things matter to the scanner, and they changed at these points:

| Family     | Releases        | Region folders                        | World seed in                          | Block palette entries                  |
|------------|-----------------|---------------------------------------|----------------------------------------|----------------------------------------|
| anvil-1.18 | 1.18 to 1.21.11 | region, DIM-1, DIM1                   | level.dat Data.WorldGenSettings.seed   | {Name, Properties}                     |
| dims-26.1  | 26.1 to 26.2    | dimensions/<namespace>/<name>/region  | data/minecraft/world_gen_settings.dat  | {Name, Properties}                     |
| ids-26.3   | 26.3            | dimensions/<namespace>/<name>/region  | data/minecraft/world_gen_settings.dat  | {id, properties}, {"": id} or plain id |

Sources (checked 1 Nov 2026): minecraft.wiki "Java Edition level format", "Chunk format" (history: 26.3
snapshot 7 renamed Name/Properties and allowed string palettes; 26.4 snapshot 1 renames Status to status),
"Java Edition 26.1" (dimensions folder; seed moved in 26.1 snapshot 6), "Data version"; release dates from
Mojang's version manifest (piston-meta.mojang.com/mc/game/version_manifest_v2.json).

Palettes are decoded by the shape of each entry (ore_scan.palette_name), which reads every family above, so
a world from an in-between snapshot still scans. The family decides where files are looked for.
"""
from collections import namedtuple

Family = namedtuple("Family", "key label first_data_version layout seed_file palette")

FAMILIES = [
    Family("ids-26.3", "Minecraft 26.3 and newer", 5023, "dimensions", "world_gen_settings.dat",
           "id/properties, empty-key or plain-string entries"),
    Family("dims-26.1", "Minecraft 26.1 to 26.2", 4786, "dimensions", "world_gen_settings.dat",
           "Name/Properties entries"),
    Family("anvil-1.18", "Minecraft 1.18 to 1.21.11", 2860, "legacy", "level.dat",
           "Name/Properties entries"),
]  # newest first

FIRST_SUPPORTED_DATA_VERSION = 2860  # 1.18: first release with the current chunk format
NEWEST_TESTED_DATA_VERSION = 5023    # 26.3: newest release a real world has been scanned from

# Full releases the scanner supports: (version, release date, data version), newest first.
# Data versions are only filled in where they were checked; family_for_version uses the version name.
RELEASES = [
    ("26.3", "2026-09-15", 5023), ("26.2", "2026-06-16", 4903), ("26.1.2", "2026-04-09", 4790),
    ("26.1.1", "2026-04-01", 4788), ("26.1", "2026-03-24", 4786),
    ("1.21.11", "2025-12-09", 4671), ("1.21.10", "2025-10-07", None), ("1.21.9", "2025-09-30", None),
    ("1.21.8", "2025-07-17", None), ("1.21.7", "2025-06-30", None), ("1.21.6", "2025-06-17", None),
    ("1.21.5", "2025-03-25", None), ("1.21.4", "2024-12-03", None), ("1.21.3", "2024-10-23", None),
    ("1.21.2", "2024-10-22", None), ("1.21.1", "2024-08-08", None), ("1.21", "2024-06-13", None),
    ("1.20.6", "2024-04-29", None), ("1.20.5", "2024-04-23", None), ("1.20.4", "2023-12-07", None),
    ("1.20.3", "2023-12-04", None), ("1.20.2", "2023-09-20", None), ("1.20.1", "2023-06-12", None),
    ("1.20", "2023-06-02", None), ("1.19.4", "2023-03-14", None), ("1.19.3", "2022-12-07", None),
    ("1.19.2", "2022-08-05", None), ("1.19.1", "2022-07-27", None), ("1.19", "2022-06-07", None),
    ("1.18.2", "2022-02-28", None), ("1.18.1", "2021-12-10", None), ("1.18", "2021-11-30", 2860),
]


def versions():
    """Supported release names, newest release first (for --mc-version choices and the GUI)."""
    return [v for v, _, _ in sorted(RELEASES, key=lambda r: r[1], reverse=True)]


def _version_key(name):
    return tuple(int(p) for p in name.split("."))


def family_for_version(name):
    """Format family of a release name such as "1.21.4" or "26.3". Raises ValueError if unsupported."""
    try:
        key = _version_key(name)
    except ValueError:
        raise ValueError(f"not a release version: {name!r}") from None
    if key < (1, 18):
        raise ValueError(f"Minecraft {name} is older than 1.18; its chunk format is not supported")
    if key >= (26, 3):
        return FAMILIES[0]
    if key >= (26, 1):
        return FAMILIES[1]
    return FAMILIES[2]


def family_for_data_version(dv):
    """Format family of a world's data version, or None when unknown or older than 1.18."""
    if dv is None or dv < FIRST_SUPPORTED_DATA_VERSION:
        return None
    return next(f for f in FAMILIES if dv >= f.first_data_version)
