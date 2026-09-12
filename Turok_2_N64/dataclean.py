import json
import struct

def clean_entity_hits(input_file: str, output_file: str):
    with open(input_file, 'r') as f:
        hits = json.load(f)
        
    valid_hits = []
    for hit in hits:
        x, y, z = hit['x'], hit['y'], hit['z']
        
        # Filter out denormalized/garbage floats
        # Real coordinates are usually between -10000 and 10000
        # and are not extremely small denormals (like 1e-39)
        is_valid = True
        for coord in (x, y, z):
            if abs(coord) > 10000:
                is_valid = False
                break
            # Allow 0.0, but reject denormals smaller than 1e-10
            if coord != 0.0 and abs(coord) < 1e-10:
                is_valid = False
                break
                
        if is_valid:
            valid_hits.append(hit)
            
    print(f"Filtered {len(hits)} hits down to {len(valid_hits)} valid entities.")
    
    with open(output_file, 'w') as f:
        json.dump(valid_hits, f, indent=2)
        
    return valid_hits

if __name__ == "__main__":
    clean_hits = clean_entity_hits("n64_entity_hits.txt", "n64_valid_entities.json")
    
    print("\nTop 10 Valid Entities:")
    for h in clean_hits[:10]:
        print(f"Offset: 0x{h['offset']:08X} | Model: {h['model_id']} | Pos: ({h['x']:.2f}, {h['y']:.2f}, {h['z']:.2f})")