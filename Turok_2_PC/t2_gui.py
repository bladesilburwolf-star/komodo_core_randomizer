#!/usr/bin/env python3
"""
Turok 2: Seeds of Evil - Map & Spawn Modder GUI (Threaded)
Front-end for t2_tool.py
"""
from __future__ import annotations
import io
import struct
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import t2_tool


class Turok2ModderGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Turok 2: Seeds of Evil - LSS Mod Tool")
        self.geometry("720x550")
        self.minsize(600, 450)
        self.current_lss_path = None
        self._create_widgets()
        self._update_status("Ready. Select an .LSS file to begin.")

    def _create_widgets(self):
        file_frame = ttk.LabelFrame(self, text="Target File Selection", padding=10)
        file_frame.pack(fill="x", padx=10, pady=5)

        self.lbl_file_path = ttk.Label(file_frame, text="No file selected...", font=("Consolas", 9))
        self.lbl_file_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_browse = ttk.Button(file_frame, text="Browse .LSS", command=self._browse_file)
        self.btn_browse.pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_info = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_info, text="File Information")
        self._build_info_tab()

        self.tab_spawns = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_spawns, text="Spawn & Warp Modder")
        self._build_spawns_tab()

        self.tab_items = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_items, text="Item & Section 5")
        self._build_items_tab()

        self.lbl_status = ttk.Label(self, text="", relief="sunken", anchor="w", padding=4)
        self.lbl_status.pack(fill="x", side="bottom")

    def _set_ui_busy(self, busy: bool):
        state = "disabled" if busy else "!disabled"
        self.notebook.state([state])
        self.btn_browse.state([state])
        self._update_status("Processing... Please wait." if busy else "Ready.")

    def _run_task(self, task_func, success_msg=None, error_title="Error"):
        self._set_ui_busy(True)

        def worker():
            try:
                task_func()
                if success_msg:
                    self.after(0, lambda: messagebox.showinfo("Success", success_msg))
            except Exception as ex:
                self.after(0, lambda e=ex: messagebox.showerror(error_title, str(e)))
            finally:
                self.after(0, lambda: self._set_ui_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _build_info_tab(self):
        ttk.Button(self.tab_info, text="Refresh Section Info", command=self._load_info).pack(
            anchor="w", pady=(0, 5)
        )
        self.txt_info = tk.Text(self.tab_info, font=("Consolas", 9), wrap="none")
        scroll_y = ttk.Scrollbar(self.tab_info, orient="vertical", command=self.txt_info.yview)
        scroll_x = ttk.Scrollbar(self.tab_info, orient="horizontal", command=self.txt_info.xview)
        self.txt_info.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self.txt_info.pack(fill="both", expand=True)

    def _build_spawns_tab(self):
        opt_frame = ttk.LabelFrame(self.tab_spawns, text="Randomizer Options", padding=10)
        opt_frame.pack(fill="x", pady=5)
        ttk.Label(opt_frame, text="RNG Seed (optional):").grid(row=0, column=0, sticky="w", padx=5)
        self.ent_spawn_seed = ttk.Entry(opt_frame, width=15)
        self.ent_spawn_seed.grid(row=0, column=1, sticky="w", padx=5)

        btn_frame = ttk.Frame(self.tab_spawns, padding=5)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Scan Spawns", command=self._list_spawns).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Shuffle & Save Spawns", command=self._shuffle_spawns).pack(
            side="left", padx=5
        )

        self.txt_spawns = tk.Text(self.tab_spawns, font=("Consolas", 9), wrap="none")
        scroll_y = ttk.Scrollbar(self.tab_spawns, orient="vertical", command=self.txt_spawns.yview)
        self.txt_spawns.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side="right", fill="y")
        self.txt_spawns.pack(fill="both", expand=True)

    def _build_items_tab(self):
        opt_frame = ttk.LabelFrame(self.tab_items, text="Randomizer Options", padding=10)
        opt_frame.pack(fill="x", pady=5)
        ttk.Label(opt_frame, text="RNG Seed (optional):").grid(row=0, column=0, sticky="w", padx=5)
        self.ent_item_seed = ttk.Entry(opt_frame, width=15)
        self.ent_item_seed.grid(row=0, column=1, sticky="w", padx=5)

        btn_frame = ttk.Frame(self.tab_items, padding=5)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="List Weapon Hits", command=self._list_weapons).pack(
            side="left", padx=2
        )
        ttk.Button(btn_frame, text="Shuffle Weapons", command=self._shuffle_weapons).pack(
            side="left", padx=2
        )
        ttk.Button(btn_frame, text="Hybrid: Spawns+Weapons", command=self._shuffle_all).pack(
            side="left", padx=2
        )
        ttk.Button(btn_frame, text="Dry-Run Scan Sec 5", command=self._scan_sec5_dryrun).pack(
            side="left", padx=2
        )

        self.txt_items = tk.Text(self.tab_items, font=("Consolas", 9), wrap="none")
        scroll_y = ttk.Scrollbar(self.tab_items, orient="vertical", command=self.txt_items.yview)
        self.txt_items.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side="right", fill="y")
        self.txt_items.pack(fill="both", expand=True)

    def _browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Turok 2 .LSS File",
            filetypes=[("LSS Files", "*.lss"), ("All Files", "*.*")],
        )
        if file_path:
            self.current_lss_path = Path(file_path)
            self.lbl_file_path.config(text=str(self.current_lss_path))
            self._load_info()

    def _get_seed(self, entry_widget) -> int | None:
        val = entry_widget.get().strip()
        if not val:
            return None
        try:
            return int(val)
        except ValueError:
            messagebox.showerror("Invalid Input", "Seed must be a valid integer.")
            return None

    def _update_status(self, text: str):
        self.lbl_status.config(text=text)

    def _load_info(self):
        if not self.current_lss_path:
            return
        self.txt_info.delete("1.0", tk.END)
        try:
            data = self.current_lss_path.read_bytes()
            count, header_size, ends = t2_tool.parse_lss_header(data)
            ranges = t2_tool.section_ranges(header_size, ends)
            out = [
                f"File          : {self.current_lss_path.name}",
                f"Size          : {len(data):,} bytes",
                f"Section count : {count}",
                f"Header size   : {header_size} (0x{header_size:x})",
                f"RNC Unpacker  : {'pure Python (vendored rnc)' if t2_tool._RNC_AVAILABLE else 'NOT available'}",
                "",
                f"{'Idx':>3}  {'Name':<16}  {'Start':>10}  {'End':>10}  {'Size':>10}",
                "-" * 58,
            ]
            for i, (start, end) in enumerate(ranges):
                name = t2_tool.SECTION_NAMES.get(i, "?")
                out.append(f"{i:3d}  {name:<16}  0x{start:08x}  0x{end:08x}  {end - start:10,}")
            self.txt_info.insert(tk.END, "\n".join(out))
            self._update_status(f"Loaded info for {self.current_lss_path.name}")
        except Exception as e:
            messagebox.showerror("Error Reading LSS", str(e))

    def _list_spawns(self):
        if not self.current_lss_path:
            messagebox.showwarning("Warning", "Please select an .LSS file first.")
            return
        self.txt_spawns.delete("1.0", tk.END)
        try:
            data = self.current_lss_path.read_bytes()
            sec, _, _ = t2_tool.get_section(data, t2_tool.WARPS_SECTION)
            strict = t2_tool.find_position_records(sec)
            out = [
                f"Strict positions: {len(strict)}",
                "",
                f"{'#':>4}  {'Offset':>8}  {'X':>10}  {'Y':>10}  {'Z':>10}",
                "-" * 50,
            ]
            for i, (off, block) in enumerate(strict):
                x, y, z, rot = struct.unpack_from("<ffff", block, 0)
                out.append(f"{i:4d}  0x{off:04x}  {x:10.2f}  {y:10.2f}  {z:10.2f}")
            self.txt_spawns.insert(tk.END, "\n".join(out))
            self._update_status(f"Found {len(strict)} spawns.")
        except Exception as e:
            messagebox.showerror("Error Scanning Spawns", str(e))

    def _shuffle_spawns(self):
        if not self.current_lss_path:
            messagebox.showwarning("Warning", "Please select an .LSS file first.")
            return
        seed = self._get_seed(self.ent_spawn_seed)
        save_path = filedialog.asksaveasfilename(
            title="Save Shuffled LSS As...",
            defaultextension=".lss",
            initialfile=f"{self.current_lss_path.stem}_spawns.lss",
            filetypes=[("LSS Files", "*.lss")],
        )
        if not save_path:
            return

        def task():
            t2_tool.cmd_shuffle_spawns(self.current_lss_path, seed, Path(save_path))

        self._run_task(
            task,
            f"Spawns shuffled successfully!\n\nSaved to:\n{save_path}",
            "Error Shuffling Spawns",
        )

    def _scan_sec5_dryrun(self):
        if not self.current_lss_path:
            messagebox.showwarning("Warning", "Please select an .LSS file first.")
            return
        self.txt_items.delete("1.0", tk.END)
        self._set_ui_busy(True)

        def worker():
            buffer = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = buffer
            try:
                t2_tool.cmd_scan_sec5_dryrun(self.current_lss_path)
                output = buffer.getvalue()
                self.after(0, lambda: self.txt_items.insert(tk.END, output))
                self.after(
                    0,
                    lambda: self._update_status(
                        f"Completed Section 5 scan for {self.current_lss_path.name}"
                    ),
                )
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error Scanning Section 5", str(e)))
            finally:
                sys.stdout = old_stdout
                self.after(0, lambda: self._set_ui_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _list_weapons(self):
        if not self.current_lss_path:
            messagebox.showwarning("No File", "Load an LSS first.")
            return
        self._update_status("Scanning weapon model IDs...")
        def worker():
            try:
                hits = t2_tool.find_weapon_model_hits(self.current_lss_path.read_bytes())
                from collections import Counter
                by = Counter(h["name"] for h in hits)
                lines = [f"Weapon model-ID hits: {len(hits)}", ""]
                for name, c in by.most_common():
                    lines.append(f"  {c:4d}  {name}")
                lines.append("")
                lines.append("First 25:")
                for h in hits[:25]:
                    lines.append(f"  map={h['map']:3d} +0x{h['local_off']:04x}  {h['name']}")
                text = "\n".join(lines)
                self.after(0, lambda: (self.txt_items.delete("1.0", "end"),
                                       self.txt_items.insert("1.0", text),
                                       self._update_status(f"{len(hits)} weapon hits")))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _shuffle_weapons(self):
        if not self.current_lss_path:
            messagebox.showwarning("No File", "Load an LSS first.")
            return
        seed = self._get_seed(self.ent_item_seed)
        save_path = filedialog.asksaveasfilename(
            title="Save Weapon-Shuffle LSS As...",
            defaultextension=".lss",
            filetypes=[("LSS files", "*.lss"), ("All", "*.*")],
            initialfile=f"{self.current_lss_path.stem}_weapons_seed{seed or 'x'}.lss",
        )
        if not save_path:
            return
        def task():
            t2_tool.cmd_shuffle_weapons(self.current_lss_path, seed, Path(save_path))
        self._run_task(
            task,
            f"Weapon model IDs shuffled (experimental).\n\nSaved to:\n{save_path}",
            "Error Shuffling Weapons",
        )


    def _shuffle_items(self):
        if not self.current_lss_path:
            messagebox.showwarning("Warning", "Please select an .LSS file first.")
            return
        seed = self._get_seed(self.ent_item_seed)
        save_path = filedialog.asksaveasfilename(
            title="Save Secondary-Shuffled LSS As...",
            defaultextension=".lss",
            initialfile=f"{self.current_lss_path.stem}_items.lss",
            filetypes=[("LSS Files", "*.lss")],
        )
        if not save_path:
            return

        def task():
            t2_tool.cmd_shuffle_items(self.current_lss_path, seed, Path(save_path))

        self._run_task(
            task,
            f"Secondary positions shuffled.\n(Real pickup types need verified IDs.)\n\nSaved to:\n{save_path}",
            "Error Shuffling Items",
        )

    def _shuffle_all(self):
        if not self.current_lss_path:
            messagebox.showwarning("Warning", "Please select an .LSS file first.")
            return
        seed = self._get_seed(self.ent_item_seed)
        save_path = filedialog.asksaveasfilename(
            title="Save Hybrid Randomizer LSS As...",
            defaultextension=".lss",
            initialfile=f"{self.current_lss_path.stem}_randomized.lss",
            filetypes=[("LSS Files", "*.lss")],
        )
        if not save_path:
            return

        def task():
            t2_tool.cmd_shuffle_all(self.current_lss_path, seed, Path(save_path))

        self._run_task(
            task,
            f"Full spawn randomization complete!\n\nSaved to:\n{save_path}",
            "Error Running Full Randomize",
        )


if __name__ == "__main__":
    app = Turok2ModderGUI()
    app.mainloop()
