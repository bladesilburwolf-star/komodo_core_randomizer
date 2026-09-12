#!/usr/bin/env python3
"""
Turok 2: Seeds of Evil (N64) - Randovania Style ROM Randomizer
Standalone tool for shuffling entity Model IDs in the .z64 ROM.
"""
import os
import json
import random
import struct
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk

# --- Randovania Dark Aesthetic ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class N64RandomizerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Turok 2 N64 - Entity Randomizer (Qwen Build)")
        self.geometry("700x650")
        self.resizable(False, False)
        
        self.rom_path = ""
        self.weapons = set()
        self.enemies = set()
        self.load_catalogs()
        
        self._build_ui()

    def load_catalogs(self):
        """Load whitelists from JSON files in the current directory."""
        try:
            with open("weapon_model_ids.json", "r") as f:
                w_data = json.load(f)
                self.weapons.update(int(k) for k in w_data.get("weapons", {}).keys())
        except FileNotFoundError:
            print("Warning: weapon_model_ids.json not found.")
            
        try:
            with open("enemy_catalog.json", "r") as f:
                e_data = json.load(f)
                for key in ["actor_1601_models", "actor_1602_models", "actor_1609_models"]:
                    self.enemies.update(e_data.get(key, []))
        except FileNotFoundError:
            print("Warning: enemy_catalog.json not found.")

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, corner_radius=10)
        header.pack(padx=20, pady=15, fill="x")
        ctk.CTkLabel(header, text="TUROK 2 N64 ROM RANDOMIZER", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=10)
        ctk.CTkLabel(header, text="Big-Endian Entity ID Shuffler", text_color="gray").pack(pady=(0, 10))

        # File Selector
        file_frame = ctk.CTkFrame(self, corner_radius=10)
        file_frame.pack(padx=20, pady=5, fill="x")
        self.btn_browse = ctk.CTkButton(file_frame, text="Browse .z64 ROM", command=self.browse_rom, width=130)
        self.btn_browse.pack(side="left", padx=15, pady=15)
        self.lbl_rom = ctk.CTkLabel(file_frame, text="No ROM selected", anchor="w")
        self.lbl_rom.pack(side="left", fill="x", expand=True, padx=10)

        # Options
        opts_frame = ctk.CTkFrame(self, corner_radius=10)
        opts_frame.pack(padx=20, pady=5, fill="x")
        
        ctk.CTkLabel(opts_frame, text="Seed:").grid(row=0, column=0, padx=15, pady=15, sticky="w")
        self.ent_seed = ctk.CTkEntry(opts_frame, placeholder_text="Random", width=120)
        self.ent_seed.grid(row=0, column=1, padx=5, pady=15, sticky="w")

        ctk.CTkLabel(opts_frame, text="Shuffle Mode:").grid(row=1, column=0, padx=15, pady=5, sticky="w")
        self.mode_var = ctk.StringVar(value="all")
        ctk.CTkRadioButton(opts_frame, text="All Entities (Weapons + Enemies)", variable=self.mode_var, value="all").grid(row=1, column=1, sticky="w", pady=5)
        ctk.CTkRadioButton(opts_frame, text="Weapons Only", variable=self.mode_var, value="weapons").grid(row=2, column=1, sticky="w", pady=5)
        ctk.CTkRadioButton(opts_frame, text="Enemies Only", variable=self.mode_var, value="enemies").grid(row=3, column=1, sticky="w", pady=5)

        # Actions
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(padx=20, pady=10, fill="x")
        self.btn_scan = ctk.CTkButton(btn_frame, text="Dry-Run Scan", command=self.start_scan, fg_color="gray")
        self.btn_scan.pack(side="left", padx=10, fill="x", expand=True)
        self.btn_randomize = ctk.CTkButton(btn_frame, text="Randomize & Save ROM", command=self.start_randomize, height=40)
        self.btn_randomize.pack(side="right", padx=10, fill="x", expand=True)

        # Log
        self.log = ctk.CTkTextbox(self, height=200)
        self.log.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        self.log.insert("0.0", "[Ready] Select a .z64 ROM to begin.\n")

    def log_msg(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def browse_rom(self):
        path = filedialog.askopenfilename(filetypes=[("N64 ROM", "*.z64"), ("All Files", "*.*")])
        if path:
            self.rom_path = path
            self.lbl_rom.configure(text=os.path.basename(path))
            self.log_msg(f"Loaded ROM: {path}")

    def start_scan(self):
        if not self.rom_path:
            messagebox.showerror("Error", "Select a ROM first.")
            return
        self.btn_scan.configure(state="disabled")
        self.btn_randomize.configure(state="disabled")
        self.log_msg("\n[Scanning] Analyzing ROM for Big-Endian entity structs...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            data = Path(self.rom_path).read_bytes()
            hits = self._find_entities(data)
            w_count = sum(1 for h in hits if h['type'] == 'WEAPON')
            e_count = sum(1 for h in hits if h['type'] == 'ENEMY')
            
            self.after(0, lambda: self.log_msg(f"[Scan Complete] Found {len(hits)} valid entities."))
            self.after(0, lambda: self.log_msg(f"  - Weapons: {w_count}"))
            self.after(0, lambda: self.log_msg(f"  - Enemies: {e_count}"))
        except Exception as e:
            self.after(0, lambda: self.log_msg(f"[Error] {str(e)}"))
        finally:
            self.after(0, lambda: self.btn_scan.configure(state="normal"))
            self.after(0, lambda: self.btn_randomize.configure(state="normal"))

    def start_randomize(self):
        if not self.rom_path:
            messagebox.showerror("Error", "Select a ROM first.")
            return
            
        save_path = filedialog.asksaveasfilename(
            title="Save Randomized ROM As...",
            defaultextension=".z64",
            initialfile=os.path.basename(self.rom_path).replace('.z64', '_randomized.z64')
        )
        if not save_path:
            return

        self.btn_randomize.configure(state="disabled")
        self.btn_scan.configure(state="disabled")
        self.log_msg("\n[Randomizing] Processing ROM...")
        
        seed_str = self.ent_seed.get().strip()
        seed = int(seed_str) if seed_str.isdigit() else random.randint(100000, 999999)
        mode = self.mode_var.get()
        
        threading.Thread(target=self._randomize_worker, args=(save_path, seed, mode), daemon=True).start()

    def _randomize_worker(self, save_path, seed, mode):
        try:
            # Read ROM into mutable bytearray
            data = bytearray(Path(self.rom_path).read_bytes())
            hits = self._find_entities(data)
            
            # Filter hits based on mode
            if mode == "weapons":
                hits = [h for h in hits if h['type'] == 'WEAPON']
            elif mode == "enemies":
                hits = [h for h in hits if h['type'] == 'ENEMY']
                
            if len(hits) < 2:
                self.after(0, lambda: self.log_msg("[Abort] Not enough entities found to shuffle."))
                return

            # Shuffle IDs
            rng = random.Random(seed)
            ids = [h['model_id'] for h in hits]
            rng.shuffle(ids)
            
            # Write new IDs back to ROM (Big-Endian u16 at offset + 40)
            for h, new_id in zip(hits, ids):
                struct.pack_into('>H', data, h['offset'] + 40, new_id)
                
            # Save
            Path(save_path).write_bytes(data)
            
            self.after(0, lambda: self.log_msg(f"[Success] ROM saved to: {save_path}"))
            self.after(0, lambda: self.log_msg(f"Seed: {seed} | Mode: {mode.upper()} | Entities shuffled: {len(hits)}"))
            self.after(0, lambda: messagebox.showinfo("Success", f"Randomization complete!\nSaved to:\n{save_path}"))
            
        except Exception as e:
            self.after(0, lambda: self.log_msg(f"[Failure] {str(e)}"))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self.btn_randomize.configure(state="normal"))
            self.after(0, lambda: self.btn_scan.configure(state="normal"))

    def _find_entities(self, data: bytearray):
        """Strict Big-Endian struct scanner."""
        hits = []
        last_offset = -100
        
        # Scan 4-byte aligned offsets
        for i in range(0, len(data) - 44, 4):
            # Prevent overlapping hits (sliding window noise)
            if i - last_offset < 20:
                continue
                
            try:
                # Parse XYZ at offset + 16 (Words 4-6)
                x, y, z = struct.unpack_from('>fff', data, i + 16)
            except:
                continue
                
            # Validate coordinates
            if not (-5000.0 < x < 5000.0 and -5000.0 < y < 5000.0 and -5000.0 < z < 5000.0):
                continue
            if any(v != v for v in (x, y, z)): # NaN check
                continue
                
            # Parse Model ID at offset + 40 (Word 10)
            model_id = struct.unpack_from('>H', data, i + 40)[0]
            
            if model_id in self.weapons:
                hits.append({'offset': i, 'model_id': model_id, 'type': 'WEAPON'})
                last_offset = i
            elif model_id in self.enemies:
                hits.append({'offset': i, 'model_id': model_id, 'type': 'ENEMY'})
                last_offset = i
                
        return hits

if __name__ == "__main__":
    app = N64RandomizerGUI()
    app.mainloop()