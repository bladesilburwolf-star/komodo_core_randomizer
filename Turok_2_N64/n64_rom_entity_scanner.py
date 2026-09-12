#!/usr/bin/env python3
"""
N64 ROM Entity Scanner for Turok 2: Seeds of Evil
Hunts for the 'kubpica' entity struct pattern in the raw N64 ROM.
"""
import struct
import json
from pathlib import Path

# Load our whitelists from the JSON catalogs
def load_catalogs():
    weapon_ids = set()
    enemy_ids = set()
    
    # Load Weapon IDs
    with open("weapon_model_ids.json", "r") as f:
        w_data = json.load(f)
        weapon_ids.update(int(k) for k in w_data.get("weapons", {}).keys())
        
    # Load Enemy IDs (from actor_1601, 1602, 1609 groups)
    with open("enemy_catalog.json", "r") as f:
        e_data = json.load(f)
        for group in ["actor_1601_models", "actor_1602_models", "actor_1609_models"]:
            enemy_ids.update(e_data.get(group, []))
            
    return weapon_ids, enemy_ids

def scan_rom_for_entities(rom_path: str, weapon_ids: set, enemy_ids: set):
    """
    Scans the N64 ROM for the entity struct pattern.
    Pattern: Big-Endian XYZ floats at offset 16, Model ID u16 at offset 40.
    """
    rom_data = Path(rom_path).read_bytes()
    rom_size = len(rom_data)
    
    print(f"Loaded ROM: {rom_path} ({rom_size / 1024 / 1024:.2f} MB)")
    print(f"Scanning for entity structs (Big-Endian)...")
    
    hits = []
    # We scan 4-byte aligned offsets. The struct is at least 44 bytes (11 words).
    # We step by 4 bytes to catch the start of the struct.
    for i in range(0, rom_size - 44, 4):
        chunk = rom_data[i : i + 44]
        if len(chunk) < 44:
            break
            
        # 1. Parse Words 5-7 as Big-Endian Floats (X, Y, Z)
        try:
            x, y, z = struct.unpack_from(">fff", chunk, 16)
        except struct.error:
            continue
            
        # Sanity Check: Turok 2 coordinates are usually within -10000 to 10000.
        # Filter out NaN, Inf, and massive geometry coordinates.
        if not (-10000.0 < x < 10000.0 and -10000.0 < y < 10000.0 and -10000.0 < z < 10000.0):
            continue
        if any(v != v for v in (x, y, z)): # NaN check
            continue
            
        # 2. Parse Word 11 as Big-Endian u16 (Model ID)
        model_id = struct.unpack_from(">H", chunk, 40)[0]
        
        # 3. Check against whitelists
        if model_id in weapon_ids:
            hits.append({
                "offset": i,
                "type": "WEAPON",
                "model_id": model_id,
                "x": x, "y": y, "z": z
            })
        elif model_id in enemy_ids:
            hits.append({
                "offset": i,
                "type": "ENEMY",
                "model_id": model_id,
                "x": x, "y": y, "z": z
            })
            
    return hits

def main():
    rom_file = "t2.z64" # Replace with your ROM name
    if not Path(rom_file).exists():
        print(f"Error: {rom_file} not found. Place the N64 ROM in the same directory.")
        return
        
    weapon_ids, enemy_ids = load_catalogs()
    print(f"Loaded {len(weapon_ids)} weapon IDs and {len(enemy_ids)} enemy IDs.")
    
    hits = scan_rom_for_entities(rom_file, weapon_ids, enemy_ids)
    
    print(f"\n=== SCAN COMPLETE ===")
    print(f"Total Valid Entity Hits: {len(hits)}")
    
    if hits:
        print(f"\n{'Type':<8} {'Offset':>10} {'Model ID':>10} {'X':>10} {'Y':>10} {'Z':>10}")
        print("-" * 60)
        for h in hits[:50]: # Print first 50
            print(f"{h['type']:<8} 0x{h['offset']:08X} {h['model_id']:>10} {h['x']:>10.2f} {h['y']:>10.2f} {h['z']:>10.2f}")
            
        # Export to JSON for further analysis
        with open("n64_entity_hits.json", "w") as f:
            json.dump(hits, f, indent=2)
        print("\nFull results exported to n64_entity_hits.json")
    else:
        print("\nNo hits found. The level data is likely compressed in the ROM.")
        print("Next step: Use an emulator (like Project64 or Mupen64Plus) with a memory dumper")
        print("to extract the decompressed level buffer from RAM while a level is loaded,")
        print("then run this scanner against the dumped .bin file.")

if __name__ == "__main__":
    main()