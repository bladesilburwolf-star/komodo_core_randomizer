#!/usr/bin/env python3
"""
Turok 1: Dinosaur Hunter (PC) — Cartdata.dat randomizer

  python t1_tool.py info Cartdata.dat
  python t1_tool.py list-spawns Cartdata.dat
  python t1_tool.py list-sec4 Cartdata.dat
  python t1_tool.py shuffle-spawns Cartdata.dat [--preset all|boss|no_boss] [--seed N]
  python t1_tool.py shuffle-sec4 Cartdata.dat [--mode values|swap] [--seed N]
  python t1_tool.py shuffle-section Cartdata.dat --section N [--seed N]
  python t1_tool.py shuffle Cartdata.dat [--spawns] [--sec4] [--sections 1,5,9] [--preset all] [--seed N]
"""
from __future__ import annotations

import argparse
import math
import random
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

_HERE = Path(__file__).resolve().parent
_RNC_ROOTS = [
    _HERE,
    _HERE / "turok2",
    Path.cwd(),
    Path.cwd() / "turok2",
    _HERE.parent / "Turok_2_PC",
    _HERE.parent.parent / "turok2",
    Path("/home/workdir/artifacts/Akklaim_Randomizers/turok2"),
]


def _rnc_complete(root: Path) -> bool:
    return (root / "rnc" / "pack.py").is_file() and (root / "rnc" / "unpack.py").is_file()


_ordered = [p for p in _RNC_ROOTS if _rnc_complete(p)]
_ordered += [p for p in _RNC_ROOTS if (p / "rnc").is_dir() and p not in _ordered]

rnc_unpack = None  # type: ignore
rnc_pack = None  # type: ignore
_RNC_ERR: object = "rnc package not found"
for _p in _ordered:
    if str(_p) in sys.path:
        sys.path.remove(str(_p))
    sys.path.insert(0, str(_p))
    try:
        for mod in list(sys.modules):
            if mod == "rnc" or mod.startswith("rnc."):
                del sys.modules[mod]
        from rnc.unpack import unpack as _u
        from rnc.pack import pack as _p_fn
        rnc_unpack = _u
        rnc_pack = _p_fn
        _RNC_ERR = None
        break
    except ImportError as e:
        _RNC_ERR = e
        continue

WARPS_SECTION = 8
SEC4 = 4
RECORD_SIZE = 20
SEC4_RECORD = 104
SEC4_FIELD76 = 76
SEC4_FIELD84 = 84
SEC4_FIELD20 = 20  # float scale candidate (~1.0 default)

# Observed amount-like values for sec4 +76 hi
SCALE_POOL = [0.35, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]

AMOUNT_POOL = [
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    17, 18, 20, 22, 25, 28, 30, 33, 50, 56, 100,
]

# Boss / arena spawn IDs (expand after more in-game dumps)
# Includes classic specials (666-style) and late-level arena clusters the spawn
# pool already reaches in full gameplay shuffle.
BOSS_SPAWN_IDS: Set[int] = {
    666, 2666, 4666, 7777,
    1999, 2000, 2041, 2044, 2045, 2046,
    2151, 2152, 2153, 2251, 2252,
    2300, 2301, 2302,
    2766, 2767, 2768, 2769, 2997,
    7999, 8000,
}


def read_u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def write_u32(buf: bytearray, off: int, val: int) -> None:
    struct.pack_into("<I", buf, off, val)


def parse_header(data: bytes) -> Tuple[int, int, List[int]]:
    count = read_u32(data, 0)
    header_size = read_u32(data, 4)
    if count < 1 or count > 64:
        raise ValueError(f"Bad section count {count}")
    ends = [read_u32(data, 8 + i * 4) for i in range(count)]
    return count, header_size, ends


def section_ranges(header_size: int, ends: List[int]) -> List[Tuple[int, int]]:
    ranges = []
    prev = header_size
    for end in ends:
        ranges.append((prev, end))
        prev = end
    return ranges


def get_section(data: bytes, index: int) -> Tuple[bytes, int, int]:
    count, header_size, ends = parse_header(data)
    if index < 0 or index >= count:
        raise IndexError(f"Section {index} out of range 0..{count - 1}")
    ranges = section_ranges(header_size, ends)
    start, end = ranges[index]
    return data[start:end], start, end


def replace_section(data: bytes, index: int, new_sec: bytes) -> bytes:
    count, header_size, ends = parse_header(data)
    ranges = section_ranges(header_size, ends)
    start, end = ranges[index]
    delta = len(new_sec) - (end - start)
    out = bytearray(data[:start] + new_sec + data[end:])
    for i in range(index, count):
        write_u32(out, 8 + i * 4, ends[i] + delta)
    return bytes(out)


def patch_section_inplace(data: bytearray, index: int, new_sec: bytes) -> None:
    _, start, end = get_section(bytes(data), index)
    if len(new_sec) != end - start:
        raise ValueError(f"Section size mismatch: {end - start} vs {len(new_sec)}")
    data[start:end] = new_sec


def _need_rnc() -> None:
    if rnc_unpack is None or rnc_pack is None:
        raise RuntimeError(
            f"RNC pack/unpack not available ({_RNC_ERR}).\n"
            "Your rnc\\ folder is incomplete (missing pack.py).\n"
            "Copy the full rnc\\ folder next to t1_tool.py "
            "(must include pack.py, unpack.py, bitwriter.py, lz.py)."
        )


# ----- Section 8 spawns -----

def _is_menu_spawn(rec: bytes, id_value: Optional[int]) -> bool:
    x, y, z, _w = struct.unpack_from("<ffff", rec, 0)
    if max(abs(x), abs(y), abs(z)) < 50.0:
        return True
    if id_value is not None:
        if id_value >= 30000:
            return True
        if 9000 <= id_value <= 9999:
            return True
    return False


def _is_boss_id(id_value: Optional[int]) -> bool:
    if id_value is None:
        return False
    if id_value in BOSS_SPAWN_IDS:
        return True
    # Heuristic extras: *666 pattern, high 2xxx arena cluster
    if id_value % 1000 == 666:
        return True
    return False


def parse_spawn_table(sec: bytes) -> Tuple[List[Optional[int]], List[Tuple[int, bytes]]]:
    """Return (id_list aligned to pos records, list of (offset, 20-byte rec))."""
    if len(sec) < 16:
        return [], []
    block_count = read_u32(sec, 0)
    if block_count < 2:
        return [], []
    offsets = [read_u32(sec, 4 + i * 4) for i in range(block_count + 1)]
    id_values: List[Optional[int]] = []
    pos_recs: List[Tuple[int, bytes]] = []
    for bi in range(block_count):
        a, b = offsets[bi], offsets[bi + 1]
        if a + 8 > len(sec) or b > len(sec):
            continue
        rsz, rcnt = struct.unpack_from("<II", sec, a)
        if rsz == 4 and 1 <= rcnt <= 2000:
            base = a + 8
            id_values = [struct.unpack_from("<I", sec, base + n * 4)[0] for n in range(rcnt)]
        elif rsz == RECORD_SIZE and 1 <= rcnt <= 2000:
            base = a + 8
            for n in range(rcnt):
                off = base + n * rsz
                if off + rsz > b:
                    break
                pos_recs.append((off, sec[off:off + rsz]))
    return id_values, pos_recs


def filter_spawn_indices(
    id_values: List[Optional[int]],
    pos_recs: List[Tuple[int, bytes]],
    preset: str,
) -> List[int]:
    """Indices into pos_recs that participate in the shuffle."""
    out = []
    for i, (off, rec) in enumerate(pos_recs):
        iv = id_values[i] if i < len(id_values) else None
        if _is_menu_spawn(rec, iv):
            continue
        boss = _is_boss_id(iv)
        if preset == "boss" and not boss:
            continue
        if preset == "no_boss" and boss:
            continue
        # preset all (default): all non-menu
        out.append(i)
    return out


def shuffle_positions(sec: bytearray, seed: Optional[int] = None, preset: str = "all") -> int:
    id_values, pos_recs = parse_spawn_table(bytes(sec))
    idxs = filter_spawn_indices(id_values, pos_recs, preset)
    if len(idxs) < 2:
        return 0
    rng = random.Random(seed)
    blocks = [pos_recs[i][1] for i in idxs]
    rng.shuffle(blocks)
    for i, nb in zip(idxs, blocks):
        off = pos_recs[i][0]
        sec[off:off + len(nb)] = nb
    return len(idxs)


# ----- Section 4 -----

def unpack_sec4(packed: bytes) -> bytes:
    _need_rnc()
    return rnc_unpack(packed, verify_crc=False)


def pack_sec4(unpacked: bytes) -> bytes:
    _need_rnc()
    return rnc_pack(unpacked, method=1)


def parse_sec4_records(unpacked: bytes) -> Tuple[List[int], int, List[bytearray]]:
    bc = read_u32(unpacked, 0)
    offs = [read_u32(unpacked, 4 + i * 4) for i in range(bc + 1)]
    a0 = offs[0]
    rsz0, rcnt0 = struct.unpack_from("<II", unpacked, a0)
    ids = [struct.unpack_from("<I", unpacked, a0 + 8 + i * 4)[0] for i in range(rcnt0)]
    a1 = offs[1]
    rsz1, rcnt1 = struct.unpack_from("<II", unpacked, a1)
    if rsz1 != SEC4_RECORD:
        raise ValueError(f"sec4 block1 rsz={rsz1}")
    base = a1 + 8
    recs = [bytearray(unpacked[base + i * rsz1:base + (i + 1) * rsz1]) for i in range(rcnt1)]
    return ids, base, recs


def apply_sec4_records(unpacked: bytes, base: int, recs: List[bytearray]) -> bytes:
    out = bytearray(unpacked)
    for i, rec in enumerate(recs):
        out[base + i * SEC4_RECORD:base + (i + 1) * SEC4_RECORD] = rec
    return bytes(out)


def shuffle_sec4_fields(unpacked: bytes, seed: Optional[int] = None, mode: str = "values") -> Tuple[bytes, int]:
    """values | swap | scale | scale_values — see SCALE_POOL / AMOUNT_POOL."""
    ids, base, recs = parse_sec4_records(unpacked)
    rng = random.Random(seed)
    n = len(recs)
    do_scale = mode in ("scale", "scale_values")
    do_vals = mode in ("values", "scale_values")
    if mode == "swap":
        vals76 = [struct.unpack_from("<I", rec, SEC4_FIELD76)[0] for rec in recs]
        vals84 = [struct.unpack_from("<I", rec, SEC4_FIELD84)[0] for rec in recs]
        order = list(range(n))
        rng.shuffle(order)
        for i, j in enumerate(order):
            struct.pack_into("<I", recs[i], SEC4_FIELD76, vals76[j])
            struct.pack_into("<I", recs[i], SEC4_FIELD84, vals84[j])
    else:
        lo84_pool = [10, 15, 20, 30, 50, 60]
        for rec in recs:
            if do_vals:
                old76 = struct.unpack_from("<I", rec, SEC4_FIELD76)[0]
                lo76 = old76 & 0xFFFF
                new_hi = rng.choice(AMOUNT_POOL)
                struct.pack_into("<I", rec, SEC4_FIELD76, ((new_hi & 0xFFFF) << 16) | lo76)
                old84 = struct.unpack_from("<I", rec, SEC4_FIELD84)[0]
                hi84 = (old84 >> 16) & 0xFFFF
                new_lo84 = rng.choice(lo84_pool)
                struct.pack_into("<I", rec, SEC4_FIELD84, ((hi84 & 0xFFFF) << 16) | new_lo84)
            if do_scale:
                cur = struct.unpack_from("<f", rec, SEC4_FIELD20)[0]
                if math.isfinite(cur) and 0.05 <= abs(cur) <= 20.0:
                    struct.pack_into("<f", rec, SEC4_FIELD20, float(rng.choice(SCALE_POOL)))
    return apply_sec4_records(unpacked, base, recs), n


# ----- Experimental section shuffle (trial & error) -----

def _looks_rnc(blob: bytes) -> bool:
    return len(blob) >= 18 and blob[:3] == b"RNC" and blob[3] in (1, 2)


def experimental_shuffle_blob(blob: bytes, seed: Optional[int]) -> bytes:
    """
    Conservative experimental pass for unknown sections:
      - If whole blob is one RNC: unpack, permute amount-like u16 hi-words at 4-byte
        aligned offsets (same idea as sec4 +76), repack method 1.
      - Else if small uncompressed: permute 4-byte words that look like small ints.
      - Multi-RNC / huge: only shuffle the *first* RNC block in place if it shrinks/fits.
    """
    _need_rnc()
    rng = random.Random(seed)

    def scramble_unpacked(unp: bytearray) -> int:
        # Collect (offset, hi) for amount-like high words
        hits = []
        for off in range(0, len(unp) - 3, 4):
            v = struct.unpack_from("<I", unp, off)[0]
            hi = v >> 16
            lo = v & 0xFFFF
            if hi in AMOUNT_POOL or (1 <= hi <= 120 and lo == 0):
                hits.append(off)
        if len(hits) < 4:
            # fallback: permute small non-zero u16 pairs
            hits = []
            for off in range(0, len(unp) - 3, 4):
                v = struct.unpack_from("<I", unp, off)[0]
                if 1 <= v <= 500:
                    hits.append(off)
        if len(hits) < 2:
            return 0
        vals = [struct.unpack_from("<I", unp, off)[0] for off in hits]
        rng.shuffle(vals)
        for off, v in zip(hits, vals):
            struct.pack_into("<I", unp, off, v)
        return len(hits)

    if _looks_rnc(blob) and blob.count(b"RNC") == 1:
        unp = bytearray(rnc_unpack(blob, verify_crc=False))
        n = scramble_unpacked(unp)
        packed = rnc_pack(bytes(unp), method=1)
        return packed

    # Multi-RNC: leave structure, only note we skip heavy mess
    if blob.count(b"RNC") > 3:
        # Too complex for blind shuffle — return unchanged
        return blob

    if not _looks_rnc(blob):
        unp = bytearray(blob)
        scramble_unpacked(unp)
        return bytes(unp)

    # Single-ish: try unpack whole
    try:
        unp = bytearray(rnc_unpack(blob, verify_crc=False))
        scramble_unpacked(unp)
        return rnc_pack(bytes(unp), method=1)
    except Exception:
        return blob


def shuffle_section_experimental(data: bytes, index: int, seed: Optional[int]) -> bytes:
    sec, _, _ = get_section(data, index)
    if index == WARPS_SECTION:
        raise ValueError("Use shuffle-spawns for section 8")
    if index == SEC4:
        raise ValueError("Use shuffle-sec4 for section 4")
    new_sec = experimental_shuffle_blob(sec, seed)
    if new_sec == sec:
        print(f"  section {index}: no experimental changes (too complex or no candidates)")
        return data
    if len(new_sec) == len(sec):
        out = bytearray(data)
        patch_section_inplace(out, index, new_sec)
        return bytes(out)
    return replace_section(data, index, new_sec)


# ----- Commands -----

def cmd_info(path: Path) -> None:
    data = path.read_bytes()
    count, hs, ends = parse_header(data)
    ranges = section_ranges(hs, ends)
    print(f"{path.name}: {len(data)} bytes, {count} sections (indices 0..{count - 1}), header={hs}")
    labels = {
        4: "object defs / bosses / enemies (RNC)",
        8: "warps/spawns",
        1: "experimental single RNC",
        5: "experimental related table",
        9: "experimental multi RNC",
    }
    for i, (a, b) in enumerate(ranges):
        chunk = data[a:b]
        rnc = chunk.count(b"RNC")
        mark = f" <-- {labels[i]}" if i in labels else ""
        print(f"  [{i:2d}] {b - a:8d} bytes  RNC={rnc:4d}{mark}")


def cmd_list_spawns(path: Path, preset: str = "all") -> None:
    data = path.read_bytes()
    sec, _, _ = get_section(data, WARPS_SECTION)
    id_values, pos_recs = parse_spawn_table(sec)
    idxs = filter_spawn_indices(id_values, pos_recs, preset)
    print(f"Spawns: {len(pos_recs)} total, {len(idxs)} in preset '{preset}' (menu excluded)")
    for n, i in enumerate(idxs[:40]):
        off, rec = pos_recs[i]
        x, y, z, w = struct.unpack_from("<ffff", rec, 0)
        iv = id_values[i] if i < len(id_values) else None
        boss = " BOSS" if _is_boss_id(iv) else ""
        print(f"  [{n:3d}] id={iv} ({x:9.1f},{y:9.1f},{z:9.1f}){boss}")
    if len(idxs) > 40:
        print(f"  ... {len(idxs) - 40} more")


def cmd_list_sec4(path: Path) -> None:
    _need_rnc()
    data = path.read_bytes()
    packed, _, _ = get_section(data, SEC4)
    unp = unpack_sec4(packed)
    ids, base, recs = parse_sec4_records(unp)
    types = Counter(struct.unpack_from("<I", r, 0)[0] for r in recs)
    hi76 = Counter(struct.unpack_from("<I", r, SEC4_FIELD76)[0] >> 16 for r in recs)
    print(f"Section 4: packed={len(packed)} unpacked={len(unp)} records={len(recs)}")
    print(f"Types (top): {types.most_common(10)}")
    print(f"+76 hi (top): {hi76.most_common(12)}")


def cmd_shuffle_spawns(path: Path, seed: Optional[int], out: Optional[Path], preset: str = "all") -> None:
    data = bytearray(path.read_bytes())
    sec, _, _ = get_section(bytes(data), WARPS_SECTION)
    sec_ba = bytearray(sec)
    n = shuffle_positions(sec_ba, seed, preset=preset)
    if n < 2:
        print(f"Not enough spawn records for preset '{preset}' ({n}).")
        return
    patch_section_inplace(data, WARPS_SECTION, bytes(sec_ba))
    if out is None:
        out = path.with_name(f"{path.stem}_spawns_{preset}_seed{seed}{path.suffix}")
    out.write_bytes(data)
    print(f"Shuffled {n} spawns (preset={preset}, seed={seed}).")
    print(f"Wrote: {out}")


def cmd_shuffle_sec4(path: Path, seed: Optional[int], out: Optional[Path], mode: str = "values") -> None:
    _need_rnc()
    data = path.read_bytes()
    packed, _, _ = get_section(data, SEC4)
    unp = unpack_sec4(packed)
    new_unp, n = shuffle_sec4_fields(unp, seed=seed, mode=mode)
    new_packed = pack_sec4(new_unp)
    print(f"sec4 pack: {len(packed)} -> {len(new_packed)} (delta {len(new_packed) - len(packed):+d})")
    out_data = replace_section(data, SEC4, new_packed)
    if out is None:
        out = path.with_name(f"{path.stem}_sec4_{mode}_seed{seed}{path.suffix}")
    out.write_bytes(out_data)
    print(f"Shuffled sec4 on {n} records (mode={mode}, seed={seed}).")
    print(f"Wrote: {out} ({len(out_data)} bytes)")


def cmd_shuffle(
    path: Path,
    seed: Optional[int],
    out: Optional[Path],
    do_spawns: bool,
    do_sec4: bool,
    sections: Sequence[int],
    preset: str,
    sec4_mode: str,
) -> None:
    rng_seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    data = path.read_bytes()
    print(f"shuffle seed={rng_seed}")

    if do_spawns:
        sec, _, _ = get_section(data, WARPS_SECTION)
        sec_ba = bytearray(sec)
        n = shuffle_positions(sec_ba, rng_seed, preset=preset)
        data = bytearray(data)
        _, start, end = get_section(bytes(data), WARPS_SECTION)
        data[start:end] = sec_ba
        data = bytes(data)
        print(f"  sec8 spawns: {n} (preset={preset})")

    if do_sec4:
        _need_rnc()
        packed, _, _ = get_section(data, SEC4)
        unp = unpack_sec4(packed)
        new_unp, n = shuffle_sec4_fields(unp, seed=rng_seed + 1, mode=sec4_mode)
        new_packed = pack_sec4(new_unp)
        data = replace_section(data, SEC4, new_packed)
        print(f"  sec4 objects: {n} (mode={sec4_mode})")

    for si in sections:
        if si in (WARPS_SECTION, SEC4):
            continue
        try:
            before = len(data)
            data = shuffle_section_experimental(data, si, rng_seed + 10 + si)
            print(f"  sec{si} experimental: size {before} -> {len(data)}")
        except Exception as e:
            print(f"  sec{si} experimental FAILED: {e}")

    if out is None:
        out = path.with_name(f"{path.stem}_rand_seed{rng_seed}{path.suffix}")
    out.write_bytes(data)
    print(f"Wrote: {out} ({len(data)} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Turok 1 PC Cartdata.dat randomizer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info")
    p.add_argument("file", type=Path)

    p = sub.add_parser("list-spawns")
    p.add_argument("file", type=Path)
    p.add_argument("--preset", choices=("all", "boss", "no_boss"), default="all")

    p = sub.add_parser("list-sec4")
    p.add_argument("file", type=Path)

    p = sub.add_parser("shuffle-spawns")
    p.add_argument("file", type=Path)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--preset", choices=("all", "boss", "no_boss"), default="all")

    p = sub.add_parser("shuffle-sec4")
    p.add_argument("file", type=Path)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--mode", choices=("values", "swap", "scale", "scale_values"), default="values")

    p = sub.add_parser("shuffle-section")
    p.add_argument("file", type=Path)
    p.add_argument("--section", type=int, required=True)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("-o", "--output", type=Path, default=None)

    p = sub.add_parser("shuffle")
    p.add_argument("file", type=Path)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--spawns", action="store_true")
    p.add_argument("--sec4", action="store_true")
    p.add_argument("--sections", type=str, default="", help="Comma list e.g. 1,5,9,10")
    p.add_argument("--preset", choices=("all", "boss", "no_boss"), default="all")
    p.add_argument("--sec4-mode", choices=("values", "swap", "scale", "scale_values"), default="values")

    args = ap.parse_args()
    if args.cmd == "info":
        cmd_info(args.file)
    elif args.cmd == "list-spawns":
        cmd_list_spawns(args.file, preset=args.preset)
    elif args.cmd == "list-sec4":
        cmd_list_sec4(args.file)
    elif args.cmd == "shuffle-spawns":
        cmd_shuffle_spawns(args.file, args.seed, args.output, preset=args.preset)
    elif args.cmd == "shuffle-sec4":
        cmd_shuffle_sec4(args.file, args.seed, args.output, mode=args.mode)
    elif args.cmd == "shuffle-section":
        data = args.file.read_bytes()
        out_data = shuffle_section_experimental(data, args.section, args.seed)
        out = args.output or args.file.with_name(f"{args.file.stem}_sec{args.section}{args.file.suffix}")
        out.write_bytes(out_data)
        print(f"Wrote: {out}")
    elif args.cmd == "shuffle":
        secs = [int(x) for x in args.sections.split(",") if x.strip().isdigit()]
        if not args.spawns and not args.sec4 and not secs:
            ap.error("Enable --spawns and/or --sec4 and/or --sections")
        cmd_shuffle(
            args.file, args.seed, args.output,
            do_spawns=args.spawns, do_sec4=args.sec4, sections=secs,
            preset=args.preset, sec4_mode=args.sec4_mode,
        )


if __name__ == "__main__":
    main()
