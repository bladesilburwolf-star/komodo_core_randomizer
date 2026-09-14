#!/usr/bin/env python3
"""
Turok Evolution PC — Randomizer GUI
ShadowMan-style front-end for te_tool.py

Always writes output OUTSIDE the levels source tree (prevents nested out_enemies loops).
"""
from __future__ import annotations

import random
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import te_tool
except ImportError:
    messagebox.showerror("Error", "Could not find te_tool.py in the same folder.")
    sys.exit(1)


class TextRedirector:
    def __init__(self, widget: tk.Text):
        self.widget = widget

    def write(self, s: str) -> None:
        self.widget.insert(tk.END, s)
        self.widget.see(tk.END)

    def flush(self) -> None:
        pass


class EvolutionGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Turok Evolution PC — Randomizer")
        self.geometry("820x620")
        self.minsize(700, 500)

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
        self.style.configure("TRadiobutton", background=dark_bg, foreground=dark_fg)
        self.style.configure("TLabel", background=dark_bg, foreground=dark_fg)
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=dark_fg)
        self.style.configure("Accent.TButton", background=accent, foreground=dark_fg)

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}

        hdr = ttk.Label(self, text="Turok Evolution PC Randomizer", font=("Segoe UI", 16, "bold"))
        hdr.pack(pady=(14, 2))
        ttk.Label(self, text="ATI path-swap · enemies / pickups · no RNC", foreground="#aaaaaa").pack()

        # --- Source ---
        src_f = ttk.LabelFrame(self, text=" Levels source folder ")
        src_f.pack(fill=tk.X, **pad)
        self.src_var = tk.StringVar()
        ttk.Entry(src_f, textvariable=self.src_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=8)
        ttk.Button(src_f, text="Browse…", command=self._browse_src).pack(side=tk.RIGHT, padx=8, pady=8)

        # --- Output ---
        out_f = ttk.LabelFrame(self, text=" Output folder (must be OUTSIDE source) ")
        out_f.pack(fill=tk.X, **pad)
        self.out_var = tk.StringVar()
        ttk.Entry(out_f, textvariable=self.out_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=8)
        ttk.Button(out_f, text="Browse…", command=self._browse_out).pack(side=tk.RIGHT, padx=8, pady=8)
        ttk.Label(
            out_f,
            text="Example: C:\\GOG\\Turok4\\shuffled_enemies   — never inside data\\levels",
            foreground="#cc9966",
        ).pack(anchor=tk.W, padx=8, pady=(0, 6))

        # --- Mode ---
        mode_f = ttk.LabelFrame(self, text=" What to shuffle ")
        mode_f.pack(fill=tk.X, **pad)
        self.mode = tk.StringVar(value="enemies")
        for val, label in (
            ("enemies", "Enemies only"),
            ("pickups", "Pickups only (health / ammo / weapons)"),
            ("all", "Enemies + pickups"),
        ):
            ttk.Radiobutton(mode_f, text=label, variable=self.mode, value=val).pack(anchor=tk.W, padx=12, pady=3)

        # --- Enemy pool (crash isolation) ---
        pool_f = ttk.LabelFrame(self, text=" Enemy pool (if shuffling enemies) ")
        pool_f.pack(fill=tk.X, **pad)
        self.pool = tk.StringVar(value="safe")
        for val, label in (
            ("safe", "Safe — ground troops only (recommended, fewer freezes)"),
            ("ground", "Ground only"),
            ("vehicle", "Vehicles only (gliders, tanks, mines…)"),
            ("large_dino", "Large dinosaurs only"),
            ("all", "Everything (may freeze more)"),
        ):
            ttk.Radiobutton(pool_f, text=label, variable=self.pool, value=val).pack(anchor=tk.W, padx=12, pady=2)

        # --- Seed ---
        seed_f = ttk.Frame(self)
        seed_f.pack(fill=tk.X, **pad)
        ttk.Label(seed_f, text="Seed:").pack(side=tk.LEFT, padx=(4, 6))
        self.seed_var = tk.StringVar()
        ttk.Entry(seed_f, textvariable=self.seed_var, width=14).pack(side=tk.LEFT)
        ttk.Button(seed_f, text="Random", command=self._rand_seed).pack(side=tk.LEFT, padx=8)
        ttk.Label(seed_f, text="(blank = random)", foreground="#888888").pack(side=tk.LEFT)

        # --- Run ---
        ttk.Button(self, text="Generate", style="Accent.TButton", command=self._run).pack(fill=tk.X, padx=12, pady=10)

        # --- Log ---
        log_f = ttk.LabelFrame(self, text=" Log ")
        log_f.pack(fill=tk.BOTH, expand=True, **pad)
        self.log = tk.Text(log_f, height=12, bg="#1e1e1e", fg="#dddddd", insertbackground="white",
                           font=("Consolas", 10), wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        sys.stdout = TextRedirector(self.log)
        sys.stderr = TextRedirector(self.log)

        self._log("Pick the levels folder (contains pod-01-…, pod-02-…, pod-03-…).\n")
        self._log("Pick an output folder OUTSIDE data\\levels.\n")
        self._log("Then Generate.\n")

    def _log(self, msg: str) -> None:
        self.log.insert(tk.END, msg)
        self.log.see(tk.END)

    def _rand_seed(self) -> None:
        self.seed_var.set(str(random.randint(100000, 999999)))

    def _browse_src(self) -> None:
        d = filedialog.askdirectory(title="Select levels folder (parent of pod-01 / pod-02 / pod-03)")
        if d:
            self.src_var.set(d)
            # Suggest a safe default output next to GOG\Turok4 if path looks right
            src = Path(d)
            if self.out_var.get().strip() == "":
                # Prefer parent of levels → parent of data → Turok4\shuffled
                guess = src
                for _ in range(3):
                    if guess.name.lower() in ("levels", "data"):
                        guess = guess.parent
                        continue
                    break
                suggested = guess / "shuffled_enemies"
                self.out_var.set(str(suggested))

    def _browse_out(self) -> None:
        d = filedialog.askdirectory(title="Select OUTPUT folder (outside levels)")
        if d:
            self.out_var.set(d)

    def _run(self) -> None:
        src_s = self.src_var.get().strip()
        out_s = self.out_var.get().strip()
        if not src_s:
            messagebox.showerror("Missing source", "Select the levels source folder.")
            return
        if not out_s:
            messagebox.showerror("Missing output", "Select an output folder outside the source.")
            return

        src = Path(src_s).resolve()
        out = Path(out_s).resolve()

        if not src.is_dir():
            messagebox.showerror("Bad source", f"Not a folder:\n{src}")
            return

        # Hard block nested output
        try:
            out.relative_to(src)
            messagebox.showerror(
                "Unsafe output path",
                "Output is inside the source tree — that caused the infinite out_enemies folders.\n\n"
                f"Source: {src}\nOutput: {out}\n\n"
                "Choose a folder outside data\\levels, e.g.\n"
                "  C:\\GOG\\Turok4\\shuffled_enemies",
            )
            return
        except ValueError:
            pass

        seed_raw = self.seed_var.get().strip()
        seed = int(seed_raw) if seed_raw.isdigit() else random.randint(100000, 999999)
        self.seed_var.set(str(seed))
        mode = self.mode.get()

        self._log(f"\n--- mode={mode} seed={seed} ---\n")
        self._log(f"src={src}\n")
        self._log(f"out={out}\n")
        self.update_idletasks()

        try:
            pool_raw = self.pool.get()
            pool = None if pool_raw == "all" else pool_raw
            if mode == "enemies":
                te_tool.shuffle_category(src, te_tool.ENEMY_CATS, seed, out, "enemies", enemy_pool=pool)
            elif mode == "pickups":
                te_tool.shuffle_category(src, te_tool.PICKUP_CATS, seed, out, "pickups")
            else:
                slots_e = te_tool.collect_slots(src, te_tool.ENEMY_CATS, enemy_pool=pool)
                slots_p = te_tool.collect_slots(src, te_tool.PICKUP_CATS)
                from collections import defaultdict
                import random as _r

                rng = _r.Random(seed)
                by_file = defaultdict(list)

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
                te_tool._ensure_out_outside_src(src, out)
                out.mkdir(parents=True, exist_ok=True)
                n = te_tool.apply_path_replacements(by_file, out, src)
                te_tool.copy_sidecar_files(src, out)
                print(f"shuffle-all seed={seed}: enemies={len(slots_e)} pickups={len(slots_p)}")
                print(f"  path rewrites={n}  output={out}")

            messagebox.showinfo("Done", f"Finished.\n\nSeed: {seed}\nOutput:\n{out}")
        except SystemExit as e:
            messagebox.showerror("Blocked", str(e))
        except Exception as e:
            self._log(f"ERROR: {e}\n")
            messagebox.showerror("Failed", str(e))


def main() -> None:
    app = EvolutionGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
