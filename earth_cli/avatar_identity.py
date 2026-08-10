"""Evidence-aware, deterministic public avatar identity for AgentsEarth."""

from __future__ import annotations

import hashlib


HAIR_STYLES = (
    "afro", "bangs", "bob", "buzzcut", "curly_short", "curtains",
    "dreadlocks_short", "long", "natural", "parted", "pixie", "spiked",
)
HAIR_COLORS = ("black", "brown", "auburn", "gold", "silver", "indigo", "teal", "rose")
EYE_COLORS = ("brown", "hazel", "green", "blue", "gray", "violet")
MALE_HEADS = ("male", "male_gaunt", "male_plump", "male_small")
FEMALE_HEADS = ("female", "female_small")
ARCHETYPE_BY_CATEGORY = {
    "frontend": "engineering", "backend": "engineering", "automation": "engineering",
    "data": "scholar", "research": "scholar", "security": "civic",
    "ui": "creative", "ux": "creative", "media": "creative", "content": "creative",
    "growth": "civic", "general": "civic",
}
ARCHETYPE_BY_FAMILY = {
    "engineering": "engineering", "data": "scholar", "research": "scholar",
    "design": "creative", "media": "creative", "content": "creative",
    "security": "civic", "ops": "civic", "marketing": "civic",
}
OUTFIT_COLORS = {
    "engineering": ("blue", "brown", "forest", "red"),
    "creative": ("red", "brown", "blue", "forest"),
    "scholar": ("forest", "blue", "brown", "red"),
    "civic": ("brown", "forest", "blue", "red"),
}


def avatar_archetype(primary_category: str, families: dict | None = None) -> str:
    category = str(primary_category or "general").lower()
    if category in ARCHETYPE_BY_CATEGORY:
        return ARCHETYPE_BY_CATEGORY[category]
    first_family = next(iter(families or {}), "general")
    return ARCHETYPE_BY_FAMILY.get(str(first_family).lower(), "civic")


def derive_avatar_identity(identity: dict, public_key: str) -> dict[str, str | int]:
    """Select a reproducible appearance from verified capability evidence.

    This is public appearance metadata only. It never contains local paths,
    private owner data, raw skill contents, or authority claims.
    """
    persona = identity.get("persona", {})
    genome = identity.get("genome", {})
    gender = str(persona.get("gender", "male")).lower()
    if gender not in {"male", "female"}:
        gender = "male"
    evidence = str(genome.get("evidence_digest", ""))
    seed = hashlib.sha256(f"{public_key}:{evidence}:{persona.get('name', 'agent')}".encode()).digest()
    variant = int.from_bytes(seed[:2], "big") % 16
    archetype = avatar_archetype(str(genome.get("primary_category", "general")), genome.get("families"))
    archetype_index = ("engineering", "creative", "scholar", "civic").index(archetype)
    hair_style = HAIR_STYLES[variant % len(HAIR_STYLES)]
    hair_color = HAIR_COLORS[(variant * 5 + archetype_index) % len(HAIR_COLORS)]
    heads = FEMALE_HEADS if gender == "female" else MALE_HEADS
    head_shape = heads[(variant // 2) % len(heads)]
    outfit_color = OUTFIT_COLORS[archetype][(variant * 3 + archetype_index) % 4]
    eye_color = EYE_COLORS[(variant * 7 + archetype_index) % len(EYE_COLORS)]
    return {
        "version": 1,
        "catalogKey": f"citizen_{gender}_{archetype}_{variant:02d}",
        "archetype": archetype,
        "variant": variant,
        "hairStyle": hair_style,
        "hairColor": hair_color,
        "headShape": head_shape,
        "outfitColor": outfit_color,
        "eyeColor": eye_color,
        "selectionBasis": "verified-capabilities",
    }
