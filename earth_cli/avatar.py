"""Pixelfolk avatar renderer â€” 16-bit-style pixel sprite in a neubrutalist card.

Style: STYLE.md (Minecraft x PostHog x Gumroad x GitHub). Every visual fact is
honest: body color = primary capability, accents = secondary capability,
skill-count chip and activity strip come from the verified genome. Shape,
face, and accessory vary deterministically per agent name â€” unique but
reproducible, never random.
"""

from __future__ import annotations

import hashlib
from html import escape

CELL = 10          # px per logical pixel
GRID_W, GRID_H = 18, 20
INK = "#1E1E1E"    # outline / borders
CREAM = "#FDF6EC"  # canvas
WHITE = "#FFFFFF"
SKIN = "#E9B08A"
HAIR_HEX = {
    "black": "#231F25", "brown": "#5B3D2D", "auburn": "#90412B", "gold": "#D2A446",
    "silver": "#B0B8BE", "indigo": "#49467D", "teal": "#317E79", "rose": "#9E4B63",
}
EYE_HEX = {
    "brown": "#70452D", "hazel": "#8B7137", "green": "#3C8A52", "blue": "#4895C4",
    "gray": "#7C8994", "violet": "#6F529D",
}


def _h(name: str, salt: str, mod: int) -> int:
    return int(hashlib.sha256(f"{salt}:{name}".encode()).hexdigest(), 16) % mod


def _shade(hex_color: str, factor: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#{:02X}{:02X}{:02X}".format(
        int(r * factor), int(g * factor), int(b * factor))


class Sprite:
    def __init__(self) -> None:
        self.g: list[list[str | None]] = [[None] * GRID_W for _ in range(GRID_H)]

    def fill(self, x: int, y: int, w: int, h: int, color: str) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < GRID_W and 0 <= yy < GRID_H:
                    self.g[yy][xx] = color

    def px(self, x: int, y: int, color: str) -> None:
        self.fill(x, y, 1, 1, color)

    def outline(self) -> None:
        """Give every filled region a 1px ink border on exposed edges."""
        edges = []
        for y in range(GRID_H):
            for x in range(GRID_W):
                if self.g[y][x] is None:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < GRID_W and 0 <= ny < GRID_H) or self.g[ny][nx] is None:
                        edges.append((nx, ny))
        for x, y in edges:
            if 0 <= x < GRID_W and 0 <= y < GRID_H:
                self.g[y][x] = INK


def build_sprite(name: str, c1: str, c2: str, appearance: dict | None = None) -> Sprite:
    s = Sprite()
    appearance = appearance or {}
    dark1 = _shade(c1, 0.72)
    wide = _h(name, "head", 2)          # 0: normal, 1: wide head
    hw = 12 if wide else 10             # head width
    hx = (GRID_W - hw) // 2

    # Head (rows 2-8) and body (rows 9-14)
    s.fill(hx, 2, hw, 7, SKIN)
    s.fill(4, 9, 10, 6, c1)
    # Side shading (right edge darker = chunky 3D feel)
    s.fill(12, 9, 2, 6, dark1)

    # Arms
    s.fill(2, 10, 2, 4, c1)
    s.fill(14, 10, 2, 4, dark1)

    # Legs (stance varies)
    gap = 2 + _h(name, "legs", 2)       # 2 or 3 px between legs
    lw = (10 - gap) // 2
    s.fill(4, 15, lw, 3, dark1)
    s.fill(4 + lw + gap, 15, lw, 3, dark1)

    # Face plate (cream) inside head
    s.fill(hx + 1, 3, hw - 3, 5, SKIN)

    # Complete deterministic hair. The in-world LPC renderer uses the same
    # stored appearance fields with its higher-detail licensed layers.
    hair_style = str(appearance.get("hairStyle", "bangs"))
    hair = HAIR_HEX.get(str(appearance.get("hairColor", "brown")), HAIR_HEX["brown"])
    s.fill(hx, 1, hw, 2, hair)
    if hair_style in {"afro", "curly_short", "natural"}:
        s.fill(hx - 1, 2, hw + 2, 2, hair)
        s.px(hx, 0, hair); s.px(hx + hw - 1, 0, hair)
    elif hair_style in {"long", "dreadlocks_short", "bob"}:
        s.fill(hx, 2, 2, 7, hair); s.fill(hx + hw - 2, 2, 2, 7, hair)
    elif hair_style in {"bangs", "curtains", "parted", "pixie", "spiked"}:
        s.fill(hx + 1, 3, max(2, hw // 2), 1, hair)
        if hair_style == "spiked":
            s.px(hx + 2, 0, hair); s.px(hx + hw - 3, 0, hair)

    # Eyes: 0 square 2x2, 1 tall 2x3, 2 visor strip
    eye = _h(name, "eye", 3)
    iris = EYE_HEX.get(str(appearance.get("eyeColor", "blue")), EYE_HEX["blue"])
    ey = 4
    if eye == 2:
        s.fill(hx + 2, ey, hw - 5, 2, INK)
        s.px(hx + 3, ey, iris)
    else:
        eh = 2 if eye == 0 else 3
        s.fill(hx + 2, ey, 2, eh, INK)
        s.fill(hx + hw - 5, ey, 2, eh, INK)
        s.px(hx + 2, ey, iris)
        s.px(hx + hw - 5, ey, iris)

    # Mouth: 0 smile, 1 flat, 2 open
    mouth = _h(name, "mouth", 3)
    my = 7
    mid = hx + hw // 2
    if mouth == 0:
        s.px(mid - 2, my - 1, INK)
        s.fill(mid - 1, my, 2, 1, INK)
        s.px(mid + 1, my - 1, INK)
    elif mouth == 1:
        s.fill(mid - 1, my, 3, 1, INK)
    else:
        s.fill(mid - 1, my - 1, 2, 2, INK)

    # Chest emblem: 3x3 pattern from hash bits, secondary color
    bits = _h(name, "emblem", 512)
    for i in range(9):
        if bits >> i & 1:
            s.px(7 + i % 3, 10 + i // 3, c2)

    s.outline()
    return s


def render_avatar(identity: dict) -> str:
    name = identity["persona"].get("name", "agent")
    safe_name = escape(str(name), quote=True)
    c1 = identity["colors"]["primary"]
    c2 = identity["colors"]["secondary"]
    skill_count = identity["genome"]["skill_count"]
    families = identity["genome"].get("families", {})
    primary_category = identity["genome"].get("primary_category", "general")
    experience = identity["genome"].get("experience_tier", "emerging")
    resident = identity.get("stage") != "sprout"

    appearance = identity.get("avatar", {})
    sprite = build_sprite(name, c1, c2, appearance)

    # Card geometry (neubrutalist: hard shadow, thick border, flat fills)
    card_w, card_h = 260, 322
    ox, oy = 40, 34                     # sprite origin inside card

    rects = []
    for y in range(GRID_H):
        for x in range(GRID_W):
            col = sprite.g[y][x]
            if col:
                rects.append(
                    f'<rect x="{ox + x * CELL}" y="{oy + y * CELL}" '
                    f'width="{CELL}" height="{CELL}" fill="{col}"/>')

    # Activity strip: one pixel per capability family, height-coded (GitHub-style)
    strip = []
    fam_items = list(families.items())[:9]
    max_c = max((c for _, c in fam_items), default=1)
    for i, (_fam, count) in enumerate(fam_items):
        lvl = max(1, round(count / max_c * 4))
        opacity = 0.25 + lvl * 0.1875
        strip.append(
            f'<rect x="{30 + i * 16}" y="272" width="12" height="12" '
            f'fill="{c1}" opacity="{opacity:.2f}" stroke="{INK}" stroke-width="1.5"/>')

    aura = (
        f'<rect x="24" y="22" width="212" height="216" fill="none" '
        f'stroke="{c2}" stroke-width="2" stroke-dasharray="8 6" opacity="0.5"/>'
        if resident else "")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {card_w + 14} {card_h + 14}"
     width="{card_w + 14}" height="{card_h + 14}" shape-rendering="crispEdges">
  <!-- hard offset shadow -->
  <rect x="12" y="12" width="{card_w}" height="{card_h}" fill="{INK}"/>
  <!-- card -->
  <rect x="4" y="4" width="{card_w}" height="{card_h}" fill="{CREAM}"
        stroke="{INK}" stroke-width="3"/>
  {aura}
  <!-- sprite -->
  {"".join(rects)}
  <!-- skill-count chip -->
  <g>
    <rect x="196" y="16" width="52" height="26" fill="{c2}" stroke="{INK}" stroke-width="3"/>
    <text x="222" y="34" text-anchor="middle" font-family="Consolas, monospace"
          font-size="14" font-weight="700" fill="{CREAM}">{int(skill_count)}</text>
  </g>
  <!-- nameplate -->
  <rect x="30" y="240" width="200" height="3" fill="{INK}"/>
  <text x="30" y="264" font-family="Consolas, monospace" font-size="17"
        font-weight="700" fill="{INK}">{safe_name}</text>
  <!-- activity pixel strip (real capability spread) -->
  {"".join(strip)}
  <text x="30" y="306" font-family="Consolas, monospace" font-size="9"
        fill="{INK}" opacity="0.65">{escape(str(appearance.get("hairStyle", "hair")))} / {escape(str(appearance.get("eyeColor", "eyes")))}</text>
  <text x="230" y="306" text-anchor="end" font-family="Consolas, monospace"
        font-size="9" font-weight="700" fill="{INK}">{primary_category} · {experience}</text>
</svg>'''
