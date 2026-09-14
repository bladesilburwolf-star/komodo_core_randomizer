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
    0: "models", 1: "actor_attrs?", 2: "model_type_tags", 3: "textures?",
    4: "particles", 5: "levels_A", 6: "levels_B", 7: "levels_C_UNSAFE",
    8: "warps_spawns", 9: "empty?", 10: "empty?", 11: "damage_scripts?",
    12: "meta_12", 13: "meta_13", 14: "meta_14", 15: "meta_15",
    16: "gui_textures", 17: "gui_tex_defs", 18: "cinema_story",
    19: "progression_UNSAFE", 20: "empty?",
}

# In-game trial notes for experimental section scrambles (expand as tested)
SECTION_EFFECTS = {
    2: (
        "model type tags — enemies/buildings/map pieces/keys/pickups can despawn "
        "across save-portals and death; do not scramble geometry tags 1/5/7"
    ),
    4: (
        "particles chaos — boots OK; enemy weapons/blood/ammo FX/gun sounds off; "
        "weaker enemies; stronger claw; invisible portals; +10-15 FPS"
    ),
    7: "UNSAFE — crash in first-key room",
    11: (
        "damage/scripts candidate — player takes more damage; rare crash on "
        "lever/gate before 2nd child save"
    ),
    18: "cinema/story/Adon — 198 named sequences; do not blind-scramble",
    19: "UNSAFE — progression/key flags; crash in key rooms",
}
# Experimental scramble policy:
#   SAFE_EXPERIMENTAL — known bootable with documented side effects
#   SECTION_UNSAFE — crash on load or progression break (blocked)
# Everything else: blocked until trial proves otherwise (user: many crash / meta noop)
SECTION_SAFE_EXPERIMENTAL = {4, 11}  # particles; damage/scripts candidate
SECTION_SOFT = {2}  # model tags — despawn risk, opt-in only
SECTION_UNSAFE = {
    0, 1, 3, 5, 6, 7, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20,
}
WARPS_SECTION = 8
# Boss arena map indices (from map_catalog)
BOSS_MAP_IDS = {1, 2, 3, 4}  # Blind One, Queen, Mother, Primagen
CINEMA_MAP_MIN = 5  # cinema maps start around here; exclude from gameplay if needed

def _rec_map_id(rec: bytes):
    if len(rec) < 20:
        return None
    return struct.unpack_from("<I", rec, 16)[0] & 0xFFFF


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


def shuffle_positions(
    sec: bytearray,
    seed: Optional[int] = None,
    preset: str = "all",
    map_ids: Optional[set] = None,
) -> int:
    """Shuffle spawn positions.

    preset:
      all     — every parsed position record
      boss    — only BOSS_MAP_IDS (1–4)
      no_boss — exclude boss map ids
    map_ids: optional explicit set (overrides preset when provided)
    """
    records = find_position_records(bytes(sec))
    if map_ids is not None:
        target = set(map_ids)
    elif preset == "boss":
        target = set(BOSS_MAP_IDS)
    elif preset == "no_boss":
        target = None  # special: exclude bosses
    else:
        target = None  # all

    if preset == "no_boss":
        filtered = [(o, r) for o, r in records if _rec_map_id(r) not in BOSS_MAP_IDS]
    elif target is not None:
        filtered = [(o, r) for o, r in records if _rec_map_id(r) in target]
    else:
        filtered = records

    if len(filtered) < 2:
        return 0
    rng = random.Random(seed)
    blocks = [b for _, b in filtered]
    rng.shuffle(blocks)
    for (off, _), new_block in zip(filtered, blocks):
        sec[off:off + len(new_block)] = new_block
    return len(filtered)


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


def cmd_list_spawns(path: Path, preset: str = "all") -> None:
    data = path.read_bytes()
    sec, _, _ = get_section(data, WARPS_SECTION)
    strict = find_position_records(sec)
    if preset == "boss":
        strict = [(o, r) for o, r in strict if _rec_map_id(r) in BOSS_MAP_IDS]
    elif preset == "no_boss":
        strict = [(o, r) for o, r in strict if _rec_map_id(r) not in BOSS_MAP_IDS]
    print(f"Positions: {len(strict)} (preset={preset})\n")
    print(f"{'#':>4}  {'Offset':>8}  {'X':>10}  {'Y':>10}  {'Z':>10}  map")
    print("-" * 58)
    for i, (off, block) in enumerate(strict[:50]):
        x, y, z, rot = struct.unpack_from("<ffff", block, 0)
        mid = _rec_map_id(block)
        boss = " BOSS" if mid in BOSS_MAP_IDS else ""
        print(f"{i:4d}  {off:8d}  {x:10.2f}  {y:10.2f}  {z:10.2f}  {mid}{boss}")
    if len(strict) > 50:
        print(f"  ... {len(strict) - 50} more")

def cmd_shuffle_spawns(
    path: Path,
    seed: Optional[int],
    out: Optional[Path],
    preset: str = "all",
    maps: Optional[str] = None,
) -> None:
    """Shuffle spawns. preset=all|boss|no_boss, or maps=alias/indices (legacy)."""
    if maps:
        cmd_shuffle_spawns_biased(path, seed, out, maps)
        return
    data = bytearray(path.read_bytes())
    sec, _, _ = get_section(bytes(data), WARPS_SECTION)
    sec_ba = bytearray(sec)
    n = shuffle_positions(sec_ba, seed, preset=preset)
    if n < 2:
        raise RuntimeError(f"Not enough position records for preset '{preset}' ({n}).")
    patch_section(data, WARPS_SECTION, bytes(sec_ba))
    if out is None:
        suffix = f"_spawns_{preset}_seed{seed}" if seed is not None else f"_spawns_{preset}"
        out = path.with_name(f"{path.stem}{suffix}.lss")
    out.write_bytes(data)
    print(f"Shuffled {n} spawn/warp positions (preset={preset}, seed={seed}).")
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


# ----- Section 4 particles (722 systems, no RNC) -----

def _parse_sec4_particles(sec: bytes):
    """Return (ids, records_base, list of 60-byte bytearray records)."""
    if len(sec) < 32:
        raise ValueError("sec4 too small")
    bc = read_u32(sec, 0)
    if bc < 3:
        raise ValueError(f"sec4 unexpected block_count={bc}")
    offs = [read_u32(sec, 4 + i * 4) for i in range(bc + 1)]
    # block1: IDs
    a1, b1 = offs[1], offs[2]
    rsz1, rcnt1 = struct.unpack_from("<II", sec, a1)
    if rsz1 != 4:
        raise ValueError(f"sec4 block1 rsz={rsz1}")
    ids = [struct.unpack_from("<I", sec, a1 + 8 + i * 4)[0] for i in range(rcnt1)]
    # block2: 60-byte records
    a2 = offs[2]
    rsz2, rcnt2 = struct.unpack_from("<II", sec, a2)
    if rsz2 != 60 or rcnt2 != rcnt1:
        raise ValueError(f"sec4 block2 rsz={rsz2} rcnt={rcnt2}")
    base = a2 + 8
    recs = [bytearray(sec[base + i * 60: base + (i + 1) * 60]) for i in range(rcnt2)]
    return ids, base, recs


def cmd_list_particles(path: Path) -> None:
    data = path.read_bytes()
    sec, _, _ = get_section(data, 4)
    ids, base, recs = _parse_sec4_particles(sec)
    print(f"Section 4 particles: {len(recs)} systems, {len(set(ids))} unique IDs")
    print(f"Record table @ +{base}")
    from collections import Counter
    print("Top particle IDs:", Counter(ids).most_common(15))
    print("Type-byte patterns (+8..+11):")
    print(Counter(tuple(r[8:12]) for r in recs).most_common(12))
    print("\nFirst 20:")
    for i in range(min(20, len(recs))):
        tb = list(recs[i][8:12])
        ptrs = [struct.unpack_from("<I", recs[i], o)[0] for o in (24, 36, 48, 56)]
        print(f"  [{i:3d}] id={ids[i]:5d} type={tb} ptrs={ptrs}")


def cmd_disable_particles(
    path: Path,
    out: Optional[Path],
    ids: Optional[list] = None,
    type_bytes: Optional[tuple] = None,
    index_range: Optional[tuple] = None,
) -> None:
    """Null out particle systems matching filters (zero the 60-byte record).

    Isolation trial: disable by id, type pattern, or index range, boot, see what vanished.
    """
    data = bytearray(path.read_bytes())
    sec, start, end = get_section(bytes(data), 4)
    sec_ba = bytearray(sec)
    pid_list, base, recs = _parse_sec4_particles(sec)
    killed = 0
    for i, rec in enumerate(recs):
        hit = False
        if ids is not None and pid_list[i] in ids:
            hit = True
        if type_bytes is not None and tuple(rec[8:12]) == type_bytes:
            hit = True
        if index_range is not None:
            lo, hi = index_range
            if lo <= i <= hi:
                hit = True
        if hit:
            # Zero record but keep size — soft-disable
            for j in range(60):
                rec[j] = 0
            sec_ba[base + i * 60: base + (i + 1) * 60] = rec
            killed += 1
    if killed == 0:
        print("No particles matched filters.")
        return
    data[start:end] = sec_ba
    if out is None:
        out = path.with_name(f"{path.stem}_noparticles.lss")
    out.write_bytes(data)
    print(f"Disabled {killed}/{len(recs)} particle systems.")
    print(f"Wrote: {out}")



def experimental_shuffle_section(data: bytes, index: int, seed: Optional[int]) -> bytes:
    """Trial-and-error: scramble amount-like u32 words in a section.

    Skips section 8 (use spawn presets). Section 5 is huge/RNC-heavy — only
    touches the first RNC block if present and pack fits in-place.
    """
    if index == WARPS_SECTION:
        raise ValueError("Use spawn shuffle for section 8")
    if index in SECTION_UNSAFE:
        print(f"  section {index} BLOCKED (unsafe/untested): {SECTION_EFFECTS.get(index, 'crash or noop')}")
        return data
    if index not in SECTION_SAFE_EXPERIMENTAL and index not in SECTION_SOFT:
        print(f"  section {index} BLOCKED (not on safe list — trial first)")
        return data
    if index in SECTION_SOFT:
        print(f"  section {index} SOFT WARNING: {SECTION_EFFECTS.get(index, 'despawn risk')}")
    if index in SECTION_EFFECTS:
        print(f"  section {index} known effects: {SECTION_EFFECTS[index]}")
    sec, start, end = get_section(data, index)
    rng = random.Random(seed)
    ba = bytearray(sec)

    def scramble(buf: bytearray) -> int:
        hits = []
        for off in range(0, len(buf) - 3, 4):
            v = struct.unpack_from("<I", buf, off)[0]
            if 1 <= v <= 500:
                hits.append(off)
        if len(hits) < 4:
            return 0
        vals = [struct.unpack_from("<I", buf, off)[0] for off in hits]
        rng.shuffle(vals)
        for off, v in zip(hits, vals):
            struct.pack_into("<I", buf, off, v)
        return len(hits)

    n = scramble(ba)
    if n == 0:
        print(f"  section {index}: no scramble candidates")
        return data
    if len(ba) != len(sec):
        print(f"  section {index}: size change not supported in experimental mode")
        return data
    out = bytearray(data)
    out[start:end] = ba
    print(f"  section {index}: scrambled {n} small-int fields")
    return bytes(out)


def cmd_shuffle(
    path: Path,
    seed: Optional[int],
    out: Optional[Path],
    do_spawns: bool = True,
    do_weapons: bool = False,
    sections: Optional[list] = None,
    preset: str = "all",
) -> None:
    """Unified shuffle entry used by GUI."""
    rng_seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    data = bytearray(path.read_bytes())
    print(f"shuffle seed={rng_seed}")

    if do_spawns:
        sec, _, _ = get_section(bytes(data), WARPS_SECTION)
        sec_ba = bytearray(sec)
        n = shuffle_positions(sec_ba, rng_seed, preset=preset)
        patch_section(data, WARPS_SECTION, bytes(sec_ba))
        print(f"  sec8 spawns: {n} (preset={preset})")

    if do_weapons:
        n_w = shuffle_weapon_models(data, rng_seed + 1)
        print(f"  weapon model-IDs: {n_w} (experimental, may be unstable)")

    for si in sections or []:
        if si == WARPS_SECTION:
            continue
        try:
            data = bytearray(experimental_shuffle_section(bytes(data), si, rng_seed + 10 + si))
        except Exception as e:
            print(f"  sec{si} experimental FAILED: {e}")

    if out is None:
        out = path.with_name(f"{path.stem}_rand_seed{rng_seed}.lss")
    out.write_bytes(data)
    print(f"Wrote: {out} ({len(data)} bytes)")



def main() -> None:
    ap = argparse.ArgumentParser(description="Turok 2 LSS hybrid randomizer (spawns + experimental weapons)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("info", "list-spawns", "list-weapons", "list-enemies", "list-particles", "scan-sec5-dryrun", "rnc-selftest"):
        p = sub.add_parser(name)
        p.add_argument("file", type=Path)
        if name == "list-spawns":
            p.add_argument("--preset", choices=("all", "boss", "no_boss"), default="all")
    for name in ("shuffle-spawns", "shuffle-weapons", "shuffle-items", "shuffle-all"):
        p = sub.add_parser(name)
        p.add_argument("file", type=Path)
        p.add_argument("--seed", type=int, default=None)
        p.add_argument("-o", "--output", type=Path, default=None)
        if name == "shuffle-spawns":
            p.add_argument("--maps", type=str, default=None,
                           help="Bias to map alias (blind,river,hive,boss,...) or comma-separated map indices")
            p.add_argument("--preset", choices=("all", "boss", "no_boss"), default="all")
    p_sh = sub.add_parser("shuffle")
    p_sh.add_argument("file", type=Path)
    p_sh.add_argument("--seed", type=int, default=None)
    p_sh.add_argument("-o", "--output", type=Path, default=None)
    p_sh.add_argument("--spawns", action="store_true")
    p_sh.add_argument("--weapons", action="store_true")
    p_sh.add_argument("--sections", type=str, default="")
    p_sh.add_argument("--preset", choices=("all", "boss", "no_boss"), default="all")
    p_dp = sub.add_parser("disable-particles")
    p_dp.add_argument("file", type=Path)
    p_dp.add_argument("-o", "--output", type=Path, default=None)
    p_dp.add_argument("--ids", type=str, default=None, help="Comma particle IDs e.g. 1,23,38")
    p_dp.add_argument("--type", type=str, default=None, help="Type bytes e.g. 2,0,0,0")
    p_dp.add_argument("--index", type=str, default=None, help="Index or range e.g. 0-50 or 12")
    p_maps = sub.add_parser("list-maps")
    p_maps.add_argument("file", type=Path)
    args = ap.parse_args()
    if args.cmd == "info":
        cmd_info(args.file)
    elif args.cmd == "list-spawns":
        cmd_list_spawns(args.file, preset=getattr(args, "preset", "all"))
    elif args.cmd == "list-weapons":
        cmd_list_weapons(args.file)
    elif args.cmd == "list-enemies":
        cmd_list_enemies(args.file)
    elif args.cmd == "list-particles":
        cmd_list_particles(args.file)
    elif args.cmd == "disable-particles":
        id_list = [int(x) for x in args.ids.split(",")] if args.ids else None
        tb = tuple(int(x) for x in args.type.split(",")) if args.type else None
        ir = None
        if args.index:
            if "-" in args.index:
                a, b = args.index.split("-", 1)
                ir = (int(a), int(b))
            else:
                ir = (int(args.index), int(args.index))
        cmd_disable_particles(args.file, args.output, ids=id_list, type_bytes=tb, index_range=ir)
    elif args.cmd == "list-maps":
        cmd_list_maps(args.file)
    elif args.cmd == "shuffle-spawns":
        cmd_shuffle_spawns(
            args.file, args.seed, args.output,
            preset=getattr(args, "preset", "all"),
            maps=getattr(args, "maps", None),
        )
    elif args.cmd == "shuffle":
        secs = [int(x) for x in args.sections.split(",") if x.strip().isdigit()]
        if not args.spawns and not args.weapons and not secs:
            ap.error("Enable --spawns and/or --weapons and/or --sections")
        cmd_shuffle(
            args.file, args.seed, args.output,
            do_spawns=args.spawns, do_weapons=args.weapons,
            sections=secs, preset=args.preset,
        )
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
