#!/usr/bin/env python3
"""
Turok 2: Seeds of Evil - Randovania Style Randomizer
Integrates with t2_tool.py backend for stable spawn shuffling.
"""
import os
import shutil
import random
import json
from dataclasses import dataclass
from typing import List, Set, Optional, Tuple
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Import backend logic from t2_tool.py
import t2_tool
from t2_tool import (
    get_section, find_position_records, spawn_record_map_id, 
    patch_section, WARPS_SECTION, get_map_catalog
)

# --- Randovania Dark Aesthetic ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BOSS_MAP_INDICES = {1, 2, 3, 4}

@dataclass
class RandomizerConfig:
    lss_file_path: str
    seed: int
    start_pool_mode: str  # "vanilla", "hubs", "chaos"
    entrance_mode: str    # "coupled", "decoupled"
    exclude_bosses: bool

class Turok2LSSProcessor:
    def __init__(self, config: RandomizerConfig):
        self.config = config
        self.rng = random.Random(config.seed)
        self.map_catalog = get_map_catalog()
        
    def _get_target_maps(self) -> Optional[Set[int]]:
        """Resolve UI selection to a set of map indices."""
        aliases = self.map_catalog.get("aliases", {})
        target_set = set()
        
        if self.config.start_pool_mode == "vanilla":
            target_set.update(aliases.get("port", []))
        elif self.config.start_pool_mode == "hubs":
            target_set.update(aliases.get("port", []))
            target_set.update(aliases.get("hub", []))
            target_set.update(aliases.get("marsh", []))
        # "chaos" returns None (handled in processor)
        
        if self.config.exclude_bosses:
            target_set -= BOSS_MAP_INDICES
            
        return target_set if target_set else None

    def process_and_save(self) -> Tuple[str, str]:
        if not os.path.exists(self.config.lss_file_path):
            raise FileNotFoundError("Target .lss file not found.")
            
        # 1. Create Backup
        backup_dir = os.path.join(os.path.dirname(self.config.lss_file_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        base_name = os.path.basename(self.config.lss_file_path)
        name_no_ext, ext = os.path.splitext(base_name)
        backup_path = os.path.join(backup_dir, f"{name_no_ext}_backup{ext}")
        if not os.path.exists(backup_path):
            shutil.copy2(self.config.lss_file_path, backup_path)
            
        # 2. Read LSS Bytes
        with open(self.config.lss_file_path, "rb") as f:
            data = bytearray(f.read())
            
        # 3. Apply Logic
        modified_data = self._shuffle_lss_spawns(data)
        
        # 4. Export
        output_filename = f"{name_no_ext}_seed{self.config.seed}{ext}"
        output_path = os.path.join(os.path.dirname(self.config.lss_file_path), output_filename)
        with open(output_path, "wb") as f:
            f.write(modified_data)
            
        return backup_path, output_path

    def _shuffle_lss_spawns(self, data: bytearray) -> bytearray:
        sec, sec_start, sec_end = get_section(data, WARPS_SECTION)
        sec_ba = bytearray(sec)
        records = find_position_records(bytes(sec_ba))
        
        if len(records) < 2:
            raise RuntimeError("Not enough spawn records found in Section 8.")
            
        target_maps = self._get_target_maps()
        
        # Identify "Entry" points (spawn points in target maps)
        if target_maps:
            entry_points = [(off, rec) for off, rec in records if spawn_record_map_id(rec) in target_maps]
        else:
            entry_points = records  # Chaos mode: all records are valid
            
        if len(entry_points) < 2:
            raise RuntimeError(f"Not enough spawn records found in target maps ({len(entry_points)}).")
            
        # Apply Entrance Logic
        if self.config.entrance_mode == "coupled":
            # Shuffle entry points among themselves
            pool = entry_points
            blocks = [b for _, b in pool]
            self.rng.shuffle(blocks)
            for (off, _), nb in zip(entry_points, blocks):
                sec_ba[off:off + len(nb)] = nb
        else:  # decoupled
            # Shuffle ALL records in the game, but only place them into entry_points
            # This creates "Chaos" starts (e.g., spawn in Port, but position is from Hive)
            all_blocks = [b for _, b in records]
            self.rng.shuffle(all_blocks)
            # Take the first N blocks (where N = len(entry_points)) and place them
            for (off, _), nb in zip(entry_points, all_blocks[:len(entry_points)]):
                sec_ba[off:off + len(nb)] = nb
                
        patch_section(data, WARPS_SECTION, bytes(sec_ba))
        return data

class RandovaniaStyleGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Acclaim Logic Randomizer - Turok 2 Engine")
        self.geometry("740x680")
        self.resizable(False, False)
        self.selected_file_path = ""
        
        # --- Header ---
        self.header_frame = ctk.CTkFrame(self, corner_radius=10)
        self.header_frame.pack(padx=20, pady=15, fill="x")
        self.title_label = ctk.CTkLabel(
            self.header_frame, 
            text="TUROK 2: SEEDS OF EVIL RANDOMIZER", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.title_label.pack(padx=10, pady=(10, 2))
        self.subtitle_label = ctk.CTkLabel(
            self.header_frame, 
            text="Randovania-Based Starting Pool & Entrance Suite", 
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="gray"
        )
        self.subtitle_label.pack(padx=10, pady=(0, 10))
        
        # --- File Selector Frame ---
        self.file_frame = ctk.CTkFrame(self, corner_radius=10)
        self.file_frame.pack(padx=20, pady=(0, 10), fill="x")
        self.btn_browse = ctk.CTkButton(
            self.file_frame, text="Browse .LSS File", command=self.browse_file, width=130
        )
        self.btn_browse.pack(side="left", padx=15, pady=15)
        self.lbl_file_path = ctk.CTkLabel(
            self.file_frame, text="No .lss file selected", text_color="gray", anchor="w"
        )
        self.lbl_file_path.pack(side="left", padx=10, fill="x", expand=True)
        
        # --- Main Options Frame ---
        self.body_frame = ctk.CTkFrame(self, corner_radius=10)
        self.body_frame.pack(padx=20, pady=5, fill="both", expand=True)
        
        # Column 1: Starting Location Pools
        self.start_box = ctk.CTkFrame(self.body_frame, fg_color="transparent")
        self.start_box.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.start_title = ctk.CTkLabel(self.start_box, text="Starting Location Pool", font=ctk.CTkFont(size=14, weight="bold"))
        self.start_title.pack(anchor="w", pady=(0, 10))
        self.start_pool_var = ctk.StringVar(value="hubs")
        self.rad_vanilla = ctk.CTkRadioButton(self.start_box, text="Vanilla (Port of Adia)", variable=self.start_pool_var, value="vanilla")
        self.rad_vanilla.pack(anchor="w", pady=5)
        self.rad_hubs = ctk.CTkRadioButton(self.start_box, text="Balanced Hubs (Port/Hub/Marsh)", variable=self.start_pool_var, value="hubs")
        self.rad_hubs.pack(anchor="w", pady=5)
        self.rad_chaos = ctk.CTkRadioButton(self.start_box, text="Unrestricted Chaos (Any Sector)", variable=self.start_pool_var, value="chaos")
        self.rad_chaos.pack(anchor="w", pady=5)
        
        # Column 2: Entrance Logic
        self.entrance_box = ctk.CTkFrame(self.body_frame, fg_color="transparent")
        self.entrance_box.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.entrance_title = ctk.CTkLabel(self.entrance_box, text="Entrance Coupling Logic", font=ctk.CTkFont(size=14, weight="bold"))
        self.entrance_title.pack(anchor="w", pady=(0, 10))
        self.entrance_var = ctk.StringVar(value="coupled")
        self.rad_coupled = ctk.CTkRadioButton(self.entrance_box, text="Coupled (2-Way Symmetric)", variable=self.entrance_var, value="coupled")
        self.rad_coupled.pack(anchor="w", pady=5)
        self.rad_decoupled = ctk.CTkRadioButton(self.entrance_box, text="Decoupled (1-Way Asymmetric)", variable=self.entrance_var, value="decoupled")
        self.rad_decoupled.pack(anchor="w", pady=5)
        self.exclude_bosses_var = ctk.BooleanVar(value=True)
        self.chk_bosses = ctk.CTkCheckBox(self.entrance_box, text="Exclude Boss Arenas", variable=self.exclude_bosses_var)
        self.chk_bosses.pack(anchor="w", pady=(15, 5))
        
        # Seed Entry
        self.config_frame = ctk.CTkFrame(self.body_frame, fg_color="transparent")
        self.config_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=5, sticky="ew")
        self.seed_label = ctk.CTkLabel(self.config_frame, text="Seed Number:")
        self.seed_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.seed_entry = ctk.CTkEntry(self.config_frame, placeholder_text="e.g. 849201", width=160)
        self.seed_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # --- Action Button ---
        self.btn_generate = ctk.CTkButton(
            self, 
            text="Randomize & Export Seed", 
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            command=self.run_generation
        )
        self.btn_generate.pack(padx=20, pady=10, fill="x")
        
        # --- Log Output ---
        self.log_box = ctk.CTkTextbox(self, height=130)
        self.log_box.pack(padx=20, pady=(0, 15), fill="x")
        self.log_box.insert("0.0", "[System Ready] Select a Seeds of Evil .lss file to begin.\n")

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Select Seeds of Evil .lss File",
            filetypes=(("LSS Save Files", "*.lss"), ("All Files", "*.*"))
        )
        if filename:
            self.selected_file_path = filename
            self.lbl_file_path.configure(text=os.path.basename(filename), text_color="white")
            self.log_box.insert("end", f"[Loaded File]: {filename}\n")
            self.log_box.see("end")

    def run_generation(self):
        if not self.selected_file_path:
            messagebox.showerror("Error", "Please select an .lss file first!")
            return
            
        seed_val = self.seed_entry.get().strip()
        seed = int(seed_val) if seed_val.isdigit() else random.randint(100000, 999999)
        
        config = RandomizerConfig(
            lss_file_path=self.selected_file_path,
            seed=seed,
            start_pool_mode=self.start_pool_var.get(),
            entrance_mode=self.entrance_var.get(),
            exclude_bosses=self.exclude_bosses_var.get()
        )
        
        try:
            processor = Turok2LSSProcessor(config)
            backup_path, output_path = processor.process_and_save()
            
            self.log_box.insert("end", f"\n=== SEED GENERATION SUCCESSFUL [{seed}] ===\n")
            self.log_box.insert("end", f"Mode: {config.start_pool_mode.upper()} | Logic: {config.entrance_mode.upper()}\n")
            self.log_box.insert("end", f"Backup Saved To: {backup_path}\n")
            self.log_box.insert("end", f"Exported New Seed: {os.path.basename(output_path)}\n")
            self.log_box.see("end")
            messagebox.showinfo("Success", f"Seed {seed} generated successfully!\nSaved to:\n{output_path}")
        except Exception as e:
            self.log_box.insert("end", f"[FAILURE]: {str(e)}\n")
            self.log_box.see("end")
            messagebox.showerror("Randomization Failed", str(e))

if __name__ == "__main__":
    app = RandovaniaStyleGUI()
    app.mainloop()