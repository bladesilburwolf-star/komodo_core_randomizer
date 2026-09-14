#!/usr/bin/env python3
"""Turok 2 MP — Loadout / Attribute GUI."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import t2_loadout


class LoadoutGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Turok 2 — Loadout / Attributes")
        self.geometry("780x640")
        self.configure(bg="#2b2b2b")
        self.data = t2_loadout.template()
        self.path: Path | None = None
        style = ttk.Style(self)
        style.theme_use("clam")
        for k in (".", "TLabel", "TButton", "TLabelframe", "TLabelframe.Label", "TCheckbutton", "TEntry"):
            style.configure(k, background="#2b2b2b", foreground="#fff")
        style.configure("TButton", background="#3c3f41")
        style.configure("TNotebook", background="#2b2b2b")
        style.configure("TNotebook.Tab", background="#3c3f41", foreground="#fff")
        self._build()
        self._load_into_ui()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="Turok 2 Loadout Editor", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(top, text="New", command=self._new).pack(side="right", padx=2)
        ttk.Button(top, text="Open JSON…", command=self._open).pack(side="right", padx=2)
        ttk.Button(top, text="Save JSON…", command=self._save).pack(side="right", padx=2)
        ttk.Button(top, text="Export CFG…", command=self._export).pack(side="right", padx=2)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=6)

        # Global tab
        gtab = ttk.Frame(nb)
        nb.add(gtab, text="Global")
        self.g_vars = {}
        fields = [
            ("SpeedMultiplier", "float"),
            ("DamageMultiplier", "float"),
            ("NodeExpansion", "float"),
            ("ArenaHealth", "int"),
            ("ArenaWeapons", "str"),
            ("ArenaMaxAmmo", "bool"),
            ("EnemiesDropWeapons", "bool"),
            ("WeaponsRemain", "bool"),
            ("AllCharactersSame", "bool"),
        ]
        for i, (name, kind) in enumerate(fields):
            ttk.Label(gtab, text=name).grid(row=i, column=0, sticky="w", padx=8, pady=3)
            if kind == "bool":
                v = tk.BooleanVar()
                ttk.Checkbutton(gtab, variable=v).grid(row=i, column=1, sticky="w")
            else:
                v = tk.StringVar()
                ttk.Entry(gtab, textvariable=v, width=48).grid(row=i, column=1, sticky="we", padx=4)
            self.g_vars[name] = (kind, v)
        ttk.Label(
            gtab,
            text="ArenaWeapons: (all)  or  comma list e.g. Pistol,Shotgun,Nuke",
            foreground="#aaa",
        ).grid(row=len(fields), column=0, columnspan=2, sticky="w", padx=8, pady=8)

        pret = ttk.Frame(gtab)
        pret.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Label(pret, text="Preset:").pack(side="left")
        self.preset = tk.StringVar(value="vanilla")
        for name in ("vanilla", "glass_cannon", "tank", "speed", "pistols_only", "heavy"):
            ttk.Radiobutton(pret, text=name, variable=self.preset, value=name).pack(side="left", padx=4)
        ttk.Button(pret, text="Apply preset", command=self._preset).pack(side="left", padx=8)

        # Characters tab
        ctab = ttk.Frame(nb)
        nb.add(ctab, text="Characters")
        left = ttk.Frame(ctab)
        left.pack(side="left", fill="y", padx=8, pady=8)
        ttk.Label(left, text="Character").pack()
        self.char_list = tk.Listbox(left, height=16, bg="#1e1e1e", fg="#ddd", exportselection=False)
        self.char_list.pack()
        for name in t2_loadout.CHARACTERS:
            self.char_list.insert("end", name)
        self.char_list.bind("<<ListboxSelect>>", self._on_char)
        self.char_list.selection_set(0)

        right = ttk.Frame(ctab)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self.c_vars = {}
        for i, field in enumerate(("Attribs", "StartAmmo", "MaxAmmo")):
            ttk.Label(right, text=field).grid(row=i, column=0, sticky="w", pady=4)
            v = tk.StringVar()
            ttk.Entry(right, textvariable=v, width=40).grid(row=i, column=1, sticky="we", pady=4)
            self.c_vars[field] = v
        ttk.Label(
            right,
            text="Attribs/StartAmmo/MaxAmmo are string tokens the EXE parses (%s).\n"
            "Use 'default' until exact token grammar is mapped in-game.",
            foreground="#aaa",
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=12)

        # Weapons ref tab
        wtab = ttk.Frame(nb)
        nb.add(wtab, text="Weapons ref")
        txt = tk.Text(wtab, bg="#1e1e1e", fg="#ddd", font=("Consolas", 10))
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("end", "Known ArenaWeapons names (from Turok2MP.exe):\n\n")
        for w in t2_loadout.WEAPONS:
            txt.insert("end", f"  {w}\n")
        txt.insert("end", "\nCharacters:\n")
        for c in t2_loadout.CHARACTERS:
            txt.insert("end", f"  {c}\n")
        txt.configure(state="disabled")

        self.status = ttk.Label(self, text="New template", relief="sunken")
        self.status.pack(fill="x", side="bottom")

    def _load_into_ui(self) -> None:
        g = self.data.get("global", {})
        for name, (kind, var) in self.g_vars.items():
            val = g.get(name, "")
            if kind == "bool":
                var.set(bool(val))
            else:
                var.set(str(val))
        self._on_char()

    def _ui_to_data(self) -> None:
        g = self.data.setdefault("global", {})
        for name, (kind, var) in self.g_vars.items():
            if kind == "bool":
                g[name] = bool(var.get())
            elif kind == "float":
                try:
                    g[name] = float(var.get())
                except ValueError:
                    pass
            elif kind == "int":
                try:
                    g[name] = int(float(var.get()))
                except ValueError:
                    pass
            else:
                g[name] = var.get()
        # current character fields
        sel = self.char_list.curselection()
        if sel:
            name = t2_loadout.CHARACTERS[sel[0]]
            ch = self.data.setdefault("characters", {}).setdefault(name, {})
            for field, var in self.c_vars.items():
                ch[field] = var.get()

    def _on_char(self, _evt=None) -> None:
        # save previous? we save all on export; load selected into fields
        sel = self.char_list.curselection()
        if not sel:
            return
        name = t2_loadout.CHARACTERS[sel[0]]
        # stash previous selection by writing all listed — simple: write current fields to last_name
        ch = self.data.get("characters", {}).get(name, {})
        for field, var in self.c_vars.items():
            var.set(str(ch.get(field, "default")))

    def _new(self) -> None:
        self.data = t2_loadout.template()
        self.path = None
        self._load_into_ui()
        self.status.configure(text="New template")

    def _open(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("CFG", "*.cfg"), ("All", "*.*")])
        if not p:
            return
        path = Path(p)
        try:
            if path.suffix.lower() == ".cfg":
                self.data = t2_loadout.import_cfg(path.read_text(encoding="utf-8", errors="replace"))
            else:
                self.data = t2_loadout.load_json(path)
            self.path = path
            self._load_into_ui()
            self.status.configure(text=f"Loaded {path.name}")
        except Exception as e:
            messagebox.showerror("Open", str(e))

    def _save(self) -> None:
        self._ui_to_data()
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            t2_loadout.save_json(self.data, Path(p))
            self.path = Path(p)
            self.status.configure(text=f"Saved {p}")
        except Exception as e:
            messagebox.showerror("Save", str(e))

    def _export(self) -> None:
        self._ui_to_data()
        p = filedialog.asksaveasfilename(defaultextension=".cfg", initialfile="integrated.cfg")
        if not p:
            return
        try:
            Path(p).write_text(t2_loadout.export_cfg(self.data), encoding="utf-8")
            self.status.configure(text=f"Exported {p}")
            messagebox.showinfo(
                "Export",
                f"Wrote {p}\n\nTry as ./integrated.cfg beside Turok2MP.exe,\nor merge keys into your MP config.",
            )
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def _preset(self) -> None:
        try:
            self.data = t2_loadout.apply_preset(t2_loadout.template(), self.preset.get())
            self._load_into_ui()
            self.status.configure(text=f"Preset {self.preset.get()}")
        except Exception as e:
            messagebox.showerror("Preset", str(e))


if __name__ == "__main__":
    LoadoutGUI().mainloop()
