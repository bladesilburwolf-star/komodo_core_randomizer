# Turok 2 LSS Level Format Notes (WIP)

## Section overview
| Idx | Name | Notes |
|-----|------|-------|
| 0 | models | 2429 model entries |
| 1 | actor_attrs | 1291 attribute *templates* (class+model+stats), NOT placements |
| 2 | actor/model map? | ties to model count 2429 |
| 5 | levels | 146 map blocks |
| 6/7 | per-map meta | 146 entries aligned with map count |
| 8 | warps_spawns | **uncompressed** position records (spawn randomizer works here) |

## Section 1 actor templates
- Header: class (u32) + model_id (u32) + scale 512.0f + flags
- Class determines record size (32–160 bytes)
- Only ~20 unique model IDs across 1291 templates
- These define *what* an actor is, not *where* it is placed

## Section 5 map block layout (9-part directory)
```
u32 part_count = 9
u32 offsets[9]
```
| Part | Contents |
|------|----------|
| 0 | 24-byte header |
| 1 | **RNC** compressed geometry (internal tags 100/16/20) |
| 2 | Nested sector/node data |
| 3 | Counted 40-byte records (mostly fill/geometry patterns) |
| 4 | 5 sub-lists; sub[4] has many positions (spatial?) |
| 5 | Room hierarchy (largest uncompressed part) |
| 6 | Fixed ~712 bytes |
| 7 | Variable nested lists |
| 8 | Trailing name/string bytes |

### RNC internal (part 1 unpacked)
| Tag | Record size | Role |
|-----|-------------|------|
| 100 | ~100 B | palette/fill patterns |
| 16 | 16 B | geometry indices |
| 20 | 20 B | geometry verts |

## Item IDs (from Turok2MP.exe UI tables)
Confirmed UI-side only (not yet proven as level placement IDs):
- plane walker 0x14D, invincibility 0x14E, flashlight 0x14F
- eagle feather 0x150, full health 0x154, ultra health 0x155
See item_catalog.json for full weapon/ammo/quest name lists.

## Blockers for enemy/weapon/ammo randomizer
1. Entity *placement* records not yet identified as clean type+xyz arrays
2. UI type IDs appear in level blobs but not as structured entity fields
3. Section 1 is templates only — need the instance/placement layer

## Working features
- Section 8 spawn/warp shuffle (sector-aware, 213 records)
- Pure-Python RNC unpack + pack (LE headers, round-trip verified)
- In-place RNC replace when new size <= old
