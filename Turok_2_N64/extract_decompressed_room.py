#!/usr/bin/env python3
"""
Extracts and decompresses a single Section 5 room block from the PC .lss
using the new pure-Python RNC module, so we can inspect the raw struct in HxD.
"""
import struct
from pathlib import Path

# Import the new RNC module you provided
try:
    from rnc import unpack_le
except ImportError:
    print("ERROR: Could not import 'rnc' module.")
    print("Make sure the 'rnc' folder (with __init__.py, unpack.py, etc.) is in the same directory.")
    exit(1)

def extract_and_decompress(lss_path: str):
    data = Path(lss_path).read_bytes()
    
    # 1. Parse LSS Header to find Section 5
    section_count = struct.unpack_from("<I", data, 0)[0]
    header_size = struct.unpack_from("<I", data, 4)[0]
    
    # Get the end offsets for all sections
    ends = [struct.unpack_from("<I", data, 8 + i * 4)[0] for i in range(section_count)]
    
    # Calculate Section 5 start and end
    sec5_start = header_size if 5 == 0 else ends[4]
    sec5_end = ends[5]
    sec5_data = data[sec5_start:sec5_end]
    
    print(f"Section 5 Size: {len(sec5_data)} bytes")
    
    # 2. Parse Section 5 Header (Array of block offsets)
    n_blocks = struct.unpack_from("<I", sec5_data, 0)[0]
    offsets = [struct.unpack_from("<I", sec5_data, 4 + i * 4)[0] for i in range(n_blocks)]
    
    print(f"Found {n_blocks} sub-blocks in Section 5.")
    
    # 3. Find the first block that actually contains RNC data
    for i in range(n_blocks):
        start_off = offsets[i]
        end_off = offsets[i + 1] if i + 1 < n_blocks else len(sec5_data)
        sub = sec5_data[start_off:end_off]
        
        if b"RNC" in sub:
            rnc_idx = sub.find(b"RNC")
            rnc_payload = sub[rnc_idx:]
            
            print(f"\nFound RNC data in Block {i} at offset 0x{start_off + rnc_idx:06X}")
            print(f"Compressed size: {len(rnc_payload)} bytes")
            
            # 4. Decompress using the new module
            try:
                decompressed = unpack_le(rnc_payload)
                print(f"Decompressed size: {len(decompressed)} bytes")
                
                # 5. Save to a file for HxD inspection
                output_file = "decompressed_room.bin"
                Path(output_file).write_bytes(decompressed)
                print(f"\nSUCCESS! Saved to: {output_file}")
                print("Open this file in HxD. You should now see clean, readable floats and model IDs.")
                return
                
            except Exception as e:
                print(f"Decompression failed: {e}")
                print("Trying next block...")
                
    print("No RNC blocks found or all failed to decompress.")

if __name__ == "__main__":
    # Update this path to your actual LSS file
    lss_file = "C:/GOG/Turok2/Data/bak/Grok/seeds.lss"
    if Path(lss_file).exists():
        extract_and_decompress(lss_file)
    else:
        print(f"File not found: {lss_file}")