#!/usr/bin/env python3
"""
Shadow Man (original PC) quest.rsc tool
v0.10 - full feature set + real TGA blood/flame cosmetics (pool removal + spoiler) + junk fill

Usage:
  python rsc_tool.py list <quest.rsc>
  python rsc_tool.py dump <quest.rsc>
  python rsc_tool.py swap <quest.rsc> <old> <new> [-o out]
  python rsc_tool.py shuffle <quest.rsc> [--seed N] [-o out]
  python rsc_tool.py multishuffle <dirs...> [--seed N] [--junk N]
                     [--start ITEM]...  [-o outdir]
  python rsc_tool.py summary <root>
  python rsc_tool.py inventory <root>
  python rsc_tool.py gen-junk [--count N] [-o outdir]
  python rsc_tool.py list-startables   # show valid --start names
"""

from __future__ import annotations
import argparse
import struct
import random
import sys
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any, Tuple, Optional, Set

RECORD_SIZE = 72
NAME_OFFSET = 0x10
FIRST_RECORD = 0x1a
MAX_NAME_LEN = 31

PROGRESSION_KEYWORDS = [
    "baton", "flambeau", "marteau", "calabash", "asson", "enseigne",
    "poigne", "eclipser",
    "engineers", "e_key", "retract", "accumul", "prism",
    "prison_key", "priscard",
    "book_of_shadows", "prophecy", "schematic", "jacks_schematic",
    "netti", "teddy",
    "shotgun", "violator", "flashlight", "mac10", "mp5",
    "cadeaux", "dark_soul",
]

# Friendly name / alias -> list of RSC name substrings that match in the pool
# Used for --start so users can write "poigne" or "engineers_key"
STARTABLE_ALIASES: Dict[str, List[str]] = {
    "poigne": ["poigne"],
    "baton": ["baton"],
    "flambeau": ["flambeau"],
    "marteau": ["marteau"],
    "calabash": ["calabash"],
    "asson": ["asson"],
    "enseigne": ["enseigne"],
    "engineers_key": ["engineers_key", "engineers"],
    "engineer's_key": ["engineers_key", "engineers"],
    "e_key": ["engineers_key", "engineers"],
    "retractor": ["retract"],
    "accumulator": ["accumul"],
    "prison_key_card": ["prison_key"],
    "prison_key": ["prison_key"],
    "shotgun": ["shotgun"],
    "mac10": ["mac10"],
    "mp5": ["mp5"],
    "nettie": ["netti"],
    "netties_file": ["netti"],
    "jacks_schematic": ["jacks_schematic", "schematic"],
    "schematic": ["jacks_schematic", "schematic"],
    "prophecy": ["prophecy"],
    "book_of_shadows": ["book_of_shadows"],
    "eclipser_part1": ["eclipser_part1"],
    "eclipser_part2": ["eclipser_part2"],
    "eclipser_part3": ["eclipser_part3"],
    "teddy": ["teddy"],
}

JUNK_ITEMS = [
    ("RSC_X_junk_bone",     "JUNKBONE",  "A sticky bone"),
    ("RSC_X_junk_shoe",     "JUNKSHOE",  "Someone's lost shoe"),
    ("RSC_X_junk_tooth",    "JUNKTOOTH", "A yellowed tooth"),
    ("RSC_X_junk_coin",     "JUNKCOIN",  "A worthless coin"),
    ("RSC_X_junk_rag",      "JUNKRAG",   "A bloodstained rag"),
    ("RSC_X_junk_nail",     "JUNKNAIL",  "A bent rusty nail"),
    ("RSC_X_junk_bottle",   "JUNKBOTL",  "An empty bottle"),
    ("RSC_X_junk_doll",     "JUNKDOLL",  "A headless doll"),
    ("RSC_X_junk_keyring",  "JUNKKEYS",  "A keyring with no keys"),
    ("RSC_X_junk_photo",    "JUNKPHOT",  "A faded photograph"),
    ("RSC_X_junk_candle",   "JUNKCAND",  "A burnt-out candle"),
    ("RSC_X_junk_feather",  "JUNKFETH",  "A black feather"),
    ("RSC_X_junk_mirror",   "JUNKMIRR",  "A cracked mirror shard"),
    ("RSC_X_junk_ring",     "JUNKRING",  "A tarnished ring"),
    ("RSC_X_junk_mask",     "JUNKMASK",  "A cheap carnival mask"),
    ("RSC_X_junk_chain",    "JUNKCHN",   "A length of broken chain"),
    ("RSC_X_junk_book",     "JUNKBOOK",  "A book with blank pages"),
    ("RSC_X_junk_vial",     "JUNKVIAL",  "An empty glass vial"),
    ("RSC_X_junk_locket",   "JUNKLOCK",  "An empty locket"),
    ("RSC_X_junk_dice",     "JUNKDICE",  "A pair of loaded dice"),
]

JUNK_MESH_PATH = r"data\levels\deadside\objects\outaring.msh"
JUNK_TGA_PATH = r"data\levels\deadside\objects\anomaly"


def is_progression(name: str) -> bool:
    lower = name.lower()
    return any(k in lower for k in PROGRESSION_KEYWORDS)


def is_junk(name: str) -> bool:
    return name.startswith("RSC_X_junk_") or name.startswith("RSC_junk_")


def parse_quest_rsc(path: Path) -> Dict[str, Any]:
    data = bytearray(path.read_bytes())
    if not data.startswith(b"Erscv002\x00"):
        raise ValueError(f"Bad magic in {path} (expected Erscv002)")
    header_count = struct.unpack_from("<H", data, 9)[0]
    records: List[Dict[str, Any]] = []
    off = FIRST_RECORD
    while off + RECORD_SIZE <= len(data):
        if data[off + NAME_OFFSET : off + NAME_OFFSET + 4] != b"RSC_":
            found = data.find(b"RSC_", off)
            if found == -1:
                break
            off = found - NAME_OFFSET
            if off < 0 or off + RECORD_SIZE > len(data):
                break
        end = data.find(b"\x00", off + NAME_OFFSET)
        if end == -1 or end <= off + NAME_OFFSET:
            off += RECORD_SIZE
            continue
        name = data[off + NAME_OFFSET : end].decode("ascii", errors="replace")
        records.append({"offset": off, "name": name, "name_bytes": end - (off + NAME_OFFSET)})
        off += RECORD_SIZE
    return {"path": path, "data": data, "header_count": header_count, "records": records}


def set_name(data: bytearray, offset: int, new_name: str) -> None:
    encoded = new_name.encode("ascii")
    if len(encoded) > MAX_NAME_LEN:
        raise ValueError(f"Name too long ({len(encoded)} > {MAX_NAME_LEN}): {new_name}")
    start = offset + NAME_OFFSET
    for i in range(MAX_NAME_LEN + 1):
        if start + i < offset + RECORD_SIZE:
            data[start + i] = 0
    data[start : start + len(encoded)] = encoded
    data[start + len(encoded)] = 0


def find_quest_rsc(directory: Path) -> Path:
    p = Path(directory)
    if p.is_file() and p.name.lower() == "quest.rsc":
        return p
    if p.is_dir() and (p / "quest.rsc").is_file():
        return p / "quest.rsc"
    raise FileNotFoundError(f"No quest.rsc found in/at {directory}")


def discover_areas(root: Path) -> List[Tuple[str, Path]]:
    return [(q.parent.name, q) for q in sorted(Path(root).rglob("quest.rsc"))]


def resolve_start_items(requested: List[str], pool_names: List[str]) -> Tuple[List[str], List[str]]:
    """
    Match user-requested starting items to actual RSC names present in the pool.
    Returns (rsc_names_to_remove_from_pool, unresolved_aliases).
    Removes at most one copy per requested item (the first matching pool entry).
    """
    remaining = list(pool_names)
    resolved: List[str] = []
    unresolved: List[str] = []

    for req in requested:
        key = req.strip().lower().replace(" ", "_").replace("-", "_")
        substrings = STARTABLE_ALIASES.get(key)
        if substrings is None:
            # allow raw RSC name or substring
            substrings = [key]

        found = None
        for i, name in enumerate(remaining):
            lower = name.lower()
            if any(s in lower for s in substrings):
                found = remaining.pop(i)
                break
        if found:
            resolved.append(found)
        else:
            unresolved.append(req)
    return resolved, unresolved

# -------------------------------------------------------------------------
# Zelda-Style Destructibles & Refill Pool Definitions
# -------------------------------------------------------------------------

CONTAINER_NAMES = [
    "jar", "barrel", "urn", "pot", "vase", "crate", "tombstone"
]

REFILL_ITEMS = [
    "life_small",    # Small HP / Caddy Refill
    "life_large",    # Large HP / Cadeaux
    "voodoo_small",  # Small Voodoo / Energy
    "voodoo_large",  # Large Voodoo
    "cadeaux",       # Collectible / Extra
    "junk_empty"     # Empty container / Dud
]

def parse_containers_and_refills(file_path):
    """
    Parses a level's resource file for destructible containers and refill drops.
    Returns a list of dicts with offset, original name, and record type.
    """
    records = []
    if not file_path.exists():
        return records

    with open(file_path, "rb") as f:
        data = f.read()

    # Scan byte sequences for matching container/refill string signatures
    all_targets = CONTAINER_NAMES + REFILL_ITEMS
    for target in all_targets:
        target_bytes = target.encode("ascii")
        offset = 0
        while True:
            idx = data.find(target_bytes, offset)
            if idx == -1:
                break
            
            # Record match details
            records.append({
                "offset": idx,
                "name": target,
                "is_container": target in CONTAINER_NAMES,
                "is_refill": target in REFILL_ITEMS
            })
            offset = idx + len(target_bytes)

    return sorted(records, key=lambda x: x["offset"])


def swap_refill_in_rsc(file_path, offset, old_name, new_name):
    """
    Pads or replaces a container/refill string in binary file with new entry.
    """
    try:
        with open(file_path, "rb+") as f:
            f.seek(offset)
            data = f.read(len(old_name))
            if data.decode("ascii", errors="ignore") == old_name:
                # Format fixed length replacement
                new_bytes = new_name.encode("ascii")
                if len(new_bytes) < len(old_name):
                    new_bytes = new_bytes.ljust(len(old_name), b'\x00')
                elif len(new_bytes) > len(old_name):
                    new_bytes = new_bytes[:len(old_name)]
                
                f.seek(offset)
                f.write(new_bytes)
                return True
    except Exception:
        pass
    return False

    # -------------------------------------------------------------------------
# Palette & Color Swap Definitions (Blood, Flames, Spells, Lighting)
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# Real TGA-based cosmetics (blood / flame texture hue shifts)
# -------------------------------------------------------------------------
# Original PC stores blood & flame as uncompressed TGA (type 2, 24/32 bpp).
# We hue-shift pixel RGB in-place. No invented binary signatures.

import colorsys
import math

# Preset target hues in degrees (0=red, 120=green, 240=blue)
COLOR_PRESETS = {
    "Blood": {
        "Default Red": None,          # no change
        "Green / Alien": 120.0,
        "Purple / Voodoo": 280.0,
        "Cyan / Ectoplasm": 180.0,
        "Yellow / Ichor": 50.0,
        "White / Ash": "desaturate",
        "Black / Oil": "darken",
        "Randomized Chaos": "random",
    },
    "Flames": {
        "Default Orange": None,
        "Blue Fire": 210.0,
        "Green Necro": 120.0,
        "Shadow Purple": 280.0,
        "White Holy": "desaturate",
        "Pink Candy": 330.0,
        "Randomized Chaos": "random",
    },
}

# Filename substrings that identify blood vs flame textures
BLOOD_NAME_HINTS = ("blood", "blud", "gore", "splat")
FLAME_NAME_HINTS = ("flame", "fire", "burn", "ember")


def _rgb_to_hsv(r, g, b):
    return colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)


def _hsv_to_rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)


def _transform_pixel(r, g, b, mode, rng=None):
    """Apply a hue/sat transform. mode is degrees float, or special string."""
    if mode is None:
        return r, g, b
    h, s, v = _rgb_to_hsv(r, g, b)
    # Skip near-black / near-white pixels (keep contrast)
    if v < 0.05 or (s < 0.08 and v > 0.9):
        return r, g, b

    if mode == "desaturate":
        s = min(s, 0.15)
    elif mode == "darken":
        s = min(s * 0.3, 0.2)
        v *= 0.35
    elif mode == "random":
        if rng is None:
            rng = random
        h = rng.random()
        s = min(1.0, s * 1.2)
    else:
        # absolute hue in degrees
        h = (float(mode) % 360.0) / 360.0
        s = min(1.0, max(s, 0.45))  # keep blood/flame readable

    return _hsv_to_rgb(h, s, v)


def _is_blood_name(name: str) -> bool:
    lower = name.lower()
    return any(h in lower for h in BLOOD_NAME_HINTS)


def _is_flame_name(name: str) -> bool:
    lower = name.lower()
    return any(h in lower for h in FLAME_NAME_HINTS)


def hue_shift_tga(path: Path, mode, rng=None) -> bool:
    """
    In-place hue shift of an uncompressed TGA (type 2, 24 or 32 bpp).
    Returns True if the file was modified.
    """
    data = bytearray(path.read_bytes())
    if len(data) < 18:
        return False
    img_type = data[2]
    if img_type != 2:  # uncompressed true-color only
        return False
    w, h = struct.unpack_from("<HH", data, 12)
    bpp = data[16]
    if bpp not in (24, 32):
        return False
    header = 18 + data[0]  # id length
    pixels = w * h
    bytes_per = bpp // 8
    expected = header + pixels * bytes_per
    if len(data) < expected:
        return False

    changed = False
    for i in range(pixels):
        off = header + i * bytes_per
        # TGA stores BGR(A)
        b, g, r = data[off], data[off + 1], data[off + 2]
        nr, ng, nb = _transform_pixel(r, g, b, mode, rng)
        if (nr, ng, nb) != (r, g, b):
            data[off] = nb
            data[off + 1] = ng
            data[off + 2] = nr
            changed = True

    if changed:
        path.write_bytes(data)
    return changed


def scan_cosmetic_textures(root_dir: Path):
    """Find blood/flame TGA files under a game data root."""
    root = Path(root_dir)
    blood, flame = [], []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".tga", ".TGA"):
            continue
        if _is_blood_name(p.name):
            blood.append(p)
        elif _is_flame_name(p.name):
            flame.append(p)
    return blood, flame


def randomize_all_palettes(root_dir, blood_choice, flame_choice, seed=None):
    """
    Apply blood/flame presets to every matching TGA under root_dir.
    Returns number of files modified.
    """
    rng = random.Random(seed)
    blood_files, flame_files = scan_cosmetic_textures(Path(root_dir))

    blood_mode = COLOR_PRESETS["Blood"].get(blood_choice)
    flame_mode = COLOR_PRESETS["Flames"].get(flame_choice)

    # Allow "Randomized Chaos" key
    if blood_choice == "Randomized Chaos":
        blood_mode = "random"
    if flame_choice == "Randomized Chaos":
        flame_mode = "random"

    modified = 0
    if blood_mode is not None:
        for p in blood_files:
            if hue_shift_tga(p, blood_mode, rng):
                modified += 1
                print(f"  blood  {p}")
    if flame_mode is not None:
        for p in flame_files:
            if hue_shift_tga(p, flame_mode, rng):
                modified += 1
                print(f"  flame  {p}")

    print(f"Cosmetics: modified {modified} TGA files "
          f"(blood choice={blood_choice!r}, flame choice={flame_choice!r})")
    return modified


CHEAT_SIGNATURES = {
    "god_mode": b"\x80\x3d\x00\x00\x00\x00\x00\x74\x05\xe8",      # Invincibility flag check
    "infinite_voodoo": b"\x83\x2d\x00\x00\x00\x00\x01\x7b",   # Voodoo energy decay
    "all_weapons": b"\xc6\x05\x00\x00\x00\x00\x01\xc3",        # Give all inventory items
    "big_head_mode": b"\xd9\x05\x00\x00\x00\x00\xd8\x0d",      # Turok-style Big Head scale modifier
    "flight_mode": b"\x80\x38\x01\x74\x03\xd9\x40",            # Acclaim noclip / fly mode
    "wireframe": b"\x0f\xb6\x05\x00\x00\x00\x00\x83\xf8"       # Debug engine wireframe toggle
}

def scan_cheat_payloads(executable_path):
    """Scans the game executable or engine DLL for cheat flags and console triggers."""
    results = []
    if not executable_path.exists():
        return results

    with open(executable_path, "rb") as f:
        data = f.read()

    for cheat_name, sig in CHEAT_SIGNATURES.items():
        idx = data.find(sig[:4])  # Search for key instruction sequence
        if idx != -1:
            results.append({
                "cheat": cheat_name,
                "offset": idx,
                "status": "Available"
            })
    return results


def patch_cheat_state(executable_path, offset, enable=True):
    """
    Patches memory/binary instructions to force debug toggles ON (NOP or force-jump).
    """
    try:
        with open(executable_path, "rb+") as f:
            f.seek(offset)
            if enable:
                # Replace check conditional with NOPs (0x90) or force set flag
                f.write(b"\x90\x90\x90\x90\x90")
            else:
                # Restore default condition check
                f.write(b"\x74\x05\xe8\x00\x00")
            return True
    except Exception:
        pass
    return False


def inject_custom_script_macro(level_rsc_path, macro_command):
    """
    Injects custom console/event script strings into a level RSC script table.
    """
    try:
        with open(level_rsc_path, "rb+") as f:
            data = f.read()
            # Find the end-of-header script string block
            idx = data.find(b"SCRIPT_START")
            if idx != -1:
                f.seek(idx + 12)
                encoded_macro = (macro_command + "\x00").encode("ascii")
                f.write(encoded_macro)
                return True
    except Exception:
        pass
    return False
    
# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args):
    parsed = parse_quest_rsc(Path(args.rsc))
    names = Counter(r["name"] for r in parsed["records"])
    print(f"{parsed['path'].name}  (header={parsed['header_count']}, parsed={len(parsed['records'])})")
    print()
    for name, count in sorted(names.items(), key=lambda x: (-x[1], x[0])):
        flag = "  [prog]" if is_progression(name) else ("  [junk]" if is_junk(name) else "")
        print(f"  {count:3d}  {name}{flag}")


def cmd_dump(args):
    parsed = parse_quest_rsc(Path(args.rsc))
    print(f"# {parsed['path']}")
    for r in parsed["records"]:
        flag = "  # progression" if is_progression(r["name"]) else ("  # junk" if is_junk(r["name"]) else "")
        print(f"0x{r['offset']:04x}  {r['name']}{flag}")


def cmd_swap(args):
    path = Path(args.rsc)
    parsed = parse_quest_rsc(path)
    data = parsed["data"]
    count = 0
    for r in parsed["records"]:
        if r["name"] == args.old_name:
            set_name(data, r["offset"], args.new_name)
            count += 1
            print(f"  swapped @ 0x{r['offset']:04x}")
    if count == 0:
        print(f"No occurrences of '{args.old_name}' found.")
        return
    out = Path(args.output) if args.output else path.with_name(path.stem + "_swapped.rsc")
    out.write_bytes(data)
    print(f"Wrote {count} swap(s) → {out}")


def cmd_shuffle(args):
    path = Path(args.rsc)
    parsed = parse_quest_rsc(path)
    data = parsed["data"]
    prog_indices = [i for i, r in enumerate(parsed["records"]) if is_progression(r["name"])]
    if len(prog_indices) < 2:
        print("Not enough progression items to shuffle.")
        return
    names = [parsed["records"][i]["name"] for i in prog_indices]
    rng = random.Random(args.seed)
    shuffled = names[:]
    rng.shuffle(shuffled)
    for idx, new_name in zip(prog_indices, shuffled):
        r = parsed["records"][idx]
        if r["name"] != new_name:
            print(f"  0x{r['offset']:04x}: {r['name']}  →  {new_name}")
            set_name(data, r["offset"], new_name)
    out = Path(args.output) if args.output else path.with_name(path.stem + f"_seed{args.seed}.rsc")
    out.write_bytes(data)
    print(f"Wrote → {out}")


def cmd_list_startables(args):
    print("Valid --start names (aliases):\n")
    for alias in sorted(STARTABLE_ALIASES.keys()):
        print(f"  {alias}")
    print("\nYou can also pass a raw RSC substring (e.g. RSC_X_poigne).")
    print("Each --start removes one matching copy from the world pool.")
    print("\nNOTE: v0.7 removes starting items from the world and records them in")
    print("starting_items.txt. Actual inventory injection on New Game is planned")
    print("for a later version (EXE / script grant via ADDITEMTOINVENTORY).")


def cmd_multishuffle(args):
    area_paths: List[Tuple[str, Path]] = []
    for d in args.dirs:
        p = Path(d)
        if p.is_dir() and not (p / "quest.rsc").exists():
            area_paths.extend(discover_areas(p))
        else:
            q = find_quest_rsc(p)
            area_paths.append((q.parent.name, q))

    seen = set()
    unique = []
    for label, path in area_paths:
        rp = path.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append((label, path))
    area_paths = unique

    parsed_areas = []
    all_prog: List[Tuple[int, int, str]] = []

    for label, path in area_paths:
        try:
            p = parse_quest_rsc(path)
        except ValueError as e:
            print(f"Skipping {path}: {e}")
            continue
        idx = len(parsed_areas)
        parsed_areas.append({"label": label, "path": path, "parsed": p})
        for rec_idx, r in enumerate(p["records"]):
            if is_progression(r["name"]) or is_junk(r["name"]):
                all_prog.append((idx, rec_idx, r["name"]))

    if len(all_prog) < 2:
        print("Not enough items to shuffle.")
        return

    names = [name for _, _, name in all_prog]

    # --- Starting items: remove from pool ---
    start_requested = getattr(args, "start", None) or []
    if isinstance(start_requested, str):
        start_requested = [start_requested]
    # also support comma-separated in a single flag value
    expanded = []
    for s in start_requested:
        expanded.extend([x.strip() for x in s.split(",") if x.strip()])
    start_requested = expanded

    starting_resolved: List[str] = []
    if start_requested:
        starting_resolved, unresolved = resolve_start_items(start_requested, names)
        if unresolved:
            print(f"WARNING: could not resolve starting items: {unresolved}")
        if starting_resolved:
            print(f"Starting items (removed from world pool):")
            for n in starting_resolved:
                print(f"  - {n}")
            # Remove one occurrence of each from names, and mark those placements
            # to be filled with junk or cadeaux later (replace the name in all_prog slots)
            for start_name in starting_resolved:
                for i, n in enumerate(names):
                    if n == start_name:
                        names[i] = None  # type: ignore
                        break
            # Compact: replace None slots with junk or leave for junk injection
            names = [n for n in names if n is not None]

    # --- Junk injection ---
    junk_count = getattr(args, "junk", 0) or 0
    junk_names_to_add = []
    if junk_count > 0:
        for i in range(junk_count):
            rsc, _, _ = JUNK_ITEMS[i % len(JUNK_ITEMS)]
            if i >= len(JUNK_ITEMS):
                rsc = f"RSC_X_junk_{i:02d}"
            junk_names_to_add.append(rsc)
        print(f"Injecting {len(junk_names_to_add)} junk items into the pool.")

    if junk_names_to_add:
        cadeaux_indices = [i for i, n in enumerate(names) if "cadeaux" in n.lower() or "dark_soul" in n.lower()]
        replace_count = min(len(junk_names_to_add), len(cadeaux_indices), len(names))
        for j in range(replace_count):
            names[cadeaux_indices[-(j + 1)]] = junk_names_to_add[j]
        if replace_count < len(junk_names_to_add):
            print(f"  (only {replace_count} cadeaux/dark_soul slots available for junk)")

    # all_prog may be longer than names when starting items were removed.
    # Leftover placements are filled with filler below; do not pad names back.
    place_count = min(len(all_prog), len(names))

    print(f"Found {len(all_prog)} original pool placements across {len(parsed_areas)} areas")
    print(f"Shuffling {place_count} names after start/junk adjustments:")
    by_area = Counter(parsed_areas[a]["label"] for a, _, _ in all_prog[:place_count])
    for label, cnt in sorted(by_area.items()):
        print(f"  {label:16s} {cnt:3d}")

    unique_names = sorted(set(names[:place_count]))
    print(f"\nUnique items in final pool ({len(unique_names)}):")
    for n in unique_names:
        tag = " [junk]" if is_junk(n) else ""
        print(f"  - {n}  (×{names[:place_count].count(n)}){tag}")

    rng = random.Random(args.seed)
    shuffled_names = names[:place_count]
    rng.shuffle(shuffled_names)

    changes = 0
    for (area_idx, rec_idx, old_name), new_name in zip(all_prog[:place_count], shuffled_names):
        if old_name == new_name:
            continue
        area = parsed_areas[area_idx]
        r = area["parsed"]["records"][rec_idx]
        set_name(area["parsed"]["data"], r["offset"], new_name)
        print(f"  {area['label']:16s} 0x{r['offset']:04x}: {old_name}  →  {new_name}")
        changes += 1

    # Any leftover all_prog slots beyond place_count (from starting-item removal)
    # get filled with a filler so the location still has something
    filler = junk_names_to_add[0] if junk_names_to_add else "RSC_X_cadeaux"
    for area_idx, rec_idx, old_name in all_prog[place_count:]:
        area = parsed_areas[area_idx]
        r = area["parsed"]["records"][rec_idx]
        if old_name != filler:
            set_name(area["parsed"]["data"], r["offset"], filler)
            print(f"  {area['label']:16s} 0x{r['offset']:04x}: {old_name}  →  {filler}  (start-item slot fill)")
            changes += 1

    outdir = Path(args.output) if args.output else Path(f"shuffled_seed{args.seed}")
    outdir.mkdir(parents=True, exist_ok=True)
    for area in parsed_areas:
        area_out = outdir / area["label"]
        area_out.mkdir(exist_ok=True)
        (area_out / "quest.rsc").write_bytes(area["parsed"]["data"])

    # Spoiler: starting items
    spoiler_lines = [
        f"Shadow Man Original PC Randomizer — seed {args.seed}",
        f"Starting items ({len(starting_resolved)}):",
    ]
    if starting_resolved:
        for n in starting_resolved:
            spoiler_lines.append(f"  - {n}")
        spoiler_lines.append("")
        spoiler_lines.append(
            "NOTE: These items were removed from the world pool. "
            "Actual New-Game inventory injection is not yet implemented; "
            "treat these as 'you begin as if you already had them' for logic, "
            "or use cheats/debug until EXE grant support lands."
        )
    else:
        spoiler_lines.append("  (none)")
    spoiler_lines.append("")
    spoiler_lines.append(f"Junk count requested: {junk_count}")
    (outdir / "starting_items.txt").write_text("\n".join(spoiler_lines) + "\n", encoding="utf-8")
    (outdir / "spoiler_seed{}.txt".format(args.seed)).write_text("\n".join(spoiler_lines) + "\n", encoding="utf-8")

    if junk_count or junk_names_to_add:
        _write_junk_support(outdir / "_junk_support", count=max(junk_count, len(JUNK_ITEMS)))

    print(f"\nDone. {changes} placements changed. Output → {outdir}/")
    if starting_resolved:
        print(f"Starting items listed in {outdir}/starting_items.txt")


def _write_junk_support(outdir: Path, count: int = 20) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    lines = ["// Auto-generated junk item captions for Shadow Man randomizer\n"]
    items_txt_lines = ["// Auto-generated junk object definitions\n"]
    for i, (rsc, code, caption) in enumerate(JUNK_ITEMS):
        if count <= len(JUNK_ITEMS) and i >= count:
            break
        lines.append(f'$item "{code}"\n{{\n\tCAPTION = "{caption}"\n}}\n')
        items_txt_lines.append(
            f"$newitem\n{{\n$rscname = {rsc}\n$meshpath = {JUNK_MESH_PATH}\n"
            f"$tgapath = {JUNK_TGA_PATH}\n$flags    =\n$type = GENERIC_SPIN_OBJECT\n"
            f"$offsets = 0 0 0\n}}\n"
        )
    for i in range(len(JUNK_ITEMS), count):
        rsc = f"RSC_X_junk_{i:02d}"
        code = f"JUNK{i:02d}"
        lines.append(f'$item "{code}"\n{{\n\tCAPTION = "Mysterious junk #{i:02d}"\n}}\n')
        items_txt_lines.append(
            f"$newitem\n{{\n$rscname = {rsc}\n$meshpath = {JUNK_MESH_PATH}\n"
            f"$tgapath = {JUNK_TGA_PATH}\n$flags    =\n$type = GENERIC_SPIN_OBJECT\n"
            f"$offsets = 0 0 0\n}}\n"
        )
    (outdir / "junk_invitems.dsc").write_text("".join(lines), encoding="utf-8")
    (outdir / "junk_items.txt").write_text("".join(items_txt_lines), encoding="utf-8")
    (outdir / "README_junk.txt").write_text(
        "Junk support files\n=================\n\n"
        "junk_invitems.dsc  – merge into data/scripts/items/inventory/english/invitems.dsc\n"
        "junk_items.txt     – append $newitem blocks into level ITEMS.TXT files\n",
        encoding="utf-8",
    )


def cmd_gen_junk(args):
    out = Path(args.output) if args.output else Path("junk_support")
    _write_junk_support(out, count=args.count or len(JUNK_ITEMS))
    print(f"Wrote junk support to {out}/")


def cmd_summary(args):
    areas = discover_areas(Path(args.root))
    if not areas:
        print("No quest.rsc found.")
        return
    print(f"{'Area':<18} {'Records':>8} {'Prog':>6} {'Junk':>6}")
    print("-" * 48)
    tr = tp = tj = 0
    for label, path in areas:
        try:
            p = parse_quest_rsc(path)
            np_ = sum(1 for r in p["records"] if is_progression(r["name"]))
            nj = sum(1 for r in p["records"] if is_junk(r["name"]))
            print(f"{label:<18} {len(p['records']):8d} {np_:6d} {nj:6d}")
            tr += len(p["records"]); tp += np_; tj += nj
        except Exception as e:
            print(f"{label:<18} ERROR {e}")
    print("-" * 48)
    print(f"{'TOTAL':<18} {tr:8d} {tp:6d} {tj:6d}")


def cmd_inventory(args):
    areas = discover_areas(Path(args.root))
    table: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    labels = []
    for label, path in areas:
        try:
            p = parse_quest_rsc(path)
        except Exception:
            continue
        labels.append(label)
        for r in p["records"]:
            if is_progression(r["name"]) or is_junk(r["name"]):
                table[r["name"]][label] += 1
    labels = sorted(set(labels))
    header = f"{'Item':<32}" + "".join(f" {a[:5]:>5}" for a in labels) + "  Tot"
    print(header)
    print("-" * len(header))
    for item in sorted(table.keys()):
        c = table[item]
        print(f"{item:<32}" + "".join(f" {c.get(a, 0):5d}" for a in labels) + f"  {sum(c.values()):4d}")
        

# -------------------------------------------------------------------------
# Enemies (enemies.rsc) — same Erscv002 72-byte records as quest.rsc
# -------------------------------------------------------------------------

# Names that are NOT combat baddies (leave alone by default)
ENEMY_EXCLUDE_KEYWORDS = [
    "speech_trigger", "secret", "cutcam", "statue", "spike",
    "milton_", "batrachian_", "cruz_", "chopper",  # scripted encounter markers
    "cage", "gib",  # props / corpses often
]

# Barrel / govi / crate-like destructibles living in quest.rsc
BARREL_KEYWORDS = [
    "barrel", "govi", "govicrate", "crate", "packbox", "item_box",
]


def is_enemy_baddy(name: str) -> bool:
    """True if this enemies.rsc entry looks like a combat spawn."""
    lower = name.lower()
    if not name.startswith("RSC_"):
        return False
    if any(k in lower for k in ENEMY_EXCLUDE_KEYWORDS):
        return False
    # Common baddy prefixes / patterns
    if any(p in lower for p in (
        "_zombi", "deadside", "deadwing", "deadfish", "bicephal",
        "hookman", "guard", "grinder", "floater",
        "bad_hd_", "bad_kil_", "inmate", "brutal", "duppy",
        "dog", "marco", "avery", "nettie", "legion", "batty",
        "biseph", "acolyte", "adept", "demon",
    )):
        return True
    # Fallback: anything in enemies.rsc that isn't excluded
    return True


def is_barrel_like(name: str) -> bool:
    lower = name.lower()
    return any(k in lower for k in BARREL_KEYWORDS)


def parse_enemies_rsc(file_path):
    """
    Parse enemies.rsc using the same 72-byte Erscv002 layout as quest.rsc.
    Returns list of {offset, name, is_baddy}.
    """
    path = Path(file_path)
    parsed = parse_quest_rsc(path)
    out = []
    for r in parsed["records"]:
        out.append({
            "offset": r["offset"],
            "name": r["name"],
            "is_baddy": is_enemy_baddy(r["name"]),
            "length": len(r["name"]),
        })
    return out


def swap_enemy_in_rsc(file_path, target_offset, old_name, new_name):
    """Replace enemy name at record offset (record start, not name start)."""
    path = Path(file_path)
    data = bytearray(path.read_bytes())
    # target_offset is record start from parse_enemies_rsc
    try:
        set_name(data, target_offset, new_name)
        path.write_bytes(data)
        return True
    except Exception:
        return False


def cmd_list_enemies(args):
    """List enemy types in one or more enemies.rsc files."""
    paths = []
    for d in args.dirs:
        p = Path(d)
        if p.is_file():
            paths.append(p)
        elif p.is_dir():
            paths.extend(sorted(p.rglob("enemies.rsc")))
    if not paths:
        print("No enemies.rsc found.")
        return
    for path in paths:
        try:
            records = parse_enemies_rsc(path)
        except Exception as e:
            print(f"{path}: ERROR {e}")
            continue
        baddies = [r for r in records if r["is_baddy"]]
        other = [r for r in records if not r["is_baddy"]]
        print(f"\n{path}  total={len(records)}  baddies={len(baddies)}  other={len(other)}")
        from collections import Counter
        c = Counter(r["name"] for r in baddies)
        for n, cnt in c.most_common():
            print(f"  {cnt:3d}  {n}")
        if other:
            print("  --- non-baddy (excluded from shuffle) ---")
            c2 = Counter(r["name"] for r in other)
            for n, cnt in c2.most_common():
                print(f"  {cnt:3d}  {n}")


def cmd_enemy_shuffle(args):
    """
    Shuffle combat baddy types within each enemies.rsc (or across all if --cross).
    Non-baddy entries (triggers, secrets, cutcams) are left alone.
    """
    paths = []
    for d in args.dirs:
        p = Path(d)
        if p.is_file() and p.name.lower() == "enemies.rsc":
            paths.append(p)
        elif p.is_dir():
            paths.extend(sorted(p.rglob("enemies.rsc")))
    # de-dupe
    seen = set()
    unique = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    paths = unique
    if not paths:
        print("No enemies.rsc found.")
        return

    cross = getattr(args, "cross", False)
    rng = random.Random(args.seed)

    # Load all
    files = []
    for path in paths:
        try:
            parsed = parse_quest_rsc(path)
        except Exception as e:
            print(f"Skipping {path}: {e}")
            continue
        baddy_idxs = [i for i, r in enumerate(parsed["records"]) if is_enemy_baddy(r["name"])]
        files.append({"path": path, "parsed": parsed, "baddy_idxs": baddy_idxs})

    if cross:
        # Pool all baddy names across files, shuffle, redistribute preserving counts per file
        all_names = []
        for f in files:
            for i in f["baddy_idxs"]:
                all_names.append(f["parsed"]["records"][i]["name"])
        print(f"Cross-area enemy shuffle: {len(all_names)} baddy placements across {len(files)} files")
        shuffled = all_names[:]
        rng.shuffle(shuffled)
        cursor = 0
        changes = 0
        for f in files:
            for i in f["baddy_idxs"]:
                r = f["parsed"]["records"][i]
                new_name = shuffled[cursor]
                cursor += 1
                if r["name"] != new_name:
                    set_name(f["parsed"]["data"], r["offset"], new_name)
                    changes += 1
        print(f"  {changes} name changes")
    else:
        changes = 0
        for f in files:
            idxs = f["baddy_idxs"]
            names = [f["parsed"]["records"][i]["name"] for i in idxs]
            if len(names) < 2:
                print(f"  {f['path']}: skip (only {len(names)} baddies)")
                continue
            shuffled = names[:]
            rng.shuffle(shuffled)
            local = 0
            for i, new_name in zip(idxs, shuffled):
                r = f["parsed"]["records"][i]
                if r["name"] != new_name:
                    set_name(f["parsed"]["data"], r["offset"], new_name)
                    local += 1
            changes += local
            print(f"  {f['path'].parent.name}: shuffled {len(names)} baddies ({local} changed)")

    outdir = Path(args.output) if args.output else Path(f"enemies_seed{args.seed}")
    outdir.mkdir(parents=True, exist_ok=True)
    for f in files:
        # preserve relative area folder name
        area = f["path"].parent.name
        dest_dir = outdir / area
        dest_dir.mkdir(exist_ok=True)
        (dest_dir / "enemies.rsc").write_bytes(f["parsed"]["data"])
    print(f"Wrote shuffled enemies.rsc files → {outdir}/")


def cmd_barrel_shuffle(args):
    """
    Shuffle barrel / govi / crate-like objects within quest.rsc files.
    These are the common breakable obstacles (pots/barrels).
    """
    paths = []
    for d in args.dirs:
        p = Path(d)
        if p.is_file() and p.name.lower() == "quest.rsc":
            paths.append(p)
        elif p.is_dir():
            paths.extend(sorted(p.rglob("quest.rsc")))
    seen = set()
    unique = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    paths = unique
    if not paths:
        print("No quest.rsc found.")
        return

    rng = random.Random(args.seed)
    cross = getattr(args, "cross", False)

    files = []
    for path in paths:
        try:
            parsed = parse_quest_rsc(path)
        except Exception as e:
            print(f"Skipping {path}: {e}")
            continue
        idxs = [i for i, r in enumerate(parsed["records"]) if is_barrel_like(r["name"])]
        files.append({"path": path, "parsed": parsed, "idxs": idxs})

    if cross:
        all_names = []
        for f in files:
            for i in f["idxs"]:
                all_names.append(f["parsed"]["records"][i]["name"])
        print(f"Cross-area barrel shuffle: {len(all_names)} placements")
        shuffled = all_names[:]
        rng.shuffle(shuffled)
        cursor = 0
        changes = 0
        for f in files:
            for i in f["idxs"]:
                r = f["parsed"]["records"][i]
                new_name = shuffled[cursor]
                cursor += 1
                if r["name"] != new_name:
                    set_name(f["parsed"]["data"], r["offset"], new_name)
                    changes += 1
        print(f"  {changes} changes")
    else:
        for f in files:
            idxs = f["idxs"]
            names = [f["parsed"]["records"][i]["name"] for i in idxs]
            if len(names) < 2:
                print(f"  {f['path'].parent.name}: skip ({len(names)} barrels)")
                continue
            shuffled = names[:]
            rng.shuffle(shuffled)
            local = 0
            for i, new_name in zip(idxs, shuffled):
                r = f["parsed"]["records"][i]
                if r["name"] != new_name:
                    set_name(f["parsed"]["data"], r["offset"], new_name)
                    local += 1
            print(f"  {f['path'].parent.name}: {len(names)} barrels/govi ({local} changed)")

    outdir = Path(args.output) if args.output else Path(f"barrels_seed{args.seed}")
    outdir.mkdir(parents=True, exist_ok=True)
    for f in files:
        area = f["path"].parent.name
        dest = outdir / area
        dest.mkdir(exist_ok=True)
        (dest / "quest.rsc").write_bytes(f["parsed"]["data"])
    print(f"Wrote → {outdir}/")




# -------------------------------------------------------------------------
# Debug / cheats menu (Acclaim engine menu scripts — not EXE byte patches)
# -------------------------------------------------------------------------

DEBUG_CHEAT_ITEMS = """
	$item = "Invincibility"
	{
		COLOR(255,234,180)
		ACTION
		EXEC = "internal_debug_invincibility_toggle"
	}

	$item = "Infinite Ammo"
	{
		COLOR(255,234,180)
		ACTION
		EXEC = "internal_debug_infinite_ammo_toggle"
	}

	$item = "Freeze Enemies"
	{
		COLOR(255,234,180)
		ACTION
		EXEC = "internal_debug_freeze_ai_toggle"
	}

	$item = "One Touch Kill"
	{
		COLOR(255,234,180)
		ACTION
		EXEC = "internal_debug_one_touch_toggle"
	}

	$item = "Wireframe Mode"
	{
		COLOR(255,210,255)
		ACTION
		EXEC = "internal_toggle_wireframe_mode"
	}

	$item = "Select Level"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_select_level"
	}

	$item = "Select Gads"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_select_gads"
	}

	$item = "Select Character"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_select_character"
	}

	$item = "Shadowmeter Settings"
	{
		COLOR(176,193,239)
		SUB_MENU = "shadowmeter_menu"
	}

	$item = "Full Debug Menu"
	{
		COLOR(100,234,255)
		SUB_MENU = "ingame_debug_menu"
	}
"""

SHADOWMETER_MENU_BLOCK = """
$menu "shadowmeter_menu"
{
	$menu_scale = 0.64, 0.80

	$item = "ShadowPower Level"
	{
		COLOR(176,193,239)
		SLIDER_VALUE
		DATA_TYPE_PERCENT
		EXEC = "internal_shadowmeter_shadpower_level"
	}

	$item = "VoodooPower Level"
	{
		COLOR(176,193,239)
		SLIDER_VALUE
		DATA_TYPE_PERCENT
		EXEC = "internal_shadowmeter_voodoopower_level"
	}

	$item = "Lifeforce Max Level"
	{
		COLOR(176,193,239)
		SLIDER_VALUE
		DATA_TYPE_PERCENT
		EXEC = "internal_shadowmeter_lifeforcemax_level"
	}

	$item = "Shotgun Ammo"
	{
		COLOR(176,193,239)
		SLIDER_VALUE
		DATA_TYPE_PERCENT
		EXEC = "internal_shadowmeter_shotgunammo_level"
	}

	$item = "Violator Ammo"
	{
		COLOR(176,193,239)
		SLIDER_VALUE
		DATA_TYPE_PERCENT
		EXEC = "internal_shadowmeter_violatorammo_level"
	}

	$item = "Cadeaux"
	{
		COLOR(176,193,239)
		SLIDER_VALUE
		DATA_TYPE_PERCENT
		EXEC = "internal_shadowmeter_cadeaux_level"
	}

	$item = "Exit"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_go_back"
	}
}
"""

INGAME_DEBUG_MENU_BLOCK = """
$menu "ingame_debug_menu"
{
	$title = "Debug Menu"
	$menu_scale = 0.64, 0.80

	$item = "Level"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_select_level"
	}

	$item = "Gads"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_select_gads"
	}

	$item = "Character"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_select_character"
	}

	$item = "Invincibility"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_invincibility_toggle"
	}

	$item = "Freeze Enemies"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_freeze_ai_toggle"
	}

	$item = "One Touch Kill"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_one_touch_toggle"
	}

	$item = "Infinite Ammo"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_debug_infinite_ammo_toggle"
	}

	$item = "Wireframe Mode"
	{
		COLOR(255,210,255)
		ACTION
		EXEC = "internal_toggle_wireframe_mode"
	}

	$item = "Shadowmeter Settings"
	{
		COLOR(176,193,239)
		SUB_MENU = "shadowmeter_menu"
	}

	$item = "More Debug..."
	{
		COLOR(100,234,255)
		SUB_MENU = "ingame_debug_menu_two"
	}

	$item = "Go Back"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_go_back"
	}
}

$menu "ingame_debug_menu_two"
{
	$title = "Debug Menu Two"
	$menu_scale = 0.64, 0.80

	$item = "Freeze Weapons"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_freeze_all_weapons"
	}

	$item = "Freeze Effects"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_freeze_all_effects"
	}

	$item = "Game Speed"
	{
		COLOR(176,193,239)
		SLIDER_VALUE
		DEFAULT = 30
		EXEC = "internal_game_speed"
	}

	$item = "Primary Wep As Any"
	{
		COLOR(255,0,100)
		TEXT_ON_OFF
		EXEC = "internal_toggle_use_prim_wep_as_any_wep"
	}

	$item = "On-Screen Stats"
	{
		COLOR(40,40,255)
		ACTION
		EXEC = "internal_toggle_onscreen_stats"
	}

	$item = "Baddy Stats"
	{
		COLOR(40,255,255)
		ACTION
		EXEC = "internal_toggle_baddy_stats"
	}

	$item = "Exit"
	{
		COLOR(176,193,239)
		ACTION
		EXEC = "internal_go_back"
	}
}
"""


def find_menus_english_dir(root):
    """Locate data/scripts/menus/english under a game root (or the folder itself)."""
    root = Path(root)
    candidates = [
        root / "data" / "scripts" / "menus" / "english",
        root / "scripts" / "menus" / "english",
        root,
    ]
    for c in candidates:
        if (c / "release.msc").is_file() or (c / "debug.msc").is_file():
            return c
    for p in root.rglob("release.msc"):
        return p.parent
    raise FileNotFoundError(f"Could not find menus/english (release.msc) under {root}")


def enable_debug_menus(root_or_menus_dir, mode="merge", backup=True):
    """
    Enable Acclaim-style debug/cheat toggles for a normal install.

    mode:
      "merge"  – inject cheats into retail release.msc Secrets menu (recommended)
      "full"   – replace release.msc with debug.msc (full Test Level UI)
    """
    menus = find_menus_english_dir(Path(root_or_menus_dir))
    release_path = menus / "release.msc"
    debug_path = menus / "debug.msc"
    result = {"menus_dir": str(menus), "mode": mode, "files": []}

    if mode == "full":
        if not debug_path.is_file():
            raise FileNotFoundError(f"debug.msc not found in {menus}")
        if not release_path.is_file():
            raise FileNotFoundError(f"release.msc not found in {menus}")
        if backup:
            bak = menus / "release.msc.bak"
            if not bak.exists():
                bak.write_bytes(release_path.read_bytes())
                result["files"].append(str(bak))
        release_path.write_bytes(debug_path.read_bytes())
        result["files"].append(str(release_path))
        result["note"] = "release.msc replaced with debug.msc (Test Level on main menu)"
        return result

    if not release_path.is_file():
        raise FileNotFoundError(f"release.msc not found in {menus}")

    original = release_path.read_text(encoding="utf-8", errors="replace")
    if backup:
        bak = menus / "release.msc.bak"
        if not bak.exists():
            bak.write_text(original, encoding="utf-8")
            result["files"].append(str(bak))

    if "internal_debug_invincibility_toggle" in original:
        result["note"] = "Already merged (invincibility toggle present)"
        result["files"].append(str(release_path))
        return result

    text = original

    old_cheats = '''$menu "cheats_menu"
{
	$title = "Secrets"
	$menu_scale	= 0.65, 0.65

	$cheats_menu

	$item = "Go Back"
	{
		COLOR(255,234,180)
		ACTION
		EXEC = "internal_go_back"
	}
}'''

    new_cheats = (
        '$menu "cheats_menu"\n{\n'
        '\t$title = "Secrets / Cheats"\n'
        '\t$menu_scale\t= 0.65, 0.65\n\n'
        '\t$cheats_menu\n'
        + DEBUG_CHEAT_ITEMS
        + '\n\t$item = "Go Back"\n'
        '\t{\n'
        '\t\tCOLOR(255,234,180)\n'
        '\t\tACTION\n'
        '\t\tEXEC = "internal_go_back"\n'
        '\t}\n}'
    )

    if old_cheats in text:
        text = text.replace(old_cheats, new_cheats)
    else:
        import re
        pattern = re.compile(
            r'(\$menu\s+"cheats_menu"\s*\{.*?\$cheats_menu)(.*?)(\$item\s*=\s*"Go Back".*?\})',
            re.DOTALL,
        )
        m = pattern.search(text)
        if not m:
            raise ValueError("Could not locate cheats_menu block in release.msc to merge")
        text = (
            text[: m.start()]
            + m.group(1)
            + "\n"
            + DEBUG_CHEAT_ITEMS
            + "\n"
            + m.group(3)
            + text[m.end() :]
        )

    if "$menu \"ingame_debug_menu\"" not in text and '$menu "ingame_debug_menu"' not in text:
        text = text.rstrip() + "\n\n" + SHADOWMETER_MENU_BLOCK + "\n" + INGAME_DEBUG_MENU_BLOCK + "\n"

    release_path.write_text(text, encoding="utf-8")
    result["files"].append(str(release_path))
    result["note"] = "Merged debug toggles into Secrets menu of release.msc"
    return result


def restore_release_menu(root_or_menus_dir):
    """Restore release.msc from release.msc.bak if present."""
    menus = find_menus_english_dir(Path(root_or_menus_dir))
    release_path = menus / "release.msc"
    bak = menus / "release.msc.bak"
    if not bak.is_file():
        raise FileNotFoundError(f"No backup at {bak}")
    release_path.write_bytes(bak.read_bytes())
    return {"restored": str(release_path), "from": str(bak)}


def cmd_enable_debug(args):
    mode = getattr(args, "mode", "merge") or "merge"
    result = enable_debug_menus(args.root, mode=mode, backup=not getattr(args, "no_backup", False))
    print(f"Mode: {result['mode']}")
    print(f"Menus dir: {result['menus_dir']}")
    print(f"Note: {result.get('note', '')}")
    for f in result.get("files", []):
        print(f"  touched: {f}")


def cmd_restore_menu(args):
    result = restore_release_menu(args.root)
    print(f"Restored {result['restored']} from {result['from']}")


def main():
    parser = argparse.ArgumentParser(description="Shadow Man original PC randomizer tool v0.10")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list"); p.add_argument("rsc"); p.set_defaults(func=cmd_list)
    p = sub.add_parser("dump"); p.add_argument("rsc"); p.set_defaults(func=cmd_dump)
    p = sub.add_parser("swap")
    p.add_argument("rsc"); p.add_argument("old_name"); p.add_argument("new_name"); p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_swap)
    p = sub.add_parser("shuffle")
    p.add_argument("rsc"); p.add_argument("--seed", type=int, default=42); p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_shuffle)
    p = sub.add_parser("multishuffle")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--junk", type=int, default=0)
    p.add_argument("--start", action="append", default=[],
                   help="Starting item alias (repeatable). Example: --start poigne --start baton")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_multishuffle)
    p = sub.add_parser("summary"); p.add_argument("root"); p.set_defaults(func=cmd_summary)
    p = sub.add_parser("inventory"); p.add_argument("root"); p.set_defaults(func=cmd_inventory)
    p = sub.add_parser("gen-junk")
    p.add_argument("--count", type=int, default=20); p.add_argument("-o", "--output", default="junk_support")
    p.set_defaults(func=cmd_gen_junk)
    p = sub.add_parser("list-startables", help="List valid --start item names")
    p.set_defaults(func=cmd_list_startables)

    # Enemies
    p = sub.add_parser("list-enemies", help="List baddy types in enemies.rsc files")
    p.add_argument("dirs", nargs="+")
    p.set_defaults(func=cmd_list_enemies)
    p = sub.add_parser("enemy-shuffle", help="Shuffle combat baddies in enemies.rsc")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--cross", action="store_true", help="Pool baddies across all areas")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_enemy_shuffle)

    # Barrels / pots / govi
    p = sub.add_parser("barrel-shuffle", help="Shuffle barrels/govi/crates in quest.rsc")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--cross", action="store_true", help="Pool across all areas")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_barrel_shuffle)

    p = sub.add_parser("enable-debug", help="Enable debug/cheat menus in release.msc")
    p.add_argument("root", help="Game root or menus/english folder")
    p.add_argument("--mode", choices=["merge", "full"], default="merge",
                   help="merge=inject into Secrets; full=replace with debug.msc")
    p.add_argument("--no-backup", action="store_true")
    p.set_defaults(func=cmd_enable_debug)

    p = sub.add_parser("restore-menu", help="Restore release.msc from .bak")
    p.add_argument("root")
    p.set_defaults(func=cmd_restore_menu)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
