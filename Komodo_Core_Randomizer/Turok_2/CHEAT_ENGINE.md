# Turok 2 PC — Cheat / debug surface (from Turok2MP.exe strings)

SP (`Turok2.exe`) is heavily string-stripped; **MP retains the full cheat UI and status text**. Same engine family — flags almost certainly exist in SP even if labels are gone.

## Pause menu path
`cheats` → `enter cheat` → typed codes → `new cheat enabled` / `… activated`

## Built-in modes (status lines on/off)

| Mode | Notes |
|------|--------|
| invincibility | |
| infinite lives | |
| all weapons | |
| unlimited ammo | |
| all special objects | keys / mission objects |
| **big head mode** | scale heads — exact “enemy size” cheat track |
| **tiny mode** | global scale down |
| **stick mode** | skinny/stick figures |
| **big hands / feet mode** | |
| pen and ink mode | render style |
| gouraud mode | render style |
| juans cheat | |
| zach attack cheat | |
| all map | |
| **blackout** | native blackout mode (matches our “blackout boss” idea) |
| frooty stripes | `mmmm... tasty frooty stripes` |

## Warp cheats
- Port of Adia, River of Souls, Death Marshes, Lair of the Blind Ones, Hive of the Mantids, Primagen's Lightship
- Queen / Blind One / Mother / Primagen **boss** warps
- Credits

## Blood
`blood color : off | red | green` (+ blue blood score strings)

## Debug channels
```
debug : off | on | vis | ais | snd | links
-- DEBUG --
DebugMaster / DebugChild / DebugObject / DebugFilter / DebugNetwork
```

## CLI (MP)
`-EnableF12ScreenGrab` `-enableInputStats` `-lan` `-Benchmark` `-FrameRate` `-FrameTime` …

## Attribute / multiplier config keys (MP, likely .ini / registry style)
```
\TurokAttribs\  \AdonAttribs\  \RaptorAttribs\ …
\SpeedMultiplier\%f
\DamageMultiplier\%f
\ArenaWeapons\  \ArenaMaxAmmo\  \EnemiesDropWeapons\  \WeaponsRemain\
```

## How this ties to Section 2 + spawn rando

Section 2 model tags re-resolve **on death, respawn, and save-portal transitions**. That is the same window where:

1. Cheat scale modes (big head / tiny / stick) re-apply to newly loaded models  
2. Spawn shuffle can drop you into a boss arena **with** blackout / big-head already armed  
3. A future randomizer can **schedule** cheat flags at those transitions instead of only at boot

**Design:**
- Seed bits → enable subset of cheat flags (toybox preset)
- On boss-map spawn → force `blackout` + optional `big head`
- Section 2 whitelist tag chaos **plus** tiny/big-head = attribute chaos without rewriting every mesh
- `DamageMultiplier` / sec11 damage findings reinforce each other

## Next RE steps
1. Locate cheat flag bytes in process (MP with debugger) or static xrefs from status strings  
2. Patch SP EXE or inject at load to set flags without typing codes  
3. Optional: write flags into a save slot so death/respawn reloads them cleanly with sec2


## Cheat flag bitfield (Turok2MP.exe, static RE)

**Address (VA): `0x005D5A60`** — `DWORD` bitfield in `.data`  
(Neighbor `0x5D5A64` also heavily referenced — secondary flags / pen-ink / frooty candidates.)

| Bit mask | Mode |
|---------:|------|
| `0x0001` | (related toggle — verify in-game) |
| `0x0002` | invincibility |
| `0x0004` | infinite lives |
| `0x0008` | all weapons |
| `0x0010` | unlimited ammo |
| `0x0020` | all special objects |
| `0x0040` | **big head mode** |
| `0x0080` | **tiny mode** |
| `0x0100` | **stick mode** |
| `0x0200` | (gap — likely pen & ink; confirm) |
| `0x0400` | big hands / feet |
| `0x0800` | gouraud mode |
| `0x1000` | juans cheat |
| `0x2000` | zach attack cheat |
| `0x4000` | all map |
| `0x8000` | **blackout** |

Toggle code pattern (each mode):
```asm
mov eax, [0x5D5A60]
xor eax, <mask>
mov [0x5D5A60], eax
```

**Randomizer use:** external injector / trainer / ASI at boot or on death can OR these masks. SP build: same layout is likely (strings stripped, addresses may shift — signature-scan the xor mask sequence).

**Toybox presets (proposed):**
- `scale_chaos` = big head | tiny | stick | big hands (`0x40|0x80|0x100|0x400`)
- `blackout_boss` = blackout | big head (`0x8000|0x40`)
- `player_power` = invincibility | all weapons | unlimited ammo (`0x2|0x8|0x10`)
- `full_toybox` = all known bits


## Implementation (shipped)

### Live trainer (Windows)
```
python t2_cheats.py list
python t2_cheats.py status
python t2_cheats.py apply --preset blackout_boss
python t2_cheats.py apply --bits big_head,0x8000 --or
python t2_cheats.py clear
python t2_cheats_gui.py
```
Writes DWORD at `module_base + 0x1D5A60` in the running process.

### Static mod (any OS)
```
python t2_cheats.py patch-exe Turok2MP.exe --preset scale_chaos -o Turok2MP_scale.exe
```
Patches `mov dword [0x5D5A60], imm32` so the chosen bits are the **default** when that init runs.

### Combine with randomizer
1. Generate LSS (spawn preset boss / all / particles).
2. Apply toybox via live trainer **or** boot patched MP EXE.
3. Die / portal → sec2 model rebind + cheat scales still active.

### SP note
`Turok2.exe` is string-stripped and does not share the same absolute addresses. Next: signature-scan for the `xor` mask ladder under a debugger. Until then, **MP is the supported mod host**.
