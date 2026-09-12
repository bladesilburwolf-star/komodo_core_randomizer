#!/usr/bin/env python3
"""
Strict Entity Struct Parser
Enforces the exact kubpica layout to eliminate sliding window false positives.
"""
import struct
import json
from pathlib import Path

def load_whitelists():
    weapons = set()
    enemies = set()
    
    try:
        with open("weapon_model_ids.json", "r") as f:
            w_data = json.load(f)
            weapons.update(int(k) for k in w_data.get("weapons", {}).keys())
    except FileNotFoundError:
        # Fallback if file is missing
        weapons.update(range(2394, 2429))
        
    try:
        with open("enemy_catalog.json", "r") as f:
            e_data = json.load(f)
            for key in ["actor_1601_models", "actor_1602_models", "actor_1609_models"]:
                enemies.update(e_data.get(key, []))
    except FileNotFoundError:
        enemies.update(range(325, 493))
        
    return weapons, enemies

def strict_struct_scan(filename: str, is_big_endian: bool = False):
    data = Path(filename).read_bytes()
    weapons, enemies = load_whitelists()
    all_valid_ids = weapons | enemies
    
    endian_char = ">" if is_big_endian else "<"
    print(f"Scanning {filename} ({len(data)} bytes) with STRICT struct enforcement...")
    print(f"Endian: {'Big (N64)' if is_big_endian else 'Little (PC)'}")
    print("=" * 80)
    
    valid_entities = []
    
    # The struct is exactly 44 bytes (11 words of 4 bytes each)
    # Word 0-3: Flags/Scale (bytes 0-15)
    # Word 4-6: X, Y, Z floats (bytes 16-27)
    # Word 7-9: Rotation/Unknown (bytes 28-39)
    # Word 10: Model ID u16 (bytes 40-41)
    
    for i in range(0, len(data) - 44, 4):
        # 1. STRICTLY parse XYZ at bytes 16, 20, 24
        x = struct.unpack_from(f'{endian_char}f', data, i + 16)[0]
        y = struct.unpack_from(f'{endian_char}f', data, i + 20)[0]
        z = struct.unpack_from(f'{endian_char}f', data, i + 24)[0]
        
        # 2. Validate coordinates (Must be reasonable, non-zero, non-denormalized)
        if not (-5000.0 < x < 5000.0 and -5000.0 < y < 5000.0 and -5000.0 < z < 5000.0):
            continue
        if abs(x) < 0.1 and abs(y) < 0.1 and abs(z) < 0.1:
            continue # Reject (0,0,0) or near-zero noise
            
        # 3. STRICTLY parse Model ID at byte 40 (Word 10)
        # Read as u32 first, then mask to u16 to handle potential padding
        raw_id = struct.unpack_from(f'{endian_char}I', data, i + 40)[0]
        model_id = raw_id & 0xFFFF
        
        # 4. Check whitelist
        if model_id in all_valid_ids:
            entity_type = "WEAPON" if model_id in weapons else "ENEMY"
            valid_entities.append({
                'offset': i,
                'x': round(x, 2),
                'y': round(y, 2),
                'z': round(z, 2),
                'model_id': model_id,
                'type': entity_type
            })
            
    print(f"Found {len(valid_entities)} STRICT matches.")
    
    if valid_entities:
        print("\nFirst 20 Valid Entities:")
        print(f"{'Offset':>10} | {'X':>8} | {'Y':>8} | {'Z':>8} | {'Model':>6} | {'Type'}")
        print("-" * 65)
        for ent in valid_entities[:20]:
            print(f"0x{ent['offset']:08X} | {ent['x']:>8.2f} | {ent['y']:>8.2f} | {ent['z']:>8.2f} | {ent['model_id']:>5d} | {ent['type']}")
            
        # Save to a manageable text file
        with open("strict_entities.txt", "w") as f:
            for ent in valid_entities:
                f.write(f"0x{ent['offset']:08X} | {ent['x']:>8.2f} | {ent['y']:>8.2f} | {ent['z']:>8.2f} | {ent['model_id']:>5d} | {ent['type']}\n")
        print("\nSaved clean results to strict_entities.txt")
        
    return valid_entities

if __name__ == "__main__":
    # Try the N64 ROM first (Big Endian) - it yielded clean results before
    if Path("Turok 2 - Seeds of Evil (USA).z64").exists():
        print(">>> Scanning N64 ROM (Big Endian) <<<")
        strict_struct_scan("Turok 2 - Seeds of Evil (USA).z64", is_big_endian=True)
        
    # Then try the decompressed PC data (Little Endian)
    if Path("decompressed_room.bin").exists():
        print("\n>>> Scanning Decompressed PC Room (Little Endian) <<<")
        strict_struct_scan("decompressed_room.bin", is_big_endian=False)