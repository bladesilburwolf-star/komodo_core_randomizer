#!/usr/bin/env python3
"""Turok 2 — Cheat / Toybox GUI (live trainer + EXE patch helper)."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import t2_cheats


class CheatsGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Turok 2 — Toybox / Cheats")
        self.geometry("640x560")
        self.configure(bg="#2b2b2b")
        style = ttk.Style(self)
        style.theme_use("clam")
        for k in (".", "TLabel", "TButton", "TLabelframe", "TLabelframe.Label", "TCheckbutton", "TRadiobutton"):
            style.configure(k, background="#2b2b2b", foreground="#fff")
        style.configure("TButton", background="#3c3f41")
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="Turok 2 Toybox", font=("Segoe UI", 16, "bold")).pack(pady=10)
        ttk.Label(
            self,
            text="Live flags need Windows + Turok2MP running. EXE patch works offline.",
            foreground="#aaa",
        ).pack()

        pre = ttk.LabelFrame(self, text=" Presets ")
        pre.pack(fill="x", padx=12, pady=6)
        self.preset = tk.StringVar(value="blackout_boss")
        for name, mask in t2_cheats.PRESETS.items():
            ttk.Radiobutton(
                pre,
                text=f"{name}  ({mask:#06x})  {t2_cheats.describe(mask)}",
                variable=self.preset,
                value=name,
            ).pack(anchor="w", padx=8, pady=1)

        bits = ttk.LabelFrame(self, text=" Individual bits (OR with preset if both used) ")
        bits.pack(fill="x", padx=12, pady=6)
        self.bit_vars = {}
        row = ttk.Frame(bits)
        row.pack(fill="x", padx=6, pady=4)
        for i, (bit, name) in enumerate(sorted(t2_cheats.BITS.items())):
            v = tk.BooleanVar(value=False)
            self.bit_vars[bit] = v
            ttk.Checkbutton(row, text=name, variable=v).grid(row=i // 3, column=i % 3, sticky="w", padx=4, pady=1)

        live = ttk.LabelFrame(self, text=" Live process (Windows) ")
        live.pack(fill="x", padx=12, pady=6)
        bf = ttk.Frame(live)
        bf.pack(fill="x", padx=8, pady=6)
        ttk.Button(bf, text="Read status", command=self._status).pack(side="left", padx=4)
        ttk.Button(bf, text="Apply (set)", command=lambda: self._apply("set")).pack(side="left", padx=4)
        ttk.Button(bf, text="Apply (OR)", command=lambda: self._apply("or")).pack(side="left", padx=4)
        ttk.Button(bf, text="Clear all", command=self._clear).pack(side="left", padx=4)

        patch = ttk.LabelFrame(self, text=" Static EXE patch (Turok2MP default init) ")
        patch.pack(fill="x", padx=12, pady=6)
        self.exe_var = tk.StringVar()
        ttk.Entry(patch, textvariable=self.exe_var).pack(side="left", fill="x", expand=True, padx=8, pady=8)
        ttk.Button(patch, text="Browse…", command=self._browse).pack(side="left", padx=4)
        ttk.Button(patch, text="Patch copy…", command=self._patch).pack(side="left", padx=8)

        logf = ttk.LabelFrame(self, text=" Log ")
        logf.pack(fill="both", expand=True, padx=12, pady=6)
        self.log = tk.Text(logf, height=10, bg="#1e1e1e", fg="#ddd", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=6, pady=6)
        self._say("Presets map to bitfield 0x5D5A60 (MP). SP needs signature scan later.\n")

    def _say(self, s: str) -> None:
        self.log.insert("end", s)
        self.log.see("end")

    def _mask(self) -> int:
        m = t2_cheats.PRESETS.get(self.preset.get(), 0)
        for bit, var in self.bit_vars.items():
            if var.get():
                m |= bit
        return m

    def _status(self) -> None:
        try:
            if sys.platform != "win32":
                self._say("Live status requires Windows.\n")
                return
            mask = t2_cheats.live_read_mask()
            self._say(f"Live {mask:#06x}: {t2_cheats.describe(mask)}\n")
        except Exception as e:
            self._say(f"ERROR: {e}\n")
            messagebox.showerror("Status", str(e))

    def _apply(self, mode: str) -> None:
        try:
            mask = self._mask()
            if sys.platform != "win32":
                raise RuntimeError("Live apply requires Windows + running game")
            new = t2_cheats.live_write_mask(mask, mode=mode if mode != "set" else "set")
            if mode == "or":
                new = t2_cheats.live_write_mask(mask, mode="or")
            self._say(f"Applied {new:#06x}: {t2_cheats.describe(new)}\n")
        except Exception as e:
            self._say(f"ERROR: {e}\n")
            messagebox.showerror("Apply", str(e))

    def _clear(self) -> None:
        try:
            if sys.platform != "win32":
                raise RuntimeError("Windows only")
            t2_cheats.live_write_mask(0, mode="clear")
            self._say("Cleared bitfield to 0\n")
        except Exception as e:
            self._say(f"ERROR: {e}\n")
            messagebox.showerror("Clear", str(e))

    def _browse(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("EXE", "*.exe")])
        if p:
            self.exe_var.set(p)

    def _patch(self) -> None:
        src = Path(self.exe_var.get().strip())
        if not src.is_file():
            messagebox.showerror("Patch", "Select Turok2MP.exe first")
            return
        out = filedialog.asksaveasfilename(defaultextension=".exe", initialfile="Turok2MP_toybox.exe")
        if not out:
            return
        try:
            mask = self._mask()
            t2_cheats.patch_exe_init(src, Path(out), mask)
            self._say(f"Patched {out} mask={mask:#06x}\n")
            messagebox.showinfo("Patch", f"Wrote {out}\nKeep original backup.")
        except Exception as e:
            self._say(f"ERROR: {e}\n")
            messagebox.showerror("Patch", str(e))


if __name__ == "__main__":
    CheatsGUI().mainloop()
