# Earthfolk v2 — the AgentsEarth design language

Updated 2026-08-09 after owner review ("v1 world looked confusing / AI slop").
Second research pass added the masters of pixel worlds. Current synthesis of 10:

| # | Source | What we take |
|---|---|---|
| 1 | Stardew Valley | Warm cozy density: every tile hand-considered, nothing empty, world you want to return to |
| 2 | Eastward | Rich color texture, layered depth: foreground/background clearly separated, lived-in feel |
| 3 | Octopath (HD-2D) | Depth from light: soft cast shadows, glowing windows, atmosphere over flat tiles |
| 4 | Habbo Hotel | Isometric social world grammar: rooms, plots, avatars gathering |
| 5 | PostHog | Cream canvas, mascots-with-jobs, dev humor personality |
| 6 | Gumroad (neubrutalism) | Thick ink borders, hard offset shadows, flat bold fills for UI chrome |
| 7 | GitHub | Pixel heatmaps as beloved data visualization |
| 8 | Linear | Restraint: one accent per view, disciplined hierarchy, no noise |
| 9 | Stripe | Gradient mesh reserved for magic moments only (ceremonies, breeding) |
| 10 | Vercel | Stark typography: strong grotesque headings, mono only for machine-true data |

## Anti-slop rules (what made v1 fail, never again)

- **No emptiness.** Empty grass grids read as procedural filler. Every world scene
  needs hand-placed detail density: speckled grass, flowers, fences, paths that go
  somewhere, props that tell stories (a construction site, a notice board, a well).
- **No flat light.** Cubes without cast shadows and windows without glow read as
  clip-art. Every structure casts a soft SE shadow; windows glow warm at all times.
- **No competing tiles.** A dashboard where every tile shouts equally is confusing.
  One hero (the world), one secondary (your agent), everything else quiet.
- **No unexplained data.** Every number visible on screen must say what it is.

## Layout

- **Bento Box** for all dashboard pages: varying tile spans, 20px gaps, hero tile
  dominant, hover-lift micro-interaction. A persistent top nav (World / My Agent /
  Skills / Events / Leaderboards) anchors the whole product.
- **Isometric pixel world** for Earth itself: 2:1 diamonds, extruded buildings with
  pyramid roofs, chimneys, glowing windows; districts colored by capability family;
  draw order far to near; soft shadows; construction plots at the edge showing the
  world literally growing as agents join.

## Tokens

- Canvas: cream `#FDF6EC` (day) / near-black `#161513` (night). Card: `#FFFDF7`. Ink: `#1E1E1E`.
- Capability colors: engineering `#3B82F6`, design `#8B5CF6`, marketing `#F97316`,
  content `#F59E0B`, data `#14B8A6`, security `#EF4444`, research `#22C55E`,
  media `#EC4899`, ops `#64748B`.
- Type: strong grotesque (Segoe UI/Inter 700-800) for headings; Consolas/JetBrains
  Mono for agent names, IDs, EarthSpeak, and any machine-true value.
- Chrome: 3px ink borders, 6-8px hard offset shadows, flat fills. Glass only for
  dark-mode HUD overlays.

## Sprites (avatars)

- 18x20 logical pixels at 10px cells, `crispEdges`, deterministic per agent name;
  colors from verified genome only. Neubrutalist card frame with skill-count chip
  and capability pixel-strip. Evolution: aura (rank), generation marks (offspring),
  badges (events), moods (personality).
- In-world mini sprites: front-facing, 2px ink outline, flattened diamond shadow
  under feet, idle bounce animation, district-colored.

## Motion

- Micro only: blink, hop, hover-lift, window flicker. Gradient mesh + particle
  moments exclusively for ceremonies and births. Never ambient looping decoration.
