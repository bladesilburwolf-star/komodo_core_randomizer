# Turok Evolution PC — ATI format (reverse engineering)

**ATI = Actor Instance table** for a level. Uncompressed. Sibling files: `.atr` (actor resource/template), `.mtf` (mesh/geometry, ELIF/FILE).

Analyzed across chapters 1–3: **12 ATI files**, **5467** actor instances, **201** unique `.atr` paths.

---

## File header

```
offset  size  field
0       1     version? (always 0x01)
1       3     magic "ati"
4       2     unknown (varies per level, e.g. 0x0042)
6       2     unknown / related to count
…
then length-prefixed chunks starting with actor records
```

Not a simple flat array — stream of **tagged actor records**.

---

## Actor record

```
u8     0x05
char   "ACTOR" 
u8     0x00
u8     path_len          # strlen of path, no null included in count? 
                         # observed: path_len == strlen(path) and path followed by 0x00
char   path[path_len]    # e.g. Y:\Data\Actors\Enemies\...
u8     0x00
…property stream…
```

Path is a Windows-style absolute path under `Y:\Data\Actors\...`.  
Randomizer path-swap rewrites `path_len` + path bytes (same-length safe, or splice with care).

---

## Property stream

After the path null, a typed property list:

### Header
Often begins with `45 01 01` (block/version marker).

### ID (special)
```
02 49 44 00  <u8 id>
```
`ID` tag + 8-bit instance id (not always unique across file).

### String property (`0x4B`)
```
4B  <flags>  <value_size>  <name_len>
name[name_len]  0x00
value[value_size]           # usually includes trailing 0x00
```
Examples: `NAME` = `"Iguana"`, `INITIALSTATE` = `"wander"`.

### Float vector property (`0x4A`)
```
4A  <flags>  <data_size>  <name_len>
name[name_len]  0x00
float32[data_size/4]        # LE
```
Common:
| Name | Size | Meaning |
|------|------|---------|
| **POS** | 12 | world position X,Y,Z |
| **ROT** | 12 | rotation (often degrees-like on Y) |
| **SCALE** | 12 | XYZ scale (1,1,1 default; also 0.8, 1.2, 1.5, 2.0, 30…) |
| WPTIME | 4 | waypoint timing |

### Nested block (`0x61`)
```
61  <flags>  <u16 size?>  00  <name_len>
name[name_len]  0x00
…child properties…
```
Most important child block: **`ACTOR_VARIABLES`**

### End
Byte `0x42…` appears as a terminator in some records; next record is another `05 ACTOR`.

---

## ACTOR_VARIABLES (examples)

| Key | Example | Role |
|-----|---------|------|
| IGNOREPLAYER | True/False | AI |
| PROVOKEONLY | True | AI |
| LEASHEDTOREGION | True | AI region lock |
| INITIALSTATE | wander | AI FSM |
| WPTIME | 4.0 | waypoint |
| HEALTH | (string/num) | health override |
| STAMN / STSPD / … | various | stance / speed params |
| GIBDEATH / GIBPART | | gib setup |
| LDSOUND / MDSOUND / HDSOUND | | damage sounds |

Variable sets differ by actor type (soldiers vs wildlife vs props).

---

## Categories (instance counts, ch1–3)

| Category | Count | Notes |
|----------|------:|-------|
| Environments | 3315 | foliage, collision, water |
| Regions | 591 | Box triggers/regions |
| Pickups | 340 | health, ammo (**exclude keys**) |
| IndigenousLife | 323 | ambient critters |
| Enemies | 249 | dinos, vehicles |
| AIObjects | 180 | |
| EnemyVariations | 156 | soldiers, scouts, raptors |
| NULLACTOR | 110 | placeholders |
| Lights / Cameras / Weapons / Players | fewer | |

**Enemy-ish total ~405** (Enemies + EnemyVariations).

---

## SCALE distribution (observed)

| Scale | Count (approx) |
|------:|---------------:|
| (1,1,1) | ~2756 |
| (2,2,2) | ~120 |
| (1.2,1.2,1.2) | ~40 |
| (1.5,…) (0.8,…) | ~30 each |
| (30,30,30) | ~35 (likely volumes/regions) |

**SCALE is a first-class mod target** (tiny/giant enemies without EXE cheats).

---

## Randomizer / mod implications

1. **Path swap** (existing `te_tool.py`) — change actor class; keep POS/ROT/SCALE/variables.  
2. **SCALE chaos** — rewrite SCALE floats only (safe visual/gameplay chaos).  
3. **POS shuffle** within category — teleport enemies among enemy slots.  
4. **ACTOR_VARIABLES** — HEALTH / INITIALSTATE / AI flags for behavior mods.  
5. **Keys** — never shuffle `Tarkeen_Key` / Misc progression pickups (freeze/softlock).

---

## Related files

| Ext | Role |
|-----|------|
| `.ati` | Instance placements + overrides (this doc) |
| `.atr` | Actor template/resource (referenced by path) |
| `.mtf` | Level mesh (ELIF/FILE chunks) |

ATR/MTF RE is separate; ATI only **points** at ATR paths.
