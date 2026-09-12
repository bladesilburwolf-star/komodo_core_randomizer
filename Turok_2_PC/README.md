# Turok 2: Seeds of Evil (PC) Randomizer

Part of the **Akklaim Randomizers** project.

## Quick start

```bash
# CLI
python t2_tool.py info "Seeds of Evil.lss"
python t2_tool.py list-spawns "Seeds of Evil.lss"
python t2_tool.py shuffle-spawns "Seeds of Evil.lss" --seed 42 -o out.lss

# GUI
python t2_gui.py
```

## What it does right now

**Spawn / warp position shuffle** (section 8 of the LSS).

The tool locates world-space position records (x, y, z floats that are followed by a facing angle) inside the warps/spawns section and randomly permutes those positions. The rest of the file structure is left intact.

This is the first, safest randomization target while we continue learning the deeper level object layouts.

## Tooling

| File        | Role                                      |
|-------------|-------------------------------------------|
| `t2_tool.py`| CLI — info, extract, list-spawns, shuffle |
| `t2_gui.py` | Simple dark-themed GUI front-end          |

### LSS top-level sections (reference)

| Idx | Role                | Size (approx) |
|-----|---------------------|---------------|
| 0   | models              | 12.7 MB       |
| 3   | textures            | 5.4 MB        |
| 4   | particles           | 120 KB        |
| 5–7 | levels              | ~6.7 MB       |
| **8** | **warps / spawns** | **5 KB**    |
| 11  | weapon effects      | 8 KB          |
| 16  | GUI textures        | 2.2 MB        |

## Assets

- `Seeds of Evil.rar` → `Seeds of Evil.lss`
- `Rok Match Levels.rar`, `TEXTURES.rar`, sound packs

Cloned originally from: https://github.com/bladesilburwolf-star/turok_2_pc_randomizer
