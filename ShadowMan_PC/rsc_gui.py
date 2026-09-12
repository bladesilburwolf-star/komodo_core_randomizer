#!/usr/bin/env python3
"""
Shadow Man (Original PC) Randomizer GUI
Front-end for rsc_tool.py — exposes features already in the backend.
"""
import os
import sys
import random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

try:
    import rsc_tool
except ImportError:
    messagebox.showerror("Error", "Could not find 'rsc_tool.py' in the same directory.")
    sys.exit(1)


class TextRedirector:
    def __init__(self, widget):
        self.widget = widget
    def write(self, s):
        self.widget.insert(tk.END, s)
        self.widget.see(tk.END)
    def flush(self):
        pass


class ShadowManRandomizerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Shadow Man (Original PC) — Randomizer")
        self.geometry("920x720")
        self.minsize(780, 560)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self._configure_styles()
        self._create_widgets()

    def _configure_styles(self):
        dark_bg, dark_fg, entry_bg, accent = "#2b2b2b", "#ffffff", "#3c3f41", "#4a6ea9"
        self.configure(bg=dark_bg)
        self.style.configure(".", background=dark_bg, foreground=dark_fg, fieldbackground=entry_bg)
        self.style.configure("TNotebook", background=dark_bg, tabmargins=[2, 5, 2, 0])
        self.style.configure("TNotebook.Tab", background="#3c3f41", foreground=dark_fg, padding=[10, 5])
        self.style.map("TNotebook.Tab", background=[("selected", accent)])
        self.style.configure("TButton", background="#3c3f41", foreground=dark_fg, borderwidth=1)
        self.style.map("TButton", background=[("active", accent)])
        self.style.configure("Treeview", background="#3c3f41", foreground=dark_fg,
                             fieldbackground="#3c3f41", rowheight=22)
        self.style.configure("Treeview.Heading", background=accent, foreground=dark_fg)
        self.style.configure("TLabelframe", background=dark_bg, foreground=dark_fg)
        self.style.configure("TLabelframe.Label", background=dark_bg, foreground=dark_fg)

    def _create_widgets(self):
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tabs = [
            (" Multi-Shuffle ", self._build_multishuffle_tab),
            (" RSC Inspector ", self._build_rsc_inspector_tab),
            (" Junk Generator ", self._build_junk_tab),
            (" Spoiler / Summary ", self._build_spoiler_tab),
            (" Enemies ", self._build_enemy_tab),
            (" Barrels / Govi ", self._build_zelda_tab),
            (" Cosmetics ", self._build_cosmetic_tab),
            (" Cheats ", self._build_cheats_tab),
        ]
        for title, builder in tabs:
            frame = ttk.Frame(nb)
            nb.add(frame, text=title)
            builder(frame)

    # ------------------------------------------------------------------ helpers
    def _browse_dir(self, entry):
        d = filedialog.askdirectory()
        if d:
            entry.delete(0, tk.END)
            entry.insert(0, d)

    def _browse_file(self, entry, pattern="*.*"):
        f = filedialog.askopenfilename(filetypes=[("Files", pattern), ("All", "*.*")])
        if f:
            entry.delete(0, tk.END)
            entry.insert(0, f)

    def _log_to(self, widget, text):
        widget.insert(tk.END, text + "\n")
        widget.see(tk.END)

    # ==================================================================
    # Tab 1: Multi-Shuffle
    # ==================================================================
    def _build_multishuffle_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Levels / data root:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.ms_dir = ttk.Entry(frame, width=55)
        self.ms_dir.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=4)
        ttk.Button(frame, text="Browse…", command=lambda: self._browse_dir(self.ms_dir)).grid(row=0, column=2, pady=4)

        ttk.Label(frame, text="Output folder:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ms_out = ttk.Entry(frame, width=55)
        self.ms_out.insert(0, "shuffled_output")
        self.ms_out.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=4)

        opts = ttk.Frame(frame)
        opts.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=8)
        ttk.Label(opts, text="Seed:").pack(side=tk.LEFT)
        self.ms_seed = ttk.Entry(opts, width=12)
        self.ms_seed.insert(0, str(random.randint(100000, 999999)))
        self.ms_seed.pack(side=tk.LEFT, padx=5)
        ttk.Button(opts, text="Randomize", command=self._new_seed).pack(side=tk.LEFT, padx=5)
        ttk.Label(opts, text="Junk count:").pack(side=tk.LEFT, padx=(20, 5))
        self.ms_junk = ttk.Entry(opts, width=6)
        self.ms_junk.insert(0, "5")
        self.ms_junk.pack(side=tk.LEFT)

        ttk.Label(frame, text="Starting items (comma-separated):").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ms_start = ttk.Entry(frame, width=55)
        self.ms_start.insert(0, "")
        self.ms_start.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=4)
        ttk.Label(frame, text="e.g. poigne, baton, shotgun").grid(row=3, column=2, sticky=tk.W)

        btns = ttk.Frame(frame)
        btns.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=10)
        ttk.Button(btns, text="Scan Summary", command=self._ms_summary).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="List Startable Items", command=self._ms_list_startables).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Run Multi-Shuffle", command=self._ms_run).pack(side=tk.LEFT, padx=4)

        ttk.Label(frame, text="Log:").grid(row=5, column=0, sticky=tk.W)
        self.ms_log = tk.Text(frame, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9), height=18)
        self.ms_log.grid(row=6, column=0, columnspan=3, sticky=tk.NSEW, pady=4)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.ms_log.yview)
        sb.grid(row=6, column=3, sticky=tk.NS)
        self.ms_log.config(yscrollcommand=sb.set)

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)

    def _new_seed(self):
        self.ms_seed.delete(0, tk.END)
        self.ms_seed.insert(0, str(random.randint(100000, 999999)))

    def _ms_summary(self):
        root = self.ms_dir.get().strip()
        if not root or not Path(root).is_dir():
            messagebox.showerror("Error", "Select a valid data directory.")
            return
        self.ms_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.ms_log)
        try:
            class A: pass
            a = A(); a.root = root
            rsc_tool.cmd_summary(a)
        except Exception as e:
            self._log_to(self.ms_log, f"ERROR: {e}")
        finally:
            sys.stdout = old

    def _ms_list_startables(self):
        self.ms_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.ms_log)
        try:
            rsc_tool.cmd_list_startables(None)
        finally:
            sys.stdout = old

    def _ms_run(self):
        root = self.ms_dir.get().strip()
        if not root or not Path(root).is_dir():
            messagebox.showerror("Error", "Select a valid data directory.")
            return
        try:
            seed = int(self.ms_seed.get().strip() or 42)
            junk = int(self.ms_junk.get().strip() or 0)
        except ValueError:
            messagebox.showerror("Error", "Seed and junk must be integers.")
            return
        start_raw = self.ms_start.get().strip()
        start = [x.strip() for x in start_raw.split(",") if x.strip()] if start_raw else []
        out = self.ms_out.get().strip() or f"shuffled_seed{seed}"

        self.ms_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.ms_log)
        try:
            class A: pass
            a = A()
            a.dirs = [root]
            a.seed = seed
            a.junk = junk
            a.start = start
            a.output = out
            rsc_tool.cmd_multishuffle(a)
            messagebox.showinfo("Done", f"Shuffle complete → {out}")
        except Exception as e:
            self._log_to(self.ms_log, f"\nERROR: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            sys.stdout = old

    # ==================================================================
    # Tab 2: RSC Inspector (+ swap)
    # ==================================================================
    def _build_rsc_inspector_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, pady=4)
        ttk.Label(top, text="quest.rsc:").pack(side=tk.LEFT, padx=4)
        self.insp_path = ttk.Entry(top)
        self.insp_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(top, text="Browse…", command=lambda: self._browse_file(self.insp_path, "*.rsc")).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Load", command=self._insp_load).pack(side=tk.LEFT, padx=2)

        cols = ("offset", "name", "type")
        self.insp_tree = ttk.Treeview(frame, columns=cols, show="headings", height=18)
        self.insp_tree.heading("offset", text="Offset")
        self.insp_tree.heading("name", text="RSC Name")
        self.insp_tree.heading("type", text="Class")
        self.insp_tree.column("offset", width=90, anchor=tk.CENTER)
        self.insp_tree.column("name", width=360)
        self.insp_tree.column("type", width=110, anchor=tk.CENTER)
        self.insp_tree.pack(fill=tk.BOTH, expand=True, pady=8)
        self.insp_tree.bind("<<TreeviewSelect>>", self._insp_select)

        swap = ttk.Frame(frame)
        swap.pack(fill=tk.X, pady=4)
        ttk.Label(swap, text="Old:").pack(side=tk.LEFT)
        self.insp_old = ttk.Entry(swap, width=28)
        self.insp_old.pack(side=tk.LEFT, padx=4)
        ttk.Label(swap, text="New:").pack(side=tk.LEFT)
        self.insp_new = ttk.Entry(swap, width=28)
        self.insp_new.pack(side=tk.LEFT, padx=4)
        ttk.Button(swap, text="Swap in file", command=self._insp_swap).pack(side=tk.LEFT, padx=6)

    def _insp_load(self):
        p = Path(self.insp_path.get().strip())
        if not p.is_file():
            messagebox.showerror("Error", "Select a valid quest.rsc")
            return
        self.insp_tree.delete(*self.insp_tree.get_children())
        try:
            parsed = rsc_tool.parse_quest_rsc(p)
            for r in parsed["records"]:
                t = "Progression" if rsc_tool.is_progression(r["name"]) else (
                    "Junk" if rsc_tool.is_junk(r["name"]) else "Standard")
                self.insp_tree.insert("", tk.END, values=(f"0x{r['offset']:04x}", r["name"], t))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _insp_select(self, _evt):
        sel = self.insp_tree.selection()
        if sel:
            name = self.insp_tree.item(sel[0])["values"][1]
            self.insp_old.delete(0, tk.END)
            self.insp_old.insert(0, name)

    def _insp_swap(self):
        path = self.insp_path.get().strip()
        old, new = self.insp_old.get().strip(), self.insp_new.get().strip()
        if not path or not old or not new:
            messagebox.showerror("Error", "Need file, old name, and new name.")
            return
        class A: pass
        a = A(); a.rsc = path; a.old_name = old; a.new_name = new; a.output = None
        try:
            rsc_tool.cmd_swap(a)
            messagebox.showinfo("Done", f"Swapped {old} → {new}")
            self._insp_load()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ==================================================================
    # Tab 3: Junk Generator
    # ==================================================================
    def _build_junk_tab(self, parent):
        frame = ttk.Frame(parent, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Generate junk_invitems.dsc + junk_items.txt support files",
                  font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 12))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Count:").pack(side=tk.LEFT)
        self.junk_count = ttk.Spinbox(row, from_=1, to=100, width=8)
        self.junk_count.set(20)
        self.junk_count.pack(side=tk.LEFT, padx=6)

        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=4)
        ttk.Label(row2, text="Output folder:").pack(side=tk.LEFT)
        self.junk_out = ttk.Entry(row2, width=40)
        self.junk_out.insert(0, "junk_support")
        self.junk_out.pack(side=tk.LEFT, padx=6)

        ttk.Button(frame, text="Generate", command=self._junk_gen).pack(anchor=tk.W, pady=12)

    def _junk_gen(self):
        try:
            n = int(self.junk_count.get())
            out = Path(self.junk_out.get().strip() or "junk_support")
            rsc_tool._write_junk_support(out, count=n)
            messagebox.showinfo("Done", f"Wrote {n} junk defs → {out.resolve()}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ==================================================================
    # Tab 4: Spoiler / Summary / Inventory
    # ==================================================================
    def _build_spoiler_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, pady=4)
        ttk.Label(top, text="Data root:").pack(side=tk.LEFT, padx=4)
        self.sp_dir = ttk.Entry(top)
        self.sp_dir.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(top, text="Browse…", command=lambda: self._browse_dir(self.sp_dir)).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Summary", command=self._sp_summary).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Full Inventory Table", command=self._sp_inventory).pack(side=tk.LEFT, padx=2)

        self.sp_text = tk.Text(frame, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9))
        self.sp_text.pack(fill=tk.BOTH, expand=True, pady=8)

    def _sp_summary(self):
        root = self.sp_dir.get().strip()
        if not root or not Path(root).is_dir():
            messagebox.showerror("Error", "Select a valid directory.")
            return
        self.sp_text.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.sp_text)
        try:
            class A: pass
            a = A(); a.root = root
            rsc_tool.cmd_summary(a)
        finally:
            sys.stdout = old

    def _sp_inventory(self):
        root = self.sp_dir.get().strip()
        if not root or not Path(root).is_dir():
            messagebox.showerror("Error", "Select a valid directory.")
            return
        self.sp_text.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.sp_text)
        try:
            class A: pass
            a = A(); a.root = root
            rsc_tool.cmd_inventory(a)
        finally:
            sys.stdout = old

    # ==================================================================
    # Tab 5: Enemy Scan
    # ==================================================================
    def _build_enemy_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Data root (or single enemies.rsc):").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.en_dir = ttk.Entry(frame, width=50)
        self.en_dir.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=4)
        ttk.Button(frame, text="Browse…", command=lambda: self._browse_dir(self.en_dir)).grid(row=0, column=2, pady=4)

        opts = ttk.Frame(frame)
        opts.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=6)
        ttk.Label(opts, text="Seed:").pack(side=tk.LEFT)
        self.en_seed = ttk.Entry(opts, width=10)
        self.en_seed.insert(0, str(random.randint(1000, 99999)))
        self.en_seed.pack(side=tk.LEFT, padx=4)
        self.en_cross = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Cross-area pool", variable=self.en_cross).pack(side=tk.LEFT, padx=12)
        ttk.Label(opts, text="Output:").pack(side=tk.LEFT)
        self.en_out = ttk.Entry(opts, width=18)
        self.en_out.insert(0, "enemies_out")
        self.en_out.pack(side=tk.LEFT, padx=4)

        btns = ttk.Frame(frame)
        btns.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=6)
        ttk.Button(btns, text="List Enemies", command=self._en_list).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Shuffle Baddies", command=self._en_shuffle).pack(side=tk.LEFT, padx=4)

        self.en_log = tk.Text(frame, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9), height=18)
        self.en_log.grid(row=3, column=0, columnspan=3, sticky=tk.NSEW, pady=6)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

    def _en_list(self):
        root = self.en_dir.get().strip()
        if not root:
            messagebox.showerror("Error", "Select data root or enemies.rsc")
            return
        self.en_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.en_log)
        try:
            class A: pass
            a = A(); a.dirs = [root]
            rsc_tool.cmd_list_enemies(a)
        except Exception as e:
            self._log_to(self.en_log, f"ERROR: {e}")
        finally:
            sys.stdout = old

    def _en_shuffle(self):
        root = self.en_dir.get().strip()
        if not root:
            messagebox.showerror("Error", "Select data root")
            return
        try:
            seed = int(self.en_seed.get().strip() or 42)
        except ValueError:
            messagebox.showerror("Error", "Bad seed")
            return
        self.en_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.en_log)
        try:
            class A: pass
            a = A()
            a.dirs = [root]
            a.seed = seed
            a.cross = self.en_cross.get()
            a.output = self.en_out.get().strip() or f"enemies_seed{seed}"
            rsc_tool.cmd_enemy_shuffle(a)
            messagebox.showinfo("Done", f"Enemy shuffle → {a.output}")
        except Exception as e:
            self._log_to(self.en_log, f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            sys.stdout = old

    # ==================================================================
    # Tab 6: Pots & Drops
    # ==================================================================
    def _build_zelda_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Data root (quest.rsc barrels/govi/crates):").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.zd_dir = ttk.Entry(frame, width=50)
        self.zd_dir.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=4)
        ttk.Button(frame, text="Browse…", command=lambda: self._browse_dir(self.zd_dir)).grid(row=0, column=2, pady=4)

        opts = ttk.Frame(frame)
        opts.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=6)
        ttk.Label(opts, text="Seed:").pack(side=tk.LEFT)
        self.zd_seed = ttk.Entry(opts, width=10)
        self.zd_seed.insert(0, str(random.randint(1000, 99999)))
        self.zd_seed.pack(side=tk.LEFT, padx=4)
        self.zd_cross = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Cross-area pool", variable=self.zd_cross).pack(side=tk.LEFT, padx=12)
        ttk.Label(opts, text="Output:").pack(side=tk.LEFT)
        self.zd_out = ttk.Entry(opts, width=18)
        self.zd_out.insert(0, "barrels_out")
        self.zd_out.pack(side=tk.LEFT, padx=4)

        btns = ttk.Frame(frame)
        btns.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=6)
        ttk.Button(btns, text="Shuffle Barrels / Govi", command=self._zd_shuffle).pack(side=tk.LEFT, padx=4)

        self.zd_log = tk.Text(frame, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9), height=18)
        self.zd_log.grid(row=3, column=0, columnspan=3, sticky=tk.NSEW, pady=6)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

    def _zd_shuffle(self):
        root = self.zd_dir.get().strip()
        if not root:
            messagebox.showerror("Error", "Select data root")
            return
        try:
            seed = int(self.zd_seed.get().strip() or 42)
        except ValueError:
            messagebox.showerror("Error", "Bad seed")
            return
        self.zd_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.zd_log)
        try:
            class A: pass
            a = A()
            a.dirs = [root]
            a.seed = seed
            a.cross = self.zd_cross.get()
            a.output = self.zd_out.get().strip() or f"barrels_seed{seed}"
            rsc_tool.cmd_barrel_shuffle(a)
            messagebox.showinfo("Done", f"Barrel shuffle → {a.output}")
        except Exception as e:
            self._log_to(self.zd_log, f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            sys.stdout = old

    # ==================================================================
    # Tab 7: Cosmetics (real TGA hue)
    # ==================================================================
    def _build_cosmetic_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Hue-shifts blood/flame TGA textures in place. Work on a copy of your data.",
                  font=("Segoe UI", 9)).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))

        ttk.Label(frame, text="Game data root:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.cos_dir = ttk.Entry(frame, width=50)
        self.cos_dir.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=4)
        ttk.Button(frame, text="Browse…", command=lambda: self._browse_dir(self.cos_dir)).grid(row=1, column=2, pady=4)

        blood_opts = list(rsc_tool.COLOR_PRESETS.get("Blood", {}).keys())
        if "Randomized Chaos" not in blood_opts:
            blood_opts.append("Randomized Chaos")
        flame_opts = list(rsc_tool.COLOR_PRESETS.get("Flames", {}).keys())
        if "Randomized Chaos" not in flame_opts:
            flame_opts.append("Randomized Chaos")

        ttk.Label(frame, text="Blood preset:").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.cos_blood = ttk.Combobox(frame, values=blood_opts, width=28)
        self.cos_blood.current(0)
        self.cos_blood.grid(row=2, column=1, sticky=tk.W, padx=5, pady=4)

        ttk.Label(frame, text="Flames preset:").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.cos_flame = ttk.Combobox(frame, values=flame_opts, width=28)
        self.cos_flame.current(0)
        self.cos_flame.grid(row=3, column=1, sticky=tk.W, padx=5, pady=4)

        ttk.Label(frame, text="Seed (for chaos):").grid(row=4, column=0, sticky=tk.W, pady=4)
        self.cos_seed = ttk.Entry(frame, width=14)
        self.cos_seed.insert(0, str(random.randint(1, 99999)))
        self.cos_seed.grid(row=4, column=1, sticky=tk.W, padx=5, pady=4)

        ttk.Button(frame, text="Apply Cosmetics", command=self._cos_apply).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, pady=16)

        self.cos_log = tk.Text(frame, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9), height=12)
        self.cos_log.grid(row=6, column=0, columnspan=3, sticky=tk.NSEW, pady=4)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)

    def _cos_apply(self):
        root = self.cos_dir.get().strip()
        if not root or not Path(root).is_dir():
            messagebox.showerror("Error", "Select a valid data directory (use a copy!).")
            return
        try:
            seed = int(self.cos_seed.get().strip() or 0)
        except ValueError:
            seed = 0
        blood = self.cos_blood.get()
        flame = self.cos_flame.get()
        self.cos_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.cos_log)
        try:
            n = rsc_tool.randomize_all_palettes(root, blood, flame, seed=seed)
            messagebox.showinfo("Done", f"Modified {n} TGA files.\nBlood={blood}\nFlames={flame}")
        except Exception as e:
            self._log_to(self.cos_log, f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            sys.stdout = old

    # ==================================================================
    # Tab 8: Cheats (experimental stubs)
    # ==================================================================
    def _build_cheats_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Uses the game's real Acclaim debug menu scripts (not EXE byte patches).",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(0, 8))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Game root (or menus/english):").pack(side=tk.LEFT, padx=4)
        self.ch_root = ttk.Entry(row)
        self.ch_root.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row, text="Browse…", command=lambda: self._browse_dir(self.ch_root)).pack(side=tk.LEFT, padx=2)

        mode_row = ttk.Frame(frame)
        mode_row.pack(fill=tk.X, pady=8)
        ttk.Label(mode_row, text="Mode:").pack(side=tk.LEFT, padx=4)
        self.ch_mode = ttk.Combobox(mode_row, values=["merge", "full"], width=12, state="readonly")
        self.ch_mode.set("merge")
        self.ch_mode.pack(side=tk.LEFT, padx=4)
        ttk.Label(
            mode_row,
            text="merge = fill Secrets menu · full = swap in debug.msc",
        ).pack(side=tk.LEFT, padx=8)

        btns = ttk.Frame(frame)
        btns.pack(fill=tk.X, pady=8)
        ttk.Button(btns, text="Enable Debug / Cheats Menu", command=self._ch_enable).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Restore release.msc from backup", command=self._ch_restore).pack(side=tk.LEFT, padx=4)

        ttk.Label(
            frame,
            text="After merge, open Secrets in-game for: Invincibility, Infinite Ammo, Freeze AI, Level Select, Gads, Shadowmeters…",
            wraplength=700,
        ).pack(anchor=tk.W, pady=4)

        self.ch_log = tk.Text(frame, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9), height=14)
        self.ch_log.pack(fill=tk.BOTH, expand=True, pady=8)

    def _ch_enable(self):
        root = self.ch_root.get().strip()
        if not root:
            messagebox.showerror("Error", "Select game root or menus/english folder")
            return
        self.ch_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.ch_log)
        try:
            class A: pass
            a = A()
            a.root = root
            a.mode = self.ch_mode.get() or "merge"
            a.no_backup = False
            rsc_tool.cmd_enable_debug(a)
            messagebox.showinfo("Done", "Debug/cheat menus enabled.\nBackup saved as release.msc.bak")
        except Exception as e:
            self._log_to(self.ch_log, f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            sys.stdout = old

    def _ch_restore(self):
        root = self.ch_root.get().strip()
        if not root:
            messagebox.showerror("Error", "Select game root or menus/english folder")
            return
        self.ch_log.delete("1.0", tk.END)
        old = sys.stdout
        sys.stdout = TextRedirector(self.ch_log)
        try:
            class A: pass
            a = A(); a.root = root
            rsc_tool.cmd_restore_menu(a)
            messagebox.showinfo("Done", "release.msc restored from backup")
        except Exception as e:
            self._log_to(self.ch_log, f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            sys.stdout = old


if __name__ == "__main__":
    app = ShadowManRandomizerGUI()
    app.mainloop()
