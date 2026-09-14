#!/usr/bin/env python3
"""Turok 1 PC Randomizer GUI — presets + per-section toggles."""
from __future__ import annotations

import random
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import t1_tool
except ImportError:
    messagebox.showerror("Error", "Could not find t1_tool.py in the same folder.")
    sys.exit(1)


class TextRedirector:
    def __init__(self, widget: tk.Text):
        self.widget = widget

    def write(self, s: str) -> None:
        self.widget.insert(tk.END, s)
        self.widget.see(tk.END)

    def flush(self) -> None:
        pass


class Turok1GUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Turok 1 PC — Randomizer")
        self.geometry("860x720")
        self.minsize(720, 600)
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self._configure_styles()
        self._build()

    def _configure_styles(self) -> None:
        dark_bg, dark_fg, entry_bg, accent = "#2b2b2b", "#ffffff", "#3c3f41", "#4a6ea9"
        self.configure(bg=dark_bg)
        self.style.configure(".", background=dark_bg, foreground=dark_fg, fieldbackground=entry_bg)
        self.style.configure("TButton", background="#3c3f41", foreground=dark_fg, borderwidth=1)
        self.style.map("TButton", background=[("active", accent)])
        self.style.configure("TLabelframe", background=dark_bg, foreground=dark_fg)
        self.style.configure("TLabelframe.Label", background=dark_bg, foreground=dark_fg)
        self.style.configure("TLabel", background=dark_bg, foreground=dark_fg)
        self.style.configure("TRadiobutton", background=dark_bg, foreground=dark_fg)
        self.style.configure("TCheckbutton", background=dark_bg, foreground=dark_fg)
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=dark_fg)
        self.style.configure("Accent.TButton", background=accent, foreground=dark_fg)

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 4}
        ttk.Label(self, text="Turok 1 PC — Randomizer", font=("Segoe UI", 16, "bold")).pack(pady=(12, 2))
        ttk.Label(
            self,
            text="Sections 0–10 · boss-rush preset · trial toggles for unknown sections",
            foreground="#aaaaaa",
        ).pack()

        src_f = ttk.LabelFrame(self, text=" Cartdata.dat (input) ")
        src_f.pack(fill=tk.X, **pad)
        self.src_var = tk.StringVar()
        ttk.Entry(src_f, textvariable=self.src_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=6)
        ttk.Button(src_f, text="Browse…", command=self._browse_src).pack(side=tk.RIGHT, padx=8, pady=6)

        out_f = ttk.LabelFrame(self, text=" Output file ")
        out_f.pack(fill=tk.X, **pad)
        self.out_var = tk.StringVar()
        ttk.Entry(out_f, textvariable=self.out_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=6)
        ttk.Button(out_f, text="Browse…", command=self._browse_out).pack(side=tk.RIGHT, padx=8, pady=6)

        # Spawn preset
        pre = ttk.LabelFrame(self, text=" Spawn preset (section 8) ")
        pre.pack(fill=tk.X, **pad)
        self.preset = tk.StringVar(value="all")
        for val, label in (
            ("all", "All gameplay spawns (menu/loading excluded)"),
            ("boss", "Boss rush — boss arenas only (~25 points)"),
            ("no_boss", "No bosses — exclude boss arena warps"),
        ):
            ttk.Radiobutton(pre, text=label, variable=self.preset, value=val).pack(anchor=tk.W, padx=12, pady=1)

        # Known sections
        known = ttk.LabelFrame(self, text=" Known randomizers ")
        known.pack(fill=tk.X, **pad)
        self.do_spawns = tk.BooleanVar(value=True)
        self.do_sec4 = tk.BooleanVar(value=False)
        ttk.Checkbutton(known, text="[8] Spawns / warps", variable=self.do_spawns).pack(anchor=tk.W, padx=12, pady=1)
        ttk.Checkbutton(
            known,
            text="[4] Object defs (+76/+84 amounts — enemies/bosses/pickups)",
            variable=self.do_sec4,
        ).pack(anchor=tk.W, padx=12, pady=1)

        mode_f = ttk.Frame(known)
        mode_f.pack(fill=tk.X, padx=24, pady=2)
        ttk.Label(mode_f, text="Sec4 mode:").pack(side=tk.LEFT)
        self.sec4_mode = tk.StringVar(value="values")
        ttk.Radiobutton(mode_f, text="Values", variable=self.sec4_mode, value="values").pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(mode_f, text="Swap", variable=self.sec4_mode, value="swap").pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(mode_f, text="Scale", variable=self.sec4_mode, value="scale").pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(mode_f, text="Scale+Values", variable=self.sec4_mode, value="scale_values").pack(side=tk.LEFT, padx=6)

        # Experimental section toggles (trial & error) — 11 sections total 0..10
        exp = ttk.LabelFrame(self, text=" Experimental section toggles (trial & error — one at a time recommended) ")
        exp.pack(fill=tk.X, **pad)
        self.sec_vars = {}
        row = ttk.Frame(exp)
        row.pack(fill=tk.X, padx=8, pady=4)
        labels = {
            0: "0 mesh",
            1: "1 RNC",
            2: "2 tiny",
            3: "3 mesh",
            5: "5 table",
            6: "6 mesh",
            7: "7 tiny",
            9: "9 multi",
            10: "10 tail",
        }
        # Note: 4 and 8 handled above; user asked for section toggles including exploring others
        col = 0
        for si in range(11):
            if si in (4, 8):
                continue
            var = tk.BooleanVar(value=False)
            self.sec_vars[si] = var
            ttk.Checkbutton(row, text=labels.get(si, str(si)), variable=var).grid(row=col // 5, column=col % 5, sticky="w", padx=6, pady=2)
            col += 1
        ttk.Label(
            exp,
            text="Tip: enable one experimental section per run to see what it affects in-game.",
            foreground="#888888",
        ).pack(anchor=tk.W, padx=12, pady=(0, 4))

        seed_f = ttk.Frame(self)
        seed_f.pack(fill=tk.X, **pad)
        ttk.Label(seed_f, text="Seed:").pack(side=tk.LEFT, padx=(4, 6))
        self.seed_var = tk.StringVar()
        ttk.Entry(seed_f, textvariable=self.seed_var, width=14).pack(side=tk.LEFT)
        ttk.Button(seed_f, text="Random", command=self._rand_seed).pack(side=tk.LEFT, padx=8)

        btn = ttk.Frame(self)
        btn.pack(fill=tk.X, **pad)
        ttk.Button(btn, text="List spawns", command=self._list_spawns).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn, text="List sec4", command=self._list_sec4).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn, text="File info", command=self._info).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn, text="Generate", style="Accent.TButton", command=self._run).pack(side=tk.RIGHT, padx=4)

        log_f = ttk.LabelFrame(self, text=" Log ")
        log_f.pack(fill=tk.BOTH, expand=True, **pad)
        self.log = tk.Text(
            log_f, height=12, bg="#1e1e1e", fg="#dddddd", insertbackground="white",
            font=("Consolas", 10), wrap=tk.WORD,
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        sys.stdout = TextRedirector(self.log)
        sys.stderr = TextRedirector(self.log)
        self._log("Boss rush: preset=Boss, only [8] Spawns, Generate.\n")
        self._log("Trial: enable one experimental section only (e.g. [1] or [5]), leave others off.\n")
        self._log("Note: cart has sections 0..10 (11 total). There is no section 11 index.\n")

    def _log(self, msg: str) -> None:
        self.log.insert(tk.END, msg)
        self.log.see(tk.END)

    def _rand_seed(self) -> None:
        self.seed_var.set(str(random.randint(100000, 999999)))

    def _browse_src(self) -> None:
        p = filedialog.askopenfilename(
            title="Select Cartdata.dat",
            filetypes=[("Cartdata", "Cartdata.dat"), ("DAT", "*.dat"), ("All", "*.*")],
        )
        if p:
            self.src_var.set(p)
            if not self.out_var.get().strip():
                src = Path(p)
                self.out_var.set(str(src.with_name(f"{src.stem}_rand{src.suffix}")))

    def _browse_out(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Save randomized Cartdata as…",
            defaultextension=".dat",
            filetypes=[("DAT", "*.dat"), ("All", "*.*")],
        )
        if p:
            self.out_var.set(p)

    def _src(self) -> Path | None:
        s = self.src_var.get().strip()
        if not s:
            messagebox.showerror("Missing file", "Select Cartdata.dat first.")
            return None
        p = Path(s)
        if not p.is_file():
            messagebox.showerror("Missing file", f"Not found:\n{p}")
            return None
        return p

    def _seed(self) -> int:
        raw = self.seed_var.get().strip()
        if raw.isdigit():
            return int(raw)
        seed = random.randint(100000, 999999)
        self.seed_var.set(str(seed))
        return seed

    def _info(self) -> None:
        p = self._src()
        if p:
            self._log("\n--- info ---\n")
            t1_tool.cmd_info(p)

    def _list_spawns(self) -> None:
        p = self._src()
        if p:
            self._log(f"\n--- list-spawns preset={self.preset.get()} ---\n")
            t1_tool.cmd_list_spawns(p, preset=self.preset.get())

    def _list_sec4(self) -> None:
        p = self._src()
        if p:
            self._log("\n--- list-sec4 ---\n")
            try:
                t1_tool.cmd_list_sec4(p)
            except Exception as e:
                self._log(f"ERROR: {e}\n")
                messagebox.showerror("Failed", str(e))

    def _run(self) -> None:
        p = self._src()
        if not p:
            return
        secs = [i for i, v in self.sec_vars.items() if v.get()]
        if not self.do_spawns.get() and not self.do_sec4.get() and not secs:
            messagebox.showerror("Nothing selected", "Enable at least one option.")
            return
        seed = self._seed()
        out_s = self.out_var.get().strip()
        out = Path(out_s) if out_s else None
        self._log(f"\n--- generate seed={seed} ---\n")
        try:
            t1_tool.cmd_shuffle(
                p,
                seed,
                out,
                do_spawns=self.do_spawns.get(),
                do_sec4=self.do_sec4.get(),
                sections=secs,
                preset=self.preset.get(),
                sec4_mode=self.sec4_mode.get(),
            )
            messagebox.showinfo("Done", f"Finished.\nSeed: {seed}")
        except Exception as e:
            self._log(f"ERROR: {e}\n")
            messagebox.showerror("Failed", str(e))


def main() -> None:
    Turok1GUI().mainloop()


if __name__ == "__main__":
    main()
