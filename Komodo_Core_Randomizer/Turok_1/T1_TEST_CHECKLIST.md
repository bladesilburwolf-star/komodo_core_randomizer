# Turok 1 — test checklist (while tooling continues)

## Spawns
1. Preset **All** — confirm menu/loading not in pool
2. Preset **Boss rush** — only arena warps (~25)
3. Preset **No bosses** — campaign without arenas

## Sec4 objects
1. **Values only** — knife elites in Campaign/Lost Land; note if HP/damage shifted
2. **Scale only** — look for tiny/giant enemies/props (`+20` float)
3. **Scale+Values** — combined chaos
4. **Swap** — redistribute existing amounts only

```
python t1_tool.py shuffle-sec4 Cartdata.dat --mode scale --seed 42 -o scale42.dat
python t1_tool.py shuffle-spawns Cartdata.dat --preset boss --seed 7 -o boss7.dat
```

## Report back
- Did scale actually change enemy/prop size?
- Values mode: knife TTK change?
- Any crash sections / softlocks?
