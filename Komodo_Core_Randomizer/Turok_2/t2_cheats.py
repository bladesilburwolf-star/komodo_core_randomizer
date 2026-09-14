#!/usr/bin/env python3
"""
Turok 2 PC — Cheat flag trainer + optional EXE default patch (MP).

Flags live in a DWORD bitfield (Turok2MP.exe VA 0x005D5A60).

  python t2_cheats.py list
  python t2_cheats.py apply --preset scale_chaos
  python t2_cheats.py apply --bits 0x40,0x8000
  python t2_cheats.py clear
  python t2_cheats.py patch-exe Turok2MP.exe --preset blackout_boss -o Turok2MP_toybox.exe
  python t2_cheats.py status

Windows only for live apply (Read/WriteProcessMemory).
EXE patch works on any OS (static default at init site).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional

# --- Flag database (from static RE of Turok2MP.exe) ---
BITFIELD_VA = 0x005D5A60
# Secondary dword also referenced; leave alone unless we map it
SECONDARY_VA = 0x005D5A64

# Init write found in .text: mov dword [0x5D5A60], 0x0C
INIT_MOV_VA = 0x00473F41  # C7 05 60 5A 5D 00 0C 00 00 00

BITS: Dict[int, str] = {
    0x0002: "invincibility",
    0x0004: "infinite_lives",
    0x0008: "all_weapons",
    0x0010: "unlimited_ammo",
    0x0020: "all_special_objects",
    0x0040: "big_head",
    0x0080: "tiny",
    0x0100: "stick",
    0x0400: "big_hands_feet",
    0x0800: "gouraud",
    0x1000: "juans_cheat",
    0x2000: "zach_attack",
    0x4000: "all_map",
    0x8000: "blackout",
}

PRESETS: Dict[str, int] = {
    "scale_chaos": 0x0040 | 0x0080 | 0x0100 | 0x0400,
    "blackout_boss": 0x8000 | 0x0040,
    "player_power": 0x0002 | 0x0008 | 0x0010,
    "full_toybox": 0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0020
    | 0x0040 | 0x0080 | 0x0100 | 0x0400 | 0x0800 | 0x1000 | 0x2000 | 0x4000 | 0x8000,
    "classic_cheat": 0x0002 | 0x0008 | 0x0010 | 0x0020,  # invinc + guns + ammo + keys
}


def mask_from_names(names: List[str]) -> int:
    inv = {v: k for k, v in BITS.items()}
    m = 0
    for n in names:
        n = n.strip().lower().replace(" ", "_")
        if n not in inv:
            raise SystemExit(f"Unknown bit name: {n}. Known: {list(inv)}")
        m |= inv[n]
    return m


def describe(mask: int) -> str:
    parts = [name for bit, name in sorted(BITS.items()) if mask & bit]
    return ", ".join(parts) if parts else "(none)"


def cmd_list() -> None:
    print(f"Bitfield VA: {BITFIELD_VA:#010x}  (Turok2MP.exe)")
    print(f"Init site:   {INIT_MOV_VA:#010x}  mov dword [bitfield], imm32")
    print("\nBits:")
    for bit, name in sorted(BITS.items()):
        print(f"  {bit:#06x}  {name}")
    print("\nPresets:")
    for name, mask in PRESETS.items():
        print(f"  {name:16s} {mask:#06x}  {describe(mask)}")


# ----- Live process (Windows) -----

def _windows_open_process(pid: int):
    import ctypes
    from ctypes import wintypes

    PROCESS_ALL = 0x1F0FFF
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(PROCESS_ALL, False, pid)
    if not h:
        raise OSError(f"OpenProcess failed for pid={pid}")
    return k32, h


def _find_pid(image_names: List[str]) -> Optional[int]:
    """Find PID by executable name (best-effort)."""
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.windll.kernel32
        TH32CS_SNAPPROCESS = 0x2

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
        names = {n.lower() for n in image_names}
        pid = None
        if k32.Process32First(snap, ctypes.byref(pe)):
            while True:
                exe = pe.szExeFile.decode("latin1", "replace").lower()
                if exe in names or any(exe.endswith(n) for n in names):
                    pid = pe.th32ProcessID
                    break
                if not k32.Process32Next(snap, ctypes.byref(pe)):
                    break
        k32.CloseHandle(snap)
        return pid
    except Exception:
        return None


def _module_base(pid: int, module_name: str) -> Optional[int]:
    """Return base address of module in process (for ASLR-aware write)."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    TH32CS_SNAPMODULE = 0x8 | 0x10

    class MODULEENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("th32ModuleID", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("GlblcntUsage", wintypes.DWORD),
            ("ProccntUsage", wintypes.DWORD),
            ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
            ("modBaseSize", wintypes.DWORD),
            ("hModule", wintypes.HMODULE),
            ("szModule", ctypes.c_char * 256),
            ("szExePath", ctypes.c_char * 260),
        ]

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    if snap == -1:
        # try without 32-bit flag variants
        snap = k32.CreateToolhelp32Snapshot(0x8, pid)
    me = MODULEENTRY32()
    me.dwSize = ctypes.sizeof(MODULEENTRY32)
    want = module_name.lower()
    base = None
    if k32.Module32First(snap, ctypes.byref(me)):
        while True:
            mod = me.szModule.decode("latin1", "replace").lower()
            if mod == want or mod.endswith(want):
                base = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
                break
            if not k32.Module32Next(snap, ctypes.byref(me)):
                break
    k32.CloseHandle(snap)
    return base


def live_read_mask(pid: Optional[int] = None) -> int:
    import ctypes
    from ctypes import wintypes

    if pid is None:
        pid = _find_pid(["turok2mp.exe", "turok2.exe"])
    if not pid:
        raise SystemExit("Turok 2 process not found. Start the game first.")
    k32, h = _windows_open_process(pid)
    # Prefer module-relative: preferred base 0x400000 → offset 0x1D5A60
    base = _module_base(pid, "Turok2MP.exe") or _module_base(pid, "Turok2.exe") or 0x400000
    addr = base + 0x1D5A60
    buf = ctypes.c_uint32()
    nread = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(addr), ctypes.byref(buf), 4, ctypes.byref(nread))
    k32.CloseHandle(h)
    if not ok:
        raise OSError(f"ReadProcessMemory failed at {addr:#x}")
    return buf.value


def live_write_mask(mask: int, pid: Optional[int] = None, mode: str = "set") -> int:
    """mode=set replace; or=OR bits on; clear=write 0."""
    import ctypes
    from ctypes import wintypes

    if pid is None:
        pid = _find_pid(["turok2mp.exe", "turok2.exe"])
    if not pid:
        raise SystemExit("Turok 2 process not found. Start the game first.")
    k32, h = _windows_open_process(pid)
    base = _module_base(pid, "Turok2MP.exe") or _module_base(pid, "Turok2.exe") or 0x400000
    addr = base + 0x1D5A60
    cur = ctypes.c_uint32()
    n = ctypes.c_size_t()
    k32.ReadProcessMemory(h, ctypes.c_void_p(addr), ctypes.byref(cur), 4, ctypes.byref(n))
    if mode == "or":
        new = cur.value | mask
    elif mode == "clear":
        new = 0
    else:
        new = mask
    val = ctypes.c_uint32(new)
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), ctypes.byref(val), 4, ctypes.byref(n))
    k32.CloseHandle(h)
    if not ok:
        raise OSError(f"WriteProcessMemory failed at {addr:#x}")
    return new


def cmd_status() -> None:
    if sys.platform != "win32":
        print("Live status requires Windows + running Turok2MP.")
        print(f"Static target VA {BITFIELD_VA:#x} offset from image base +0x1D5A60")
        return
    mask = live_read_mask()
    print(f"Current mask: {mask:#06x}")
    print(f"Active: {describe(mask)}")


def cmd_apply(mask: int, mode: str = "set") -> None:
    if sys.platform != "win32":
        raise SystemExit("Live apply requires Windows.")
    new = live_write_mask(mask, mode=mode)
    print(f"Wrote mask {new:#06x}: {describe(new)}")


# ----- Static EXE patch (default bits at init) -----

def patch_exe_init(src: Path, out: Path, mask: int) -> None:
    """Patch mov dword [0x5D5A60], imm32 at known VA so the game boots with bits set."""
    data = bytearray(src.read_bytes())
    # Prefer signature scan: C7 05 60 5A 5D 00 ?? ?? ?? ??
    sig = bytes.fromhex("C705605A5D00")
    idx = data.find(sig)
    if idx < 0:
        # try file offset from known VA (non-ASLR file layout)
        fo = INIT_MOV_VA - 0x400000
        if data[fo:fo+6] == sig:
            idx = fo
        else:
            raise SystemExit("Init mov signature not found — is this Turok2MP.exe?")
    old_imm = struct.unpack_from("<I", data, idx + 6)[0]
    struct.pack_into("<I", data, idx + 6, mask & 0xFFFFFFFF)
    out.write_bytes(data)
    print(f"Patched init imm {old_imm:#x} -> {mask:#x} ({describe(mask)})")
    print(f"Wrote: {out}")
    print("Note: only applies when that init path runs; keep a backup of the original EXE.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Turok 2 cheat flags — trainer + EXE patch")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show bits and presets")
    sub.add_parser("status", help="Read live bitfield from running game (Windows)")

    p = sub.add_parser("apply", help="Write flags to running game (Windows)")
    p.add_argument("--preset", choices=list(PRESETS), default=None)
    p.add_argument("--bits", type=str, default=None, help="Comma masks or names e.g. 0x40,blackout")
    p.add_argument("--or", dest="or_mode", action="store_true", help="OR onto existing instead of replace")

    p = sub.add_parser("clear", help="Clear all known flags in running game")
    p = sub.add_parser("patch-exe", help="Static-patch MP EXE default init mask")
    p.add_argument("exe", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--preset", choices=list(PRESETS), default="blackout_boss")
    p.add_argument("--mask", type=lambda x: int(x, 0), default=None)

    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list()
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "clear":
        cmd_apply(0, mode="clear")
    elif args.cmd == "apply":
        mask = 0
        if args.preset:
            mask |= PRESETS[args.preset]
        if args.bits:
            for part in args.bits.split(","):
                part = part.strip()
                if not part:
                    continue
                if part.lower().startswith("0x") or part.isdigit():
                    mask |= int(part, 0)
                else:
                    mask |= mask_from_names([part])
        if not mask and not args.preset:
            raise SystemExit("Specify --preset and/or --bits")
        cmd_apply(mask, mode="or" if args.or_mode else "set")
    elif args.cmd == "patch-exe":
        mask = args.mask if args.mask is not None else PRESETS[args.preset]
        patch_exe_init(args.exe, args.output, mask)


if __name__ == "__main__":
    main()
