#!/usr/bin/env python3
"""
Filter and analyze entity data to find the true structure.
"""
import json
import math

def filter_valid_entities(input_file: str, output_file: str):
    with open(input_file, 'r') as f:
        entities = json.load(f)
    
    valid_entities = []
    for ent in entities:
        x, y, z = ent['x'], ent['y'], ent['z']
        
        # Check for valid coordinates
        # Must be in reasonable range and not denormalized
        is_valid = True
        for coord in (x, y, z):
            # Reject NaN and Infinity
            if math.isnan(coord) or math.isinf(coord):
                is_valid = False
                break
            # Reject denormalized floats (extremely small non-zero values)
            if coord != 0.0 and abs(coord) < 1e-10:
                is_valid = False
                break
            # Reject coordinates outside reasonable world bounds
            if abs(coord) > 10000:
                is_valid = False
                break
        
        if is_valid:
            valid_entities.append(ent)
    
    print(f"Filtered {len(entities)} total hits down to {len(valid_entities)} valid entities")
    
    with open(output_file, 'w') as f:
        json.dump(valid_entities, f, indent=2)
    
    # Analyze the valid entities
    if valid_entities:
        print("\n=== VALID ENTITY ANALYSIS ===")
        
        # Count by type
        weapons = [e for e in valid_entities if e['type'] == 'WEAPON']
        enemies = [e for e in valid_entities if e['type'] == 'ENEMY']
        print(f"\nWeapons: {len(weapons)}")
        print(f"Enemies: {len(enemies)}")
        
        # Show sample valid entities
        print("\n=== SAMPLE VALID ENTITIES (first 20) ===")
        for ent in valid_entities[:20]:
            print(f"Map {ent['map']:3d} Part {ent['part']} Offset 0x{ent['offset_in_part']:05X} | "
                  f"XYZ({ent['x']:8.2f}, {ent['y']:8.2f}, {ent['z']:8.2f}) | "
                  f"Model {ent['model_id']:5d} ({ent['type']})")
        
        # Analyze model ID distribution
        print("\n=== MODEL ID DISTRIBUTION ===")
        model_counts = {}
        for ent in valid_entities:
            mid = ent['model_id']
            model_counts[mid] = model_counts.get(mid, 0) + 1
        
        print("Top 20 most common model IDs:")
        for mid, count in sorted(model_counts.items(), key=lambda x: -x[1])[:20]:
            print(f"  Model {mid:5d}: {count:3d} occurrences")
        
        # Analyze map distribution
        print("\n=== MAP DISTRIBUTION ===")
        map_counts = {}
        for ent in valid_entities:
            m = ent['map']
            map_counts[m] = map_counts.get(m, 0) + 1
        
        print("Maps with most entities:")
        for m, count in sorted(map_counts.items(), key=lambda x: -x[1])[:15]:
            print(f"  Map {m:3d}: {count:3d} entities")
    
    return valid_entities

if __name__ == "__main__":
    filter_valid_entities("all_entities.txt", "valid_entities.json")