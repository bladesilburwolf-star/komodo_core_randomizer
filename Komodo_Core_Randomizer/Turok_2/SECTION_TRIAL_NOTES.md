# Turok 2 LSS — In-game section trial notes

From experimental scrambles + structure scans (2026-09-13).

## Summary table

| Sec | Size | Safe? | In-game effect | Structure |
|-----|------|-------|----------------|-----------|
| **2** | 4.8 KB | Soft (despawns) | **Enemies, buildings, map pieces, keys, health, pickups vanish** between save-portals / death | 2429 model **type tags** (u16) |
| **4** | 122 KB | Yes | Particles chaos (weapons FX, blood, claw, portals, +FPS) | 722 particle systems |
| **7** | 17 KB | **Crash** | Crash in room with **first key** | 146×592-related table |
| **8** | 5 KB | Yes | Spawns/warps (known rando) | Position records |
| **11** | 8 KB | Mostly | **More damage taken**; crash after lever→gate before 2nd child save | 91 entries (72 or 120 bytes) — stats/scripts candidate |
| **18** | 104 KB | Careful | **Story, cutscenes, Adon**, flythroughs, endings, totems | 198 named cinema/script chunks |
| **19** | 424 B | **Crash** | Crash in key rooms; **progression flags** | Tiny flag/index table |

## Section 2 — model type tags (HIGH VALUE)

```
u32 unk = 2
u32 model_count = 2429
u16 tags[2429]
```

Tag histogram (vanilla): geometry-heavy tags 1/5/7 dominate; 1601/1602/1608/1609 are actor groups (see enemy_catalog).

**Scramble effect:** models fail to resolve after reload/death/portal → enemies, architecture pieces, keys, and pickups **disappear**. Confirms this table is the **model-class index** the engine uses for streaming / respawn / persistence.

**Rando ideas (careful):**
- Whitelist-only tag swaps within enemy groups (1601↔1602) — still deny 1608 bulk + boss-proximity models
- Do **not** scramble geometry tags 1/5/7 (map pieces vanish)
- Key/pickup tags once identified → progression-safe pools only

## Section 4 — particles

See `SECTION4_PARTICLES.md`. Isolation via `--ids` / `--type` / `--index`.

## Section 7 — UNSAFE

Crash when entering first-key room. Leave experimental toggle **off** by default. Structure looks like offset list + 146-byte records (rcnt field 592 — verify before any poke).

## Section 11 — damage / scripts candidate

91 variable entries (72 or 120 bytes). Floats/half-float-like u16 patterns.  
In-game: player takes **more damage**; rare crash on gate script before 2nd child.  
Good for **damage multiplier chaos** once fields are labeled; until then treat as experimental.

## Section 18 — cinema / story (REALLY BIG)

198 chunks with embedded names, e.g.:
- `mother start cine A/B/C`, `Primagen Death`, `End Credits`
- `Gstart-adon-speech1`, `save-adon`, `TAL-Adon`
- `L1-mission totem`, `Gstart-play level 1`, level end sequences
- Flythroughs: swamp/hive/flesh

**Rando ideas:** skip intro cinemas, shuffle Adon speech order (cosmetic), boss intro variants — **do not** scramble blindly (story softlocks).

## Section 19 — progression flags (UNSAFE)

424-byte table of mostly `1`s with sparse other indices (2–12). Crash in key rooms → almost certainly **key/progression state**. Do not scramble for playable seeds.

## Policy for GUI experimental toggles

| Sec | Default | Label |
|-----|---------|-------|
| 2 | off | Model tags (despawn risk) |
| 4 | off | Particles chaos (known safe-ish) |
| 7 | **blocked** | Crash — first key |
| 11 | off | Damage/scripts experimental |
| 18 | **blocked** | Story/cinema — manual only |
| 19 | **blocked** | Progression — crash |


## Policy update (user report)

- **Many sections crash on load** when scrambled → default **blocklist** is large.
- **Meta / empty-looking sections** — no observed effect so far; still blocked from auto-scramble.
- **Allow experimental scramble only for:** sec4 (particles), sec11 (damage/scripts).
- **Sec2** soft opt-in only (model despawn).
- **Sec8** uses dedicated spawn rando, not experimental scramble.

Focus shifts to: **cheat bitfield + spawn presets + sec4 isolation + careful sec2**.
