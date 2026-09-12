#!/usr/bin/env python3
"""
Analyze decompressed Section 5 Part 5 data to find entity structures.
"""
import struct
from pathlib import Path

def analyze_decompressed_room(filename: str):
    data = Path(filename).read_bytes()
    print(f"Analyzing {filename} ({len(data)} bytes)")
    print("=" * 60)
    
    # Look for the kubpica pattern: XYZ floats at word 5-7, model ID at word 11
    # Assuming 32-bit words (4 bytes each)
    print("\n1. Scanning for kubpica entity pattern (32-bit words):")
    print("   Word 5-7: XYZ floats, Word 11: model ID (u16)")
    
    entity_candidates = []
    for i in range(0, len(data) - 44, 4):
        # Try to parse as entity struct
        # Word 0 (offset 0): flags/unknown
        # Words 1-3 (offset 4-12): size floats
        # Words 4-6 (offset 16-24): XYZ position
        # Words 7-9 (offset 28-36): unknown/rotation
        # Word 10 (offset 40): model ID (u16)
        
        if i + 44 > len(data):
            break
            
        # Parse XYZ as floats
        try:
            x = struct.unpack_from('<f', data, i + 16)[0]
            y = struct.unpack_from('<f', data, i + 20)[0]
            z = struct.unpack_from('<f', data, i + 24)[0]
        except:
            continue
        
        # Validate coordinates (Turok 2 typical range: -10000 to 10000)
        if not (-10000 < x < 10000 and -10000 < y < 10000 and -10000 < z < 10000):
            continue
        
        # Check for NaN/Inf
        import math
        if math.isnan(x) or math.isnan(y) or math.isnan(z):
            continue
        if math.isinf(x) or math.isinf(y) or math.isinf(z):
            continue
        
        # Parse model ID at word 11 (offset 40) as u16 LE
        model_id = struct.unpack_from('<H', data, i + 40)[0]
        
        # Check if model ID is in a reasonable range for weapons/enemies
        # Weapons: 2394-2428, Enemies: 325-492 (from catalogs)
        if 2394 <= model_id <= 2428 or 325 <= model_id <= 492 or model_id == 0:
            entity_candidates.append({
                'offset': i,
                'x': x, 'y': y, 'z': z,
                'model_id': model_id
            })
    
    print(f"   Found {len(entity_candidates)} potential entities")
    for ent in entity_candidates[:10]:
        print(f"   Offset 0x{ent['offset']:04X}: XYZ=({ent['x']:.1f}, {ent['y']:.1f}, {ent['z']:.1f}) Model={ent['model_id']}")
    
    # 2. Look for repeating record patterns
    print("\n2. Searching for repeating record patterns:")
    record_size_candidates = [20, 24, 32, 40, 44, 48, 64]
    
    for rec_size in record_size_candidates:
        print(f"\n   Testing record size: {rec_size} bytes")
        # Look for patterns at regular intervals
        matches = []
        for start in range(0, min(256, len(data) - rec_size * 3)):
            pattern = data[start:start + 4]
            count = 0
            for offset in range(start, len(data) - rec_size, rec_size):
                if data[offset:offset + 4] == pattern:
                    count += 1
            if count >= 3:
                matches.append((start, pattern, count))
        
        if matches:
            print(f"   Found {len(matches)} repeating patterns:")
            for start, pattern, count in matches[:3]:
                print(f"     Start: 0x{start:04X}, Pattern: {pattern.hex()}, Count: {count}")
    
    # 3. Dump hex around known coordinate locations
    print("\n3. Hex dump around coordinate data (offset 0x40):")
    start = max(0, 0x40 - 16)
    end = min(len(data), 0x40 + 64)
    for i in range(start, end, 16):
        hex_str = ' '.join(f'{b:02X}' for b in data[i:i+16])
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        print(f"   0x{i:04X}: {hex_str:<48} {ascii_str}")
    
    # 4. Search for weapon model IDs as u16 LE
    print("\n4. Searching for weapon model IDs (u16 LE):")
    weapon_ids = {
        2394: "Bore", 2395: "ChargeDart", 2396: "Firestorm",
        2397: "FlameThrower", 2398: "FlareGun", 2399: "GrenadeLauncher",
        2400: "Mag60", 2412: "Bow", 2413: "Nuke", 2414: "PFM",
        2415: "Pistol", 2416: "PlasmaRifle", 2418: "Scorpion",
        2419: "Shotgun", 2420: "Shredder", 2421: "Sunfire",
        2422: "RazorWind", 2423: "Talon", 2424: "TekBow",
        2425: "Tranq", 2426: "Harpoon", 2427: "Torpedo", 2428: "WarBlade"
    }
    
    for model_id, name in weapon_ids.items():
        pattern = struct.pack('<H', model_id)
        offset = data.find(pattern)
        if offset != -1:
            print(f"   Found {name} (ID {model_id}) at offset 0x{offset:04X}")
            # Show context
            context_start = max(0, offset - 8)
            context_end = min(len(data), offset + 16)
            context = data[context_start:context_end]
            print(f"     Context: {context.hex()}")

if __name__ == "__main__":
    analyze_decompressed_room("decompressed_room.bin")