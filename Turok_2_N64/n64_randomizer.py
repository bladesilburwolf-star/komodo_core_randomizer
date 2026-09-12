#!/usr/bin/env python3
"""
Turok 2 N64 - Entity Randomizer
Focuses on safe, strict-struct Model ID swapping in the .z64 ROM.
"""
import os
import json
import random
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

# --- Configuration ---
# Turok 2 N64 World Bounds (approximate)
MIN_COORD = -8000.0
MAX_COORD = 8000.0
MIN_VALID_FLOAT = 0.5  # Reject denormalized floats (noise)

class N64Randomizer:
    def __init__(self, root):
        self.root = root
        self.root.title("Turok 2 N64 Randomizer (Qwen Build)")
        self.root.geometry("700x600")
        self.root.configure(bg="#2b2b2b")
        
        self.rom_path = ""
        self.weapons = set()
        self.enemies = set()
        self.load_catalogs()
        
        self.build_ui()

    def load_catalogs(self):
        """Load whitelists from JSON files."""
        try:
            with open("weapon_model_ids.json", "r") as f:
                w_data = json.load(f)
                # Handle both list and dict formats
                if isinstance(w_data, dict):
                    self.weapons.update(int(k) for k in w_data.get("weapons", {}).keys())
                else:
                    self.weapons.update(w_data)
        except FileNotFoundError:
            self.log("Warning: weapon_model_ids.json not found. Weapons will not be shuffled.")
            
        try:
            with open("enemy_catalog.json", "r") as f:
                e_data = json.load(f)
                # Handle nested structure
                if "classification" in e_data:
                    for key in ["actor_1601", "actor_1602", "actor_1609"]:
                        if key in e_data["classification"]:
                            self.enemies.update(e_data["classification"][key].get("tags", []))
                else:
                    self.enemies.update(e_data.get("models", []))
        except FileNotFoundError:
            self.log("Warning: enemy_catalog.json not found. Enemies will not be shuffled.")

    def build_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#2b2b2b")
        header.pack(fill="x", pady=10)
        tk.Label(header, text="TUROK 2 N64 ROM RANDOMIZER", font=("Arial", 16, "bold"), fg="white", bg="#2b2b2b").pack()
        tk.Label(header, text="Big-Endian Entity ID Shuffler", font=("Arial", 10), fg="#aaaaaa", bg="#2b2b2b").pack()

        # File Selector
        file_frame = tk.Frame(self.root, bg="#2b2b2b")
        file_frame.pack(fill="x", padx=20, pady=10)
        tk.Button(file_frame, text="Browse .z64 ROM", command=self.browse_rom, bg="#444444", fg="white", relief="flat").pack(side="left")
        self.lbl_rom = tk.Label(file_frame, text="No ROM selected", fg="#aaaaaa", bg="#2b2b2b", anchor="w")
        self.lbl_rom.pack(side="left", fill="x", expand=True, padx=10)

        # Options
        opts_frame = tk.Frame(self.root, bg="#2b2b2b")
        opts_frame.pack(fill="x", padx=20, pady=5)
        
        tk.Label(opts_frame, text="Seed:", fg="white", bg="#2b2b2b").grid(row=0, column=0, sticky="w", padx=5)
        self.ent_seed = tk.Entry(opts_frame, width=15, bg="#333333", fg="white", insertbackground="white")
        self.ent_seed.grid(row=0, column=1, sticky="w", padx=5)
        self.ent_seed.insert(0, "Random")

        tk.Label(opts_frame, text="Mode:", fg="white", bg="#2b2b2b").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.mode_var = tk.StringVar(value="all")
        tk.Radiobutton(opts_frame, text="All Entities", variable=self.mode_var, value="all", fg="white", bg="#2b2b2b", selectcolor="#444444").grid(row=1, column=1, sticky="w", padx=5)
        tk.Radiobutton(opts_frame, text="Weapons Only", variable=self.mode_var, value="weapons", fg="white", bg="#2b2b2b", selectcolor="#444444").grid(row=2, column=1, sticky="w", padx=5)
        tk.Radiobutton(opts_frame, text="Enemies Only", variable=self.mode_var, value="enemies", fg="white", bg="#2b2b2b", selectcolor="#444444").grid(row=3, column=1, sticky="w", padx=5)

        # Actions
        btn_frame = tk.Frame(self.root, bg="#2b2b2b")
        btn_frame.pack(fill="x", padx=20, pady=10)
        tk.Button(btn_frame, text="Dry-Run Scan", command=self.start_scan, bg="#555555", fg="white", relief="flat").pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(btn_frame, text="Randomize & Save ROM", command=self.start_randomize, bg="#007acc", fg="white", relief="flat", font=("Arial", 10, "bold")).pack(side="right", fill="x", expand=True, padx=5)

        # Log
        self.log_box = scrolledtext.ScrolledText(self.root, height=15, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9), insertbackground="white")
        self.log_box.pack(fill="both", expand=True, padx=20, pady=10)
        self.log("[Ready] Select a .z64 ROM to begin.")

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.root.update_idletasks()

    def browse_rom(self):
        path = filedialog.askopenfilename(filetypes=[("N64 ROM", "*.z64"), ("All Files", "*.*")])
        if path:
            self.rom_path = path
            self.lbl_rom.configure(text=os.path.basename(path), fg="white")
            self.log(f"Loaded ROM: {path}")

    def start_scan(self):
        if not self.rom_path:
            messagebox.showerror("Error", "Select a ROM first.")
            return
        self.log("\n[Scanning] Analyzing ROM for Big-Endian entity structs...")
        self.root.update_idletasks()
        
        try:
            data = open(self.rom_path, "rb").read()
            hits = self.find_entities(data)
            
            w_count = sum(1 for h in hits if h['type'] == 'WEAPON')
            e_count = sum(1 for h in hits if h['type'] == 'ENEMY')
            
            self.log(f"[Scan Complete] Found {len(hits)} valid entities.")
            self.log(f"  - Weapons: {w_count}")
            self.log(f"  - Enemies: {e_count}")
        except Exception as e:
            self.log(f"[Error] {str(e)}")

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

        self.log("\n[Randomizing] Processing ROM...")
        self.root.update_idletasks()
        
        seed_str = self.ent_seed.get().strip()
        seed = int(seed_str) if seed_str.isdigit() else random.randint(100000, 999999)
        mode = self.mode_var.get()
        
        try:
            data = bytearray(open(self.rom_path, "rb").read())
            hits = self.find_entities(data)
            
            if mode == "weapons":
                hits = [h for h in hits if h['type'] == 'WEAPON']
            elif mode == "enemies":
                hits = [h for h in hits if h['type'] == 'ENEMY']
                
            if len(hits) < 2:
                self.log("[Abort] Not enough entities found to shuffle.")
                return

            rng = random.Random(seed)
            ids = [h['model_id'] for h in hits]
            rng.shuffle(ids)
            
            for h, new_id in zip(hits, ids):
                # Write Big-Endian u16 at offset + 40
                struct.pack_into('>H', data, h['offset'] + 40, new_id)
                
            with open(save_path, "wb") as f:
                f.write(data)
                
            self.log(f"[Success] ROM saved to: {save_path}")
            self.log(f"Seed: {seed} | Mode: {mode.upper()} | Entities shuffled: {len(hits)}")
            messagebox.showinfo("Success", f"Randomization complete!\nSaved to:\n{save_path}")
            
        except Exception as e:
            self.log(f"[Failure] {str(e)}")
            messagebox.showerror("Error", str(e))

    def find_entities(self, data: bytearray):
        """Strict Big-Endian struct scanner with noise filtering."""
        hits = []
        last_offset = -100
        
        # Scan 4-byte aligned offsets
        # We look for XYZ at offset+16 and Model ID at offset+40
        for i in range(0, len(data) - 44, 4):
            # Enforce minimum distance to prevent sliding window duplicates
            if i - last_offset < 20:
                continue
                
            try:
                # Parse XYZ as Big-Endian Floats
                x, y, z = struct.unpack_from('>fff', data, i + 16)
            except:
                continue
                
            # 1. Filter out NaN/Inf
            if any(v != v or abs(v) == float('inf') for v in (x, y, z)):
                continue
                
            # 2. Filter out Denormalized Floats (The main source of noise)
            # Real coordinates are usually > 0.5 or exactly 0.0
            is_valid_coord = True
            for v in (x, y, z):
                if v != 0.0 and abs(v) < MIN_VALID_FLOAT:
                    is_valid_coord = False
                    break
            if not is_valid_coord:
                continue
                
            # 3. Filter out of bounds
            if not (MIN_COORD < x < MAX_COORD and MIN_COORD < y < MAX_COORD and MIN_COORD < z < MAX_COORD):
                continue
                
            # 4. Parse Model ID at offset + 40 (Word 10)
            model_id = struct.unpack_from('>H', data, i + 40)[0]
            
            if model_id in self.weapons:
                hits.append({'offset': i, 'model_id': model_id, 'type': 'WEAPON'})
                last_offset = i
            elif model_id in self.enemies:
                hits.append({'offset': i, 'model_id': model_id, 'type': 'ENEMY'})
                last_offset = i
                
        return hits

if __name__ == "__main__":
    root = tk.Tk()
    app = N64Randomizer(root)
    root.mainloop()