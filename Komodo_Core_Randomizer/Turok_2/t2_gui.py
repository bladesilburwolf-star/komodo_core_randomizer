#!/usr/bin/env python3
"""
Turok 2: Seeds of Evil (PC) — Randomizer GUI
Spawn presets (all / boss / no_boss) + experimental section toggles.
"""
from __future__ import annotations

import random
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import t2_tool
except ImportError:
    messagebox.showerror("Error", "Could not find t2_tool.py in the same folder.")
    sys.exit(1)


class TextRedirector:
    def __init__(self, widget: tk.Text):
        self.widget = widget

    def write(self, s: str) -> None:
        self.widget.insert(tk.END, s)
        self.widget.see(tk.END)

    def flush(self) -> None:
        pass


class Turok2GUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Turok 2 PC — Randomizer")
        self.geometry("880x740")
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
        ttk.Label(self, text="Turok 2 PC — Randomizer", font=("Segoe UI", 16, "bold")).pack(pady=(12, 2))
        ttk.Label(
            self,
            text="Seeds of Evil LSS · boss-rush maps 1–4 · section trial toggles",
            foreground="#aaaaaa",
        ).pack()

        src_f = ttk.LabelFrame(self, text=" LSS file (input) ")
        src_f.pack(fill=tk.X, **pad)
        self.src_var = tk.StringVar()
        ttk.Entry(src_f, textvariable=self.src_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=6)
        ttk.Button(src_f, text="Browse…", command=self._browse_src).pack(side=tk.RIGHT, padx=8, pady=6)

        out_f = ttk.LabelFrame(self, text=" Output file ")
        out_f.pack(fill=tk.X, **pad)
        self.out_var = tk.StringVar()
        ttk.Entry(out_f, textvariable=self.out_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=6)
        ttk.Button(out_f, text="Browse…", command=self._browse_out).pack(side=tk.RIGHT, padx=8, pady=6)

        pre = ttk.LabelFrame(self, text=" Spawn preset (section 8) ")
        pre.pack(fill=tk.X, **pad)
        self.preset = tk.StringVar(value="all")
        for val, label in (
            ("all", "All spawns (~213)"),
            ("boss", "Boss rush — Blind One / Queen / Mother / Primagen only (maps 1–4)"),
            ("no_boss", "No bosses — exclude boss arena maps"),
        ):
            ttk.Radiobutton(pre, text=label, variable=self.preset, value=val).pack(anchor=tk.W, padx=12, pady=1)

        known = ttk.LabelFrame(self, text=" Known randomizers ")
        known.pack(fill=tk.X, **pad)
        self.do_spawns = tk.BooleanVar(value=True)
        self.do_weapons = tk.BooleanVar(value=False)
        self.do_particles = tk.BooleanVar(value=False)
        ttk.Checkbutton(known, text="[8] Spawns / warps", variable=self.do_spawns).pack(anchor=tk.W, padx=12, pady=1)
        ttk.Checkbutton(
            known,
            text="[5] Weapon model-IDs (EXPERIMENTAL — can cause hive/lightship loops)",
            variable=self.do_weapons,
        ).pack(anchor=tk.W, padx=12, pady=1)
        ttk.Checkbutton(
            known,
            text="[4] Particles chaos (safe boot — weaker enemies, stronger claw, FX off, +FPS)",
            variable=self.do_particles,
        ).pack(anchor=tk.W, padx=12, pady=1)

        exp = ttk.LabelFrame(
            self,
            text=" Experimental section toggles (trial & error — one at a time recommended) ",
        )
        exp.pack(fill=tk.X, **pad)
        self.sec_vars = {}
        row = ttk.Frame(exp)
        row.pack(fill=tk.X, padx=8, pady=4)
        # 21 sections 0..20; skip 8 (spawns handled above)
        names = getattr(t2_tool, "SECTION_NAMES", {})
        col = 0
        for si in range(21):
            if si == 8:
                continue
            var = tk.BooleanVar(value=False)
            self.sec_vars[si] = var
            label = f"{si}"
            if si in names:
                short = names[si].replace("_", "")[:8]
                label = f"{si}:{short}"
            ttk.Checkbutton(row, text=label, variable=var).grid(
                row=col // 5, column=col % 5, sticky="w", padx=4, pady=1
            )
            col += 1
        ttk.Label(
            exp,
            text="Tip: enable one experimental section per run. Sec5 is huge — prefer weapon toggle above.",
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
        ttk.Button(btn, text="List maps", command=self._list_maps).pack(side=tk.LEFT, padx=4)
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
        self._log("Weapon model shuffle stays OFF by default (known softlock risk).\n")

    def _log(self, msg: str) -> None:
        self.log.insert(tk.END, msg)
        self.log.see(tk.END)

    def _rand_seed(self) -> None:
        self.seed_var.set(str(random.randint(100000, 999999)))

    def _browse_src(self) -> None:
        p = filedialog.askopenfilename(
            title="Select LSS",
            filetypes=[("LSS", "*.lss"), ("All", "*.*")],
        )
        if p:
            self.src_var.set(p)
            if not self.out_var.get().strip():
                src = Path(p)
                self.out_var.set(str(src.with_name(f"{src.stem}_rand{src.suffix}")))

    def _browse_out(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Save randomized LSS as…",
            defaultextension=".lss",
            filetypes=[("LSS", "*.lss"), ("All", "*.*")],
        )
        if p:
            self.out_var.set(p)

    def _src(self) -> Path | None:
        s = self.src_var.get().strip()
        if not s:
            messagebox.showerror("Missing file", "Select an LSS first.")
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
            t2_tool.cmd_info(p)

    def _list_spawns(self) -> None:
        p = self._src()
        if p:
            self._log(f"\n--- list-spawns preset={self.preset.get()} ---\n")
            t2_tool.cmd_list_spawns(p, preset=self.preset.get())

    def _list_maps(self) -> None:
        p = self._src()
        if p:
            self._log("\n--- list-maps ---\n")
            t2_tool.cmd_list_maps(p)

    def _run(self) -> None:
        p = self._src()
        if not p:
            return
        secs = [i for i, v in self.sec_vars.items() if v.get()]
        if self.do_particles.get() and 4 not in secs:
            secs.append(4)
        if not self.do_spawns.get() and not self.do_weapons.get() and not secs:
            messagebox.showerror("Nothing selected", "Enable at least one option.")
            return
        seed = self._seed()
        out_s = self.out_var.get().strip()
        out = Path(out_s) if out_s else None
        self._log(f"\n--- generate seed={seed} ---\n")
        try:
            t2_tool.cmd_shuffle(
                p,
                seed,
                out,
                do_spawns=self.do_spawns.get(),
                do_weapons=self.do_weapons.get(),
                sections=secs,
                preset=self.preset.get(),
            )
            messagebox.showinfo("Done", f"Finished.\nSeed: {seed}")
        except Exception as e:
            self._log(f"ERROR: {e}\n")
            messagebox.showerror("Failed", str(e))


def main() -> None:
    Turok2GUI().mainloop()


if __name__ == "__main__":
    main()
