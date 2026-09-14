#!/usr/bin/env python3
"""
Turok Evolution PC (Turok 4) — ATI actor path randomizer
Part of komodo_core_randomizer / Akklaim Randomizers

Level packs use uncompressed ATI actor-instance files with length-prefixed
Windows paths (e.g. Y:\\Data\\Actors\\Enemies\\...). No RNC.

Usage:
  python te_tool.py list-actors [level_dir|root]
  python te_tool.py list-levels [root]
  python te_tool.py shuffle-enemies <root> [--seed N] [-o outdir]
  python te_tool.py shuffle-pickups <root> [--seed N] [-o outdir]
  python te_tool.py shuffle-all <root> [--seed N] [-o outdir]
"""

from __future__ import annotations

import argparse
import random
import re
import shutil
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PATH_RE = re.compile(rb"([A-Za-z]:\\Data\\Actors\\[^\x00]+)\x00")

# Categories we randomize
ENEMY_CATS = {"Enemies", "EnemyVariations"}
PICKUP_CATS = {"Pickups"}

# Never touch these even if they match a category string
DENY_SUBSTR = (
    "Cinematic",
    "NULLACTOR",
    "EnemyGenerator",  # generators stay; swap what they reference later
)

# Progression / door keys — shuffling these softlocks or freezes (bone door, etc.)
PICKUP_DENY_SUBSTR = (
    "Tarkeen_Key",
    "TarkeenKey",
    "\\Key\\",
    "/Key/",
    "KeyPickup",
    "\\Misc\\",   # progression misc pickups
    "/Misc/",
    "SwivelSwitch_key",
)

# Crash-isolation pools for enemy shuffle
VEHICLE_MARKERS = (
    "Vehicles\\", "Glider", "VTOL", "Tank", "Mine", "Airship", "Zepplin",
    "Zeppelin", "WAPC", "SeaPlane", "Barracuda", "B-17", "GNAT", "Turret",
)
LARGE_DINO_MARKERS = (
    "Dinosaurs\\", "Parasaur", "Stegosaur", "Brachiosaurus", "T-rex", "T-Rex",
    "Triceratops", "Ankylo", "AxeBeak",
)


def enemy_pool_of(path: str) -> str:
    """ground | vehicle | large_dino"""
    if any(m in path for m in VEHICLE_MARKERS):
        return "vehicle"
    if any(m in path for m in LARGE_DINO_MARKERS):
        return "large_dino"
    return "ground"


def category_of(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    try:
        i = parts.index("Actors")
        return parts[i + 1] if i + 1 < len(parts) else "?"
    except ValueError:
        return "?"


def short_path(path: str) -> str:
    if "Actors\\" in path:
        return path.split("Actors\\", 1)[1].replace("\\", "/")
    return path




class PathSlot:
    __slots__ = ("file", "len_off", "path", "category")

    def __init__(self, file: Path, len_off: int, path: str, category: str):
        self.file = file
        self.len_off = len_off
        self.path = path
        self.category = category

    @property
    def path_len(self) -> int:
        return len(self.path)


def find_ati_files(root: Path) -> List[Path]:
    return sorted(root.rglob("*.ati"))


def parse_ati_slots(ati_path: Path) -> List[PathSlot]:
    data = ati_path.read_bytes()
    slots: List[PathSlot] = []
    for m in PATH_RE.finditer(data):
        path_bytes = m.group(1)
        path = path_bytes.decode("ascii", errors="ignore")
        len_off = m.start() - 1
        if len_off < 0:
            continue
        if data[len_off] != len(path_bytes):
            # length byte mismatch — skip
            continue
        cat = category_of(path)
        slots.append(PathSlot(ati_path, len_off, path, cat))
    return slots


def collect_slots(root: Path, cats: set, enemy_pool: str | None = None) -> List[PathSlot]:
    """enemy_pool: None=all enemies, or ground|vehicle|large_dino|safe (ground only)."""
    slots: List[PathSlot] = []
    for ati in find_ati_files(root):
        for s in parse_ati_slots(ati):
            if s.category not in cats:
                continue
            if any(d.lower() in s.path.lower() for d in DENY_SUBSTR):
                continue
            if s.category in PICKUP_CATS and any(
                d.lower() in s.path.lower() for d in PICKUP_DENY_SUBSTR
            ):
                continue
            if enemy_pool and s.category in ENEMY_CATS:
                pool = enemy_pool_of(s.path)
                if enemy_pool == "safe" and pool != "ground":
                    continue
                if enemy_pool in ("ground", "vehicle", "large_dino") and pool != enemy_pool:
                    continue
            slots.append(s)
    return slots


def apply_path_replacements(
    file_slots: Dict[Path, List[Tuple[PathSlot, str]]],
    out_root: Path,
    src_root: Path,
) -> int:
    """
    file_slots: ati_path -> list of (slot, new_path)
    Writes modified ATIs under out_root mirroring relative layout.
    Returns number of replacements written.
    """
    written = 0
    for src_ati, pairs in file_slots.items():
        data = bytearray(src_ati.read_bytes())
        # Apply from highest offset to lowest so earlier offsets stay valid
        pairs_sorted = sorted(pairs, key=lambda x: x[0].len_off, reverse=True)
        for slot, new_path in pairs_sorted:
            old_len = slot.path_len
            new_bytes = new_path.encode("ascii")
            new_len = len(new_bytes)
            if new_len > 255:
                raise ValueError(f"Path too long ({new_len}): {new_path}")
            off = slot.len_off
            # Verify still matches what we parsed
            if data[off] != old_len:
                # File already mutated unexpectedly
                continue
            # splice: len_byte + path  (trailing 0x00 stays at old end position → move with tail)
            # old layout: [len][path...][0x00][rest]
            # new layout: [len'][path'...][0x00][rest]
            rest_start = off + 1 + old_len  # points at 0x00
            data[off : rest_start] = bytes([new_len]) + new_bytes
            written += 1

        rel = src_ati.relative_to(src_root)
        dest = out_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return written


def _ensure_out_outside_src(src_root: Path, out_root: Path) -> None:
    """Refuse output directories inside the source tree (prevents infinite nesting)."""
    src = src_root.resolve()
    out = out_root.resolve()
    try:
        out.relative_to(src)
    except ValueError:
        return  # out is not under src — OK
    raise SystemExit(
        f"Output path must NOT be inside the source tree.\n"
        f"  source: {src}\n"
        f"  output: {out}\n"
        f"Use a sibling folder, e.g. {src.parent / (src.name + '_shuffled')}"
    )


def copy_sidecar_files(src_root: Path, out_root: Path) -> None:
    """Copy .atr / .mtf / other files so outdir is a playable level tree.

    Snapshots the file list first and skips anything under out_root so a
    nested -o path cannot recurse forever.
    """
    src_root = src_root.resolve()
    out_root = out_root.resolve()
    _ensure_out_outside_src(src_root, out_root)

    # Snapshot paths BEFORE any copies (do not iterate a live tree we are writing)
    files = [p for p in src_root.rglob("*") if p.is_file()]
    for p in files:
        # Skip ATIs (written by apply_path_replacements) and anything already under out
        try:
            p.resolve().relative_to(out_root)
            continue
        except ValueError:
            pass
        if p.suffix.lower() == ".ati":
            continue
        rel = p.relative_to(src_root)
        dest = out_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(p, dest)


def shuffle_category(
    root: Path,
    cats: set,
    seed: Optional[int],
    out: Optional[Path],
    label: str,
    enemy_pool: Optional[str] = None,
) -> None:
    root = root.resolve()
    slots = collect_slots(root, cats, enemy_pool=enemy_pool if cats & ENEMY_CATS else None)
    if len(slots) < 2:
        print(f"Not enough {label} slots to shuffle ({len(slots)}).")
        return

    rng = random.Random(seed)
    old_paths = [s.path for s in slots]
    new_paths = old_paths[:]
    rng.shuffle(new_paths)

    # Group replacements by file
    by_file: Dict[Path, List[Tuple[PathSlot, str]]] = defaultdict(list)
    changed = 0
    for slot, np in zip(slots, new_paths):
        if np != slot.path:
            changed += 1
        by_file[slot.file].append((slot, np))

    if out is None:
        tag = f"{label}_seed{seed}" if seed is not None else label
        out = root.parent / f"{root.name}_{tag}"
    out = out.resolve()
    _ensure_out_outside_src(root, out)
    out.mkdir(parents=True, exist_ok=True)

    n = apply_path_replacements(by_file, out, root)
    copy_sidecar_files(root, out)

    # Summary
    type_counts = Counter(short_path(p) for p in new_paths)
    print(f"Shuffled {len(slots)} {label} placements ({changed} changed), seed={seed}")
    print(f"  unique types in pool: {len(type_counts)}")
    print(f"  wrote {n} path rewrites across {len(by_file)} ATI files")
    print(f"  output: {out}")


def cmd_list_levels(root: Path) -> None:
    root = root.resolve()
    atis = find_ati_files(root)
    print(f"Levels under {root} ({len(atis)} ATI files):")
    for ati in atis:
        slots = parse_ati_slots(ati)
        cats = Counter(s.category for s in slots)
        enemies = sum(v for k, v in cats.items() if k in ENEMY_CATS)
        pickups = sum(v for k, v in cats.items() if k in PICKUP_CATS)
        rel = ati.parent.relative_to(root) if ati.parent != root else ati.name
        print(f"  {rel}: actors={len(slots)} enemies={enemies} pickups={pickups}")


def cmd_list_actors(root: Path) -> None:
    root = root.resolve()
    slots = []
    for ati in find_ati_files(root):
        slots.extend(parse_ati_slots(ati))
    by_cat: Dict[str, Counter] = defaultdict(Counter)
    for s in slots:
        by_cat[s.category][short_path(s.path)] += 1

    print(f"Actor paths in {root}: {len(slots)} placements, {sum(len(c) for c in by_cat.values())} unique")
    for cat in sorted(by_cat.keys()):
        print(f"\n[{cat}] {sum(by_cat[cat].values())} placements, {len(by_cat[cat])} types")
        for name, n in by_cat[cat].most_common(12):
            print(f"  {n:4d}  {name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Turok Evolution PC ATI actor randomizer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list-levels")
    p.add_argument("root", type=Path, nargs="?", default=Path("."))
    p = sub.add_parser("list-actors")
    p.add_argument("root", type=Path, nargs="?", default=Path("."))

    for name in ("shuffle-enemies", "shuffle-pickups", "shuffle-all"):
        p = sub.add_parser(name)
        p.add_argument("root", type=Path)
        p.add_argument("--seed", type=int, default=None)
        p.add_argument("-o", "--output", type=Path, default=None)
        p.add_argument(
            "--pool",
            choices=("all", "safe", "ground", "vehicle", "large_dino"),
            default="safe",
            help="Enemy pool: safe=ground only (default, fewer freezes)",
        )

    args = ap.parse_args()
    if args.cmd == "list-levels":
        cmd_list_levels(args.root)
    elif args.cmd == "list-actors":
        cmd_list_actors(args.root)
    elif args.cmd == "shuffle-enemies":
        pool = None if args.pool == "all" else args.pool
        shuffle_category(args.root, ENEMY_CATS, args.seed, args.output, "enemies", enemy_pool=pool)
    elif args.cmd == "shuffle-pickups":
        shuffle_category(args.root, PICKUP_CATS, args.seed, args.output, "pickups")
    elif args.cmd == "shuffle-all":
        # enemies then pickups into same outdir
        root = args.root.resolve()
        seed = args.seed
        out = args.output
        if out is None:
            tag = f"all_seed{seed}" if seed is not None else "all"
            out = root.parent / f"{root.name}_{tag}"
        # First pass enemies
        pool = None if getattr(args, "pool", "safe") == "all" else getattr(args, "pool", "safe")
        slots_e = collect_slots(root, ENEMY_CATS, enemy_pool=pool)
        slots_p = collect_slots(root, PICKUP_CATS)
        if len(slots_e) < 2 and len(slots_p) < 2:
            print("Nothing to shuffle.")
            return
        rng = random.Random(seed)
        by_file: Dict[Path, List[Tuple[PathSlot, str]]] = defaultdict(list)

        def assign(slots):
            paths = [s.path for s in slots]
            shuffled = paths[:]
            rng.shuffle(shuffled)
            for s, np in zip(slots, shuffled):
                by_file[s.file].append((s, np))

        if len(slots_e) >= 2:
            assign(slots_e)
        if len(slots_p) >= 2:
            assign(slots_p)

        out = out.resolve()
        _ensure_out_outside_src(root, out)
        out.mkdir(parents=True, exist_ok=True)
        n = apply_path_replacements(by_file, out, root)
        copy_sidecar_files(root, out)
        print(f"shuffle-all seed={seed}: enemies={len(slots_e)} pickups={len(slots_p)}")
        print(f"  path rewrites={n}  output={out}")


if __name__ == "__main__":
    main()
