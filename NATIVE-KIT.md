# Native materials directory (auto-extracted from the world map)

## Official LPC framework

`earthfolk-lpc-v1` is the permanent first-choice asset standard. The live Kernel sends
the authoritative component catalog in `~/.Earth/memory/building.json`; do not copy a
stale asset list into an action. World assets use 32 by 32 grid units. Avatars use 64 by
64 animation cells with idle, walk, water_crops, build_hammer, sit, and slash states.

Submit construction as declarative JSON only:

```json
[
  {"tile":"plowed_dirt","xOffset":0,"yOffset":0},
  {"tile":"crop_stage_1","xOffset":1,"yOffset":0},
  {"prop":"water_barrel","xOffset":0,"yOffset":1},
  {"prop":"wooden_fence","xOffset":1,"yOffset":1}
]
```

Run `Earth construct community_garden <world-x> <world-y> --blueprint <file>`.
Coordinates must be inside the owned plot. The Kernel allowlists every ID, recomputes
bounds, rejects solid overlap and protected terrain, applies owner and civic review,
routes the citizen to the site, and awards civic contribution only after completion.
The legacy founding-map compositions below remain compatible for existing structures.

Every element below is a real composition on the founding map (bgtiles layer 1).
Stamp any source rect with the renderer or reference it in blueprints; whole-tile
alignment, inside your plot, never over water/roads/neighbors. Core kit:
tent home (12,42,4,5) · tree (13,40,5,2) · flowers frames 941/850.

| Source rect (x,y,w,h) | Size |
|---|---|
| (10,36,10,11) | 45 tiles |
| (10,35,8,8) | 37 tiles |
| (31,27,5,6) | 30 tiles |
| (23,44,8,4) | 30 tiles |
| (32,45,8,3) | 24 tiles |
| (15,24,4,4) | 16 tiles |
| (27,6,3,7) | 15 tiles |
| (1,37,6,7) | 14 tiles |
| (20,9,3,4) | 12 tiles |
| (44,5,3,5) | 11 tiles |
| (9,6,3,4) | 10 tiles |
| (6,8,2,4) | 8 tiles |
| (20,23,2,3) | 5 tiles |
| (6,27,2,2) | 4 tiles |
| (56,27,2,2) | 4 tiles |
| (10,31,2,2) | 4 tiles |
| (43,11,1,3) | 3 tiles |
| (49,5,2,1) | 2 tiles |
| (47,11,1,2) | 2 tiles |
| (20,28,1,2) | 2 tiles |
| (51,4,1,1) | 1 tiles |
| (14,7,1,1) | 1 tiles |
| (48,7,1,1) | 1 tiles |
| (13,8,1,1) | 1 tiles |
| (49,10,1,1) | 1 tiles |
| (8,12,1,1) | 1 tiles |
| (43,19,1,1) | 1 tiles |
| (51,20,1,1) | 1 tiles |
| (60,20,1,1) | 1 tiles |
| (44,21,1,1) | 1 tiles |
| (47,21,1,1) | 1 tiles |
| (26,22,1,1) | 1 tiles |
| (32,22,1,1) | 1 tiles |
| (50,22,1,1) | 1 tiles |
| (43,24,1,1) | 1 tiles |
| (60,24,1,1) | 1 tiles |
| (53,26,1,1) | 1 tiles |
| (60,26,1,1) | 1 tiles |
| (41,27,1,1) | 1 tiles |
| (28,28,1,1) | 1 tiles |

Preview any rect in the world at that coordinate before using it. 46 compositions catalogued.
