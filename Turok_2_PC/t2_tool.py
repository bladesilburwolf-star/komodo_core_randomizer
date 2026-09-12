#!/usr/bin/env python3
"""
Turok 2: Seeds of Evil (PC) LSS tool + hybrid randomizer
Part of Akklaim Randomizers

Hybrid approach:
  A) Section 8 spawn/warp shuffle (stable, sector-aware)
  B) Experimental weapon model-ID shuffle in sec5 part5 (in-place u16)
  C) Future: runtime inject for full pickup/enemy control

Usage:
  python t2_tool.py info <file.lss>
  python t2_tool.py list-spawns <file.lss>
  python t2_tool.py shuffle-spawns <file.lss> [--seed N] [-o out.lss]
  python t2_tool.py list-weapons <file.lss>
  python t2_tool.py list-enemies <file.lss>
  python t2_tool.py shuffle-weapons <file.lss> [--seed N] [-o out.lss]
  python t2_tool.py shuffle-all <file.lss> [--seed N] [-o out.lss]
  python t2_tool.py scan-sec5-dryrun <file.lss>
  python t2_tool.py rnc-selftest <file.lss>
"""

from __future__ import annotations
import argparse
import math
import random
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple, Optional, Dict

SECTION_NAMES = {
    0: "models", 1: "actor_attrs?", 2: "actor_types?", 3: "textures?",
    4: "particles", 5: "levels_A", 6: "levels_B", 7: "levels_C",
    8: "warps_spawns", 9: "empty?", 10: "empty?", 11: "weapon_effects",
    12: "meta_12", 13: "meta_13", 14: "meta_14", 15: "meta_15",
    16: "gui_textures", 17: "gui_tex_defs", 18: "other_18",
    19: "other_19", 20: "empty?",
}
WARPS_SECTION = 8

# Speculative pools — refine with in-game verification.
# Real enemy/weapon/ammo placements live in RNC level blobs; type-swap
# writes use vendored pure-Python RNC pack (in-place when new size fits).
QUEST_ITEM_TYPE_IDS = {
    0x0300, 0x0301, 0x0302, 0x0303,
    0x0310, 0x0311, 0x0312,
    0x0320, 0x0330, 0x0331,
    0x0340, 0x0341, 0x0342, 0x0343, 0x0400,
}

# Working categories for dry-run labeling (IDs still being mapped)
ENEMY_TYPE_IDS = set()      # filled as we confirm
WEAPON_TYPE_IDS = set()
AMMO_TYPE_IDS = set()
HEALTH_TYPE_IDS = set()

# Observed frequent candidate IDs from sec5 scans (unverified)
CANDIDATE_IDS = {
    0x0010, 0x0014, 0x0040, 0x0001, 0x0002, 0x0008,
    0x00c2, 0x00c3, 0x00c4, 0x0082, 0x0064, 0x03e0, 0x03e6,
}

# Section 0 model indices used by weapon pickups (community Weapon_IDs list).
# Shuffling these u16 values in sec5 part5 is experimental — some hits may be
# coincidental in mesh data. Always keep a backup LSS.
WEAPON_MODEL_IDS = {
    2394: "Bore",
    2395: "Charge Dart Rifle",
    2396: "Firestorm Cannon",
    2397: "Flame Thrower",
    2398: "Flare Gun",
    2399: "Grenade Launcher",
    2400: "Mag 60",
    2412: "Bow",
    2413: "Nuke",
    2414: "PFM Layer",
    2415: "Pistol",
    2416: "Plasma Rifle",
    2418: "Scorpion Launcher",
    2419: "Shotgun",
    2420: "Shredder",
    2421: "Sunfire Pods",
    2422: "Razor Wind",
    2423: "Talon",
    2424: "Tek Bow",
    2425: "Tranq Gun",
    2426: "Harpoon Gun",
    2427: "Underwater Rockets",
    2428: "War Blade",
}


# Pure-Python RNC (vendored under ./rnc/) — no external tools
try:
    from rnc import unpack_le as rnc_unpack_le, pack_le as rnc_pack_le
    _RNC_AVAILABLE = True
except Exception:
    _RNC_AVAILABLE = False
    def rnc_unpack_le(blob: bytes, start: int = 0):  # type: ignore
        return None
    def rnc_pack_le(data: bytes, method: int = 2):  # type: ignore
        raise RuntimeError("RNC pack not available")


def read_u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def parse_lss_header(data: bytes) -> Tuple[int, int, List[int]]:
    if len(data) < 8:
        raise ValueError("File too small for LSS header")
    count = read_u32(data, 0)
    header_size = read_u32(data, 4)
    if count < 1 or count > 64:
        raise ValueError(f"Unreasonable section count: {count}")
    ends = [read_u32(data, 8 + i * 4) for i in range(count)]
    return count, header_size, ends


def section_ranges(header_size: int, ends: List[int]) -> List[Tuple[int, int]]:
    ranges, prev = [], header_size
    for end in ends:
        ranges.append((prev, end))
        prev = end
    return ranges


def get_section(data: bytes, index: int) -> Tuple[bytes, int, int]:
    count, header_size, ends = parse_lss_header(data)
    if index < 0 or index >= count:
        raise IndexError(f"Section {index} out of range (0..{count - 1})")
    ranges = section_ranges(header_size, ends)
    start, end = ranges[index]
    return data[start:end], start, end


def patch_section(lss: bytearray, index: int, new_sec: bytes) -> None:
    _, start, end = get_section(bytes(lss), index)
    if len(new_sec) != (end - start):
        raise ValueError(f"Section size mismatch: original {end - start}, new {len(new_sec)}")
    lss[start:end] = new_sec


def _heuristic_position_records(sec: bytes, start_at: int = 0x300) -> List[Tuple[int, bytes]]:
    records: List[Tuple[int, bytes]] = []
    i = start_at
    while i + 20 <= len(sec):
        x, y, z, w = struct.unpack_from("<ffff", sec, i)
        if any(math.isnan(v) or math.isinf(v) for v in (x, y, z, w)):
            i += 4
            continue
        mags = sorted([abs(x), abs(y), abs(z)], reverse=True)
        a = abs(w)
        is_ang = a < 0.05 or abs(a - 1.5708) < 0.12 or abs(a - 3.1416) < 0.12
        if mags[0] > 50 and mags[1] > 10 and mags[0] < 8500 and is_ang:
            records.append((i, sec[i:i + 20]))
            i += 20
            continue
        i += 4
    return records


def parse_section8_position_records(sec: bytes) -> List[Tuple[int, bytes]]:
    if len(sec) < 16:
        return []
    block_count = read_u32(sec, 0)
    if block_count < 2:
        return _heuristic_position_records(sec)
    try:
        offsets = [read_u32(sec, 4 + i * 4) for i in range(block_count + 1)]
        start, end = offsets[1], offsets[2]
        if start + 8 > len(sec) or end > len(sec):
            return _heuristic_position_records(sec)
        record_size, record_count = struct.unpack_from("<II", sec, start)
        if record_size < 16 or record_size > 64 or record_count < 1 or record_count > 2000:
            return _heuristic_position_records(sec)
        records_start = start + 8
        records_end = records_start + record_size * record_count
        if records_end > len(sec):
            return _heuristic_position_records(sec)
        return [
            (off, sec[off:off + record_size])
            for off in range(records_start, records_end, record_size)
        ]
    except Exception:
        return _heuristic_position_records(sec)


def find_position_records(sec: bytes, require_angle: bool = True, start_at: int = 0x300) -> List[Tuple[int, bytes]]:
    recs = parse_section8_position_records(sec)
    if recs:
        return recs
    return _heuristic_position_records(sec, start_at=start_at)


def shuffle_positions(sec: bytearray, seed: Optional[int] = None) -> int:
    records = find_position_records(bytes(sec))
    if len(records) < 2:
        return 0
    rng = random.Random(seed)
    blocks = [b for _, b in records]
    rng.shuffle(blocks)
    for (off, _), new_block in zip(records, blocks):
        sec[off:off + len(new_block)] = new_block
    return len(records)


def extract_entities_from_raw(raw: bytes) -> List[Dict]:
    entities: List[Dict] = []
    i = 0
    while i + 20 <= len(raw):
        type_id = struct.unpack_from("<I", raw, i)[0]
        x, y, z, rot = struct.unpack_from("<ffff", raw, i + 4)
        if any(math.isnan(v) or math.isinf(v) for v in (x, y, z, rot)):
            i += 4
            continue
        if 1 <= type_id <= 0x2000 and abs(rot) <= 360.0:
            mags = sorted([abs(x), abs(y), abs(z)], reverse=True)
            if mags[0] > 30 and mags[0] < 15000:
                entities.append({"offset": i, "type_id": type_id, "pos": (x, y, z), "rot": rot})
                i += 20
                continue
        i += 4
    return entities


def scan_section5_entities(data: bytes) -> Tuple[List[Dict], Counter]:
    sec5, _, _ = get_section(data, 5)
    n_blocks = read_u32(sec5, 0)
    offsets = [read_u32(sec5, 4 + i * 4) for i in range(n_blocks)]
    all_ents: List[Dict] = []
    hist: Counter = Counter()
    for mi in range(n_blocks):
        a = offsets[mi]
        b = offsets[mi + 1] if mi + 1 < n_blocks else len(sec5)
        sub = sec5[a:b]
        if len(sub) < 20:
            continue
        idx = 0
        while True:
            j1 = sub.find(b"RNC\x01", idx)
            j2 = sub.find(b"RNC\x02", idx)
            cands = [j for j in (j1, j2) if j >= 0]
            if not cands:
                break
            j = min(cands)
            out = rnc_unpack_le(sub, j)
            if out is not None and len(out) >= 20:
                for it in extract_entities_from_raw(out):
                    it["map_index"] = mi
                    all_ents.append(it)
                    hist[it["type_id"]] += 1
            idx = j + 4
    return all_ents, hist



def rnc_replace_in_blob(blob: bytearray, start: int, new_unpacked: bytes, method: int | None = None) -> int:
    """Replace RNC block at start. In-place only if new packed <= old packed (zero-padded)."""
    if start + 18 > len(blob) or bytes(blob[start:start+3]) != b"RNC":
        return -1
    old_method = blob[start + 3]
    old_p = struct.unpack_from("<I", blob, start + 8)[0]
    if method is None:
        method = old_method if old_method in (1, 2) else 2
    try:
        packed = rnc_pack_le(new_unpacked, method=method)
    except Exception:
        try:
            packed = rnc_pack_le(new_unpacked, method=2)
        except Exception:
            return -1
    new_p = len(packed) - 18
    if new_p > old_p:
        return -1
    # Pad to original packed size; keep size field as old_p for stream alignment
    if len(packed) < 18 + old_p:
        packed = packed + bytes(18 + old_p - len(packed))
    # Force packed-size field to old_p
    packed = bytearray(packed[:18 + old_p])
    struct.pack_into("<I", packed, 8, old_p)
    blob[start:start + 18 + old_p] = packed
    return 18 + old_p


def cmd_rnc_selftest(path: Path) -> None:
    """Verify pure-Python RNC pack/unpack round-trip on this LSS."""
    data = path.read_bytes()
    for method in (1, 2):
        sig = b"RNC" + bytes([method])
        i = data.find(sig)
        if i < 0:
            print(f"method {method}: signature not found")
            continue
        orig = rnc_unpack_le(data, i)
        if orig is None:
            print(f"method {method} @0x{i:x}: unpack failed")
            continue
        try:
            packed = rnc_pack_le(orig, method=method)
            back = rnc_unpack_le(packed, 0)
            print(f"method {method} @0x{i:x}: unpack={len(orig)} pack={len(packed)} roundtrip={back==orig}")
        except Exception as e:
            print(f"method {method}: pack error: {e}")



def _map_part_slices(sec5: bytes, map_index: int):
    """Return (map_sub_bytes, list of 9 part slices) for one map in section 5."""
    n5 = read_u32(sec5, 0)
    if map_index < 0 or map_index >= n5:
        raise IndexError(f"map {map_index} out of range 0..{n5-1}")
    offs = [read_u32(sec5, 4 + i * 4) for i in range(n5)]
    a = offs[map_index]
    b = offs[map_index + 1] if map_index + 1 < n5 else len(sec5)
    sub = sec5[a:b]
    pc = read_u32(sub, 0)
    if pc < 6:
        return sub, a, []
    poffs = [read_u32(sub, 4 + i * 4) for i in range(pc)]
    parts = []
    for i in range(pc):
        s = poffs[i]
        e = poffs[i + 1] if i + 1 < pc else len(sub)
        parts.append((s, e, sub[s:e]))
    return sub, a, parts


def find_weapon_model_hits(lss: bytes) -> List[dict]:
    """Scan section 5 part5 for u16 values that match known weapon model IDs.

    Returns list of {map, part, abs_off, local_off, model_id, name}.
    abs_off is absolute offset in the full LSS file for direct patching.
    """
    sec5, sec5_start, _ = get_section(lss, 5)
    n5 = read_u32(sec5, 0)
    hits: List[dict] = []
    ids = set(WEAPON_MODEL_IDS.keys())
    for mi in range(n5):
        try:
            sub, map_off_in_sec5, parts = _map_part_slices(sec5, mi)
        except Exception:
            continue
        if len(parts) < 6:
            continue
        # part index 5 = room hierarchy (largest uncompressed region)
        part_start, part_end, chunk = parts[5]
        for off in range(0, len(chunk) - 2, 2):
            u16 = struct.unpack_from("<H", chunk, off)[0]
            if u16 not in ids:
                continue
            abs_off = sec5_start + map_off_in_sec5 + part_start + off
            hits.append({
                "map": mi,
                "part": 5,
                "local_off": off,
                "abs_off": abs_off,
                "model_id": u16,
                "name": WEAPON_MODEL_IDS[u16],
            })
    return hits


def shuffle_weapon_models(lss: bytearray, seed: Optional[int] = None) -> int:
    """In-place shuffle of weapon model u16s among found hits.

    Only rewrites the 2-byte model ID fields — no size change, no RNC.
    Experimental: false-positive hits in mesh data may cause visual glitches.
    """
    hits = find_weapon_model_hits(bytes(lss))
    if len(hits) < 2:
        return 0
    rng = random.Random(seed)
    ids = [h["model_id"] for h in hits]
    rng.shuffle(ids)
    for h, new_id in zip(hits, ids):
        struct.pack_into("<H", lss, h["abs_off"], new_id)
    return len(hits)


# Section 2 type-tag groups for enemy RE (see enemy_catalog.json).
# DO NOT auto-shuffle: boss minions (Blind One leeches etc.) are not yet
# separated from regular enemies. Whitelist-only when we enable this.
ENEMY_TAG_GROUPS = {
    1601: "actor_1601",  # 75 models, includes sec1-linked 377/381/441/445
    1602: "actor_1602",  # 42 models
    1609: "actor_1609",  # 46 models
}
# Explicitly blocked from any enemy pool until verified
ENEMY_DENY_TAGS = {
    1608,  # bulk 180 models — massive false-positive rate in part5
    1, 5, 7,  # geometry
}
# Models seen near boss name strings — deny until proven safe
BOSS_PROXIMITY_MODELS = {
    2304, 72, 1440, 579, 1345, 258, 910, 781, 974,  # Blind One area
    376, 384, 1912, 488, 286, 260, 902, 272, 912,  # Queen area
    115, 2353, 778,  # Mother area
}


def load_section2_tags(lss: bytes) -> List[int]:
    sec2, _, _ = get_section(lss, 2)
    n_models = read_u32(sec2, 4)
    return list(struct.unpack_from("<" + "H" * n_models, sec2, 8))


def cmd_list_enemies(path: Path) -> None:
    """Dry-run: report section-2 actor tag groups. No shuffling."""
    data = path.read_bytes()
    tags = load_section2_tags(data)
    print(f"Section 2: {len(tags)} model type tags")
    print()
    print("Candidate enemy/NPC tag groups (NOT shuffled yet):")
    for tag, label in sorted(ENEMY_TAG_GROUPS.items()):
        models = [i for i, t in enumerate(tags) if t == tag]
        print(f"  tag {tag} ({label}): {len(models)} models")
        print(f"    ids: {models[:15]}{'...' if len(models) > 15 else ''}")
    print()
    print("Denied / blocked:")
    print(f"  geometry tags 1/5/7")
    print(f"  bulk tag 1608 ({sum(1 for t in tags if t == 1608)} models) — false-positive risk")
    print(f"  boss-proximity model deny-list: {len(BOSS_PROXIMITY_MODELS)} entries")
    print()
    print("Policy: whitelist-only. Boss minions (e.g. Blind One green leeches)")
    print("must be explicitly identified before any enemy model shuffle ships.")
    print("See enemy_catalog.json for full notes.")


def get_map_catalog() -> dict:
    """Load map_catalog.json if present."""
    p = Path(__file__).with_name("map_catalog.json")
    if p.exists():
        import json
        return json.loads(p.read_text())
    return {"maps": {}, "aliases": {}}


def spawn_record_map_id(rec: bytes) -> Optional[int]:
    """Extract likely map index from a 20-byte section-8 position record."""
    if len(rec) < 20:
        return None
    fifth = struct.unpack_from("<I", rec, 16)[0]
    return fifth & 0xFFFF


def cmd_list_maps(path: Path) -> None:
    cat = get_map_catalog()
    if not cat.get("maps"):
        # build from file
        data = path.read_bytes()
        sec5, _, _ = get_section(data, 5)
        n5 = read_u32(sec5, 0)
        offs5 = [read_u32(sec5, 4 + i * 4) for i in range(n5)]
        print(f"Maps in {path.name}: {n5}")
        for mi in range(n5):
            a = offs5[mi]
            b = offs5[mi + 1] if mi + 1 < n5 else len(sec5)
            sub = sec5[a:b]
            pc = read_u32(sub, 0)
            name = f"map_{mi}"
            if pc >= 9:
                poffs = [read_u32(sub, 4 + i * 4) for i in range(pc)]
                trailer = sub[poffs[8]:]
                name = trailer.split(b"\x00")[0].decode("ascii", errors="ignore").strip() or name
            print(f"  [{mi:3d}] {name}")
        return
    print("Map catalog aliases:")
    for alias, ids in sorted(cat.get("aliases", {}).items()):
        print(f"  {alias}: {ids}")
    print("\nBeta note: Fireborn/Raptor/MP characters are NOT in the SP LSS.")
    print("Spawn bias can force starts into Blind Lair / River of Souls for testing.")


def cmd_shuffle_spawns_biased(path: Path, seed: Optional[int], out: Optional[Path],
                               map_filter: Optional[str] = None) -> None:
    """Shuffle spawns, optionally restricting to maps matching an alias or ID list.

    map_filter: alias name (blind, river, hive, ...) or comma-separated map indices.
    When set, only spawn records whose sector map-id is in the set are kept as
    the player-start pool; other records are left in place but the shuffled
    positions among the filtered set are redistributed.
    """
    data = bytearray(path.read_bytes())
    sec, _, _ = get_section(bytes(data), WARPS_SECTION)
    sec_ba = bytearray(sec)
    records = find_position_records(bytes(sec_ba))
    if len(records) < 2:
        print("Not enough spawn records.")
        return

    target_maps: Optional[set] = None
    if map_filter:
        cat = get_map_catalog()
        aliases = cat.get("aliases", {})
        if map_filter in aliases:
            target_maps = set(aliases[map_filter])
            print(f"Filter alias '{map_filter}' -> maps {sorted(target_maps)}")
        else:
            try:
                target_maps = set(int(x.strip()) for x in map_filter.split(","))
                print(f"Filter maps: {sorted(target_maps)}")
            except ValueError:
                print(f"Unknown map filter '{map_filter}'. Use alias or comma-separated indices.")
                print(f"Aliases: {list(aliases.keys())}")
                return

    if target_maps is not None:
        # Partition records by map membership
        primary = []   # in target maps — these get shuffled among themselves
        for off, rec in records:
            mid = spawn_record_map_id(rec)
            if mid in target_maps:
                primary.append((off, rec))
        if len(primary) < 2:
            print(f"Only {len(primary)} spawn(s) in target maps — need at least 2.")
            return
        rng = random.Random(seed)
        blocks = [b for _, b in primary]
        rng.shuffle(blocks)
        for (off, _), nb in zip(primary, blocks):
            sec_ba[off:off + len(nb)] = nb
        n = len(primary)
        print(f"Biased shuffle: {n} spawns within target maps (seed={seed}).")
    else:
        n = shuffle_positions(sec_ba, seed)
        print(f"Shuffled {n} spawn/warp positions (seed={seed}).")

    patch_section(data, WARPS_SECTION, bytes(sec_ba))
    if out is None:
        tag = map_filter or "all"
        suffix = f"_spawns_{tag}_seed{seed}" if seed is not None else f"_spawns_{tag}"
        out = path.with_name(f"{path.stem}{suffix}.lss")
    out.write_bytes(data)
    print(f"Wrote: {out}")


def cmd_list_weapons(path: Path) -> None:
    data = path.read_bytes()
    hits = find_weapon_model_hits(data)
    print(f"Weapon model-ID hits in section 5 part5: {len(hits)}")
    by_name = Counter(h["name"] for h in hits)
    print("By type:")
    for name, c in by_name.most_common():
        print(f"  {c:4d}  {name}")
    print("\nFirst 30:")
    for h in hits[:30]:
        print(f"  map={h['map']:3d} +0x{h['local_off']:04x}  {h['name']} ({h['model_id']})")


def cmd_shuffle_weapons(path: Path, seed: Optional[int], out: Optional[Path]) -> None:
    data = bytearray(path.read_bytes())
    n = shuffle_weapon_models(data, seed)
    if n < 2:
        print("Not enough weapon model hits to shuffle.")
        return
    if out is None:
        suffix = f"_weapons_seed{seed}" if seed is not None else "_weapons"
        out = path.with_name(f"{path.stem}{suffix}.lss")
    out.write_bytes(data)
    print(f"Shuffled {n} weapon model-ID hits (seed={seed}).")
    print("EXPERIMENTAL: some hits may be false positives in mesh data.")
    print(f"Wrote: {out}")


def cmd_info(path: Path) -> None:
    data = path.read_bytes()
    count, header_size, ends = parse_lss_header(data)
    ranges = section_ranges(header_size, ends)
    print(f"File          : {path.name}")
    print(f"Size          : {len(data):,} bytes")
    print(f"Section count : {count}")
    print(f"Header size   : {header_size} (0x{header_size:x})")
    print(f"RNC unpacker  : {'pure Python (vendored rnc)' if _RNC_AVAILABLE else 'NOT available'}")
    print()
    print(f"{'Idx':>3}  {'Name':<16}  {'Start':>10}  {'End':>10}  {'Size':>10}")
    print("-" * 58)
    for i, (start, end) in enumerate(ranges):
        name = SECTION_NAMES.get(i, "?")
        print(f"{i:3d}  {name:<16}  0x{start:08x}  0x{end:08x}  {end - start:10,}")


def cmd_list_spawns(path: Path) -> None:
    data = path.read_bytes()
    sec, _, _ = get_section(data, WARPS_SECTION)
    strict = find_position_records(sec)
    print(f"Strict positions: {len(strict)}\n")
    print(f"{'#':>4}  {'Offset':>8}  {'X':>10}  {'Y':>10}  {'Z':>10}")
    print("-" * 50)
    for i, (off, block) in enumerate(strict):
        x, y, z, rot = struct.unpack_from("<ffff", block, 0)
        print(f"{i:4d}  0x{off:04x}  {x:10.2f}  {y:10.2f}  {z:10.2f}")


def cmd_shuffle_spawns(path: Path, seed: Optional[int], out: Optional[Path]) -> None:
    data = bytearray(path.read_bytes())
    sec, _, _ = get_section(bytes(data), WARPS_SECTION)
    sec_ba = bytearray(sec)
    n = shuffle_positions(sec_ba, seed)
    if n < 2:
        raise RuntimeError("Not enough position records found to shuffle.")
    patch_section(data, WARPS_SECTION, bytes(sec_ba))
    if out is None:
        suffix = f"_spawns_seed{seed}" if seed is not None else "_spawns"
        out = path.with_name(f"{path.stem}{suffix}.lss")
    out.write_bytes(data)
    print(f"Shuffled {n} spawn/warp positions (seed={seed}).")
    print(f"Wrote: {out}")


def cmd_scan_sec5_dryrun(path: Path) -> None:
    data = path.read_bytes()
    print(f"=== DRY RUN SCAN: Section 5 ({path.name}) ===")
    print(f"RNC unpacker: {'pure Python (vendored rnc)' if _RNC_AVAILABLE else 'NOT available'}")
    if not _RNC_AVAILABLE:
        print("RNC module unavailable.")
        return
    ents, hist = scan_section5_entities(data)
    print(f"Candidate entity records : {len(ents)}")
    quest = sum(1 for e in ents if e["type_id"] in QUEST_ITEM_TYPE_IDS)
    print(f"Matching speculative quest IDs : {quest}")
    print()
    if hist:
        print(f"{'Type ID':>10}  {'Count':>6}  Flag")
        print("-" * 36)
        for tid, cnt in hist.most_common(40):
            flag = " [quest?]" if tid in QUEST_ITEM_TYPE_IDS else ""
            print(f"0x{tid:04x} ({tid:4d})  {cnt:6d}{flag}")
    if ents:
        print("\nSample:")
        print(f"{'Map':>4}  {'Type':>8}  {'X':>10}  {'Y':>10}  {'Z':>10}")
        print("-" * 50)
        for it in ents[:20]:
            x, y, z = it["pos"]
            print(f"{it.get('map_index', -1):4d}  0x{it['type_id']:04x}  {x:10.1f}  {y:10.1f}  {z:10.1f}")


def cmd_shuffle_items(path: Path, seed: Optional[int], out: Optional[Path]) -> None:
    """Safe v1: shuffle secondary half of section-8 records only. No section-5 writes."""
    data = bytearray(path.read_bytes())
    sec, _, _ = get_section(bytes(data), WARPS_SECTION)
    sec_ba = bytearray(sec)
    records = find_position_records(bytes(sec_ba))
    if len(records) < 4:
        raise RuntimeError("Not enough section-8 records for secondary shuffle.")
    mid = max(2, len(records) // 2)
    secondary = records[mid:]
    rng = random.Random(seed)
    blocks = [b for _, b in secondary]
    rng.shuffle(blocks)
    for (off, _), nb in zip(secondary, blocks):
        sec_ba[off:off + len(nb)] = nb
    patch_section(data, WARPS_SECTION, bytes(sec_ba))
    if out is None:
        suffix = f"_items_seed{seed}" if seed is not None else "_items"
        out = path.with_name(f"{path.stem}{suffix}.lss")
    out.write_bytes(data)
    print(f"Shuffled {len(secondary)} secondary section-8 records (seed={seed}).")
    print("Note: real health/ammo type-swap needs verified type IDs + RNC re-pack.")
    print(f"Wrote: {out}")


def cmd_shuffle_all(path: Path, seed: Optional[int], out: Optional[Path]) -> None:
    """Hybrid: spawn shuffle + experimental weapon model-ID shuffle."""
    data = bytearray(path.read_bytes())
    sec, _, _ = get_section(bytes(data), WARPS_SECTION)
    sec_ba = bytearray(sec)
    n_spawns = shuffle_positions(sec_ba, seed)
    patch_section(data, WARPS_SECTION, bytes(sec_ba))
    n_weap = shuffle_weapon_models(data, seed)
    if out is None:
        suffix = f"_all_seed{seed}" if seed is not None else "_all"
        out = path.with_name(f"{path.stem}{suffix}.lss")
    out.write_bytes(data)
    print(f"Hybrid randomizer (seed={seed}):")
    print(f"  spawns/warps shuffled: {n_spawns}")
    print(f"  weapon model-ID hits shuffled: {n_weap} (experimental)")
    print("  full pickup/enemy control: future runtime inject")
    print(f"Wrote: {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Turok 2 LSS hybrid randomizer (spawns + experimental weapons)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("info", "list-spawns", "list-weapons", "list-enemies", "scan-sec5-dryrun", "rnc-selftest"):
        p = sub.add_parser(name)
        p.add_argument("file", type=Path)
    for name in ("shuffle-spawns", "shuffle-weapons", "shuffle-items", "shuffle-all"):
        p = sub.add_parser(name)
        p.add_argument("file", type=Path)
        p.add_argument("--seed", type=int, default=None)
        p.add_argument("-o", "--output", type=Path, default=None)
        if name == "shuffle-spawns":
            p.add_argument("--maps", type=str, default=None,
                           help="Bias to map alias (blind,river,hive,marsh,port,lightship) or comma-separated map indices")
    p_maps = sub.add_parser("list-maps")
    p_maps.add_argument("file", type=Path)
    args = ap.parse_args()
    if args.cmd == "info":
        cmd_info(args.file)
    elif args.cmd == "list-spawns":
        cmd_list_spawns(args.file)
    elif args.cmd == "list-weapons":
        cmd_list_weapons(args.file)
    elif args.cmd == "list-enemies":
        cmd_list_enemies(args.file)
    elif args.cmd == "list-maps":
        cmd_list_maps(args.file)
    elif args.cmd == "shuffle-spawns":
        if getattr(args, "maps", None):
            cmd_shuffle_spawns_biased(args.file, args.seed, args.output, args.maps)
        else:
            cmd_shuffle_spawns(args.file, args.seed, args.output)
    elif args.cmd == "shuffle-weapons":
        cmd_shuffle_weapons(args.file, args.seed, args.output)
    elif args.cmd == "scan-sec5-dryrun":
        cmd_scan_sec5_dryrun(args.file)
    elif args.cmd == "rnc-selftest":
        cmd_rnc_selftest(args.file)
    elif args.cmd == "shuffle-items":
        cmd_shuffle_items(args.file, args.seed, args.output)
    elif args.cmd == "shuffle-all":
        cmd_shuffle_all(args.file, args.seed, args.output)


if __name__ == "__main__":
    main()
