# Turok 2 MP — Loadout / Attribute editor

## Tools
- `t2_loadout.py` — CLI
- `t2_loadout_gui.py` — dark GUI (JSON + CFG export)

## Workflow
1. Open GUI or `python t2_loadout.py template -o my.json`
2. Set global multipliers, arena health, weapon pool
3. Per-character Attribs / StartAmmo / MaxAmmo tokens
4. **Export CFG** → try as `./integrated.cfg` beside `Turok2MP.exe` or merge into MP config
5. Combine with `t2_cheats.py` toybox bits for scale/blackout/invinc

## Presets
`vanilla` · `glass_cannon` · `tank` · `speed` · `pistols_only` · `heavy`

## Notes
- Keys match format strings inside **Turok2MP.exe** (`\TurokAttribs\%s`, `\SpeedMultiplier\%f`, …).
- Character `Attribs` / ammo fields are **opaque strings** until in-game tokens are fully mapped; start with globals + ArenaWeapons.
- Evolution may get a cleaner path-based loadout editor later (ATI / multiplayer mods).
