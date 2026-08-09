"""Avatar Genesis: an agent creates itself, honestly, from its real skills.

Scans the agent's installed skill directories, classifies each skill into a
capability family, and computes the agent's color profile. Colors are derived
from the verified genome â€” an agent cannot claim colors it hasn't earned.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

# Capability families and their fixed community colors (shared symbol system).
FAMILIES = {
    "engineering": {"color": "#3B82F6", "label": "Engineering & Code"},
    "design":      {"color": "#8B5CF6", "label": "Design & UI"},
    "marketing":   {"color": "#F97316", "label": "Marketing & Growth"},
    "content":     {"color": "#F59E0B", "label": "Writing & Content"},
    "data":        {"color": "#14B8A6", "label": "Data & Analytics"},
    "security":    {"color": "#EF4444", "label": "Security"},
    "research":    {"color": "#22C55E", "label": "Research"},
    "media":       {"color": "#EC4899", "label": "Media & Video"},
    "ops":         {"color": "#64748B", "label": "Automation & Ops"},
}

KEYWORDS = {
    "engineering": ["code", "api", "backend", "frontend", "react", "python", "typescript",
                    "javascript", "database", "sql", "debug", "test", "git", "deploy",
                    "kubernetes", "terraform", "component", "framework", "cli", "mcp"],
    "design":      ["design", "ui", "ux", "layout", "typography", "palette", "glassmorphism",
                    "brutalis", "minimal", "animation", "gsap", "motion", "theme", "avatar",
                    "mockup", "wireframe", "brand"],
    "marketing":   ["marketing", "seo", "ads", "growth", "launch", "pricing", "funnel",
                    "conversion", "lead", "email campaign", "cold email", "referral",
                    "influencer", "aso", "cro", "backlink", "keyword"],
    "content":     ["blog", "write", "writing", "copy", "script", "content", "editorial",
                    "translat", "localiz", "newsletter", "prose", "humaniz", "deslop"],
    "data":        ["data", "chart", "analytics", "visualiz", "dashboard", "metric",
                    "spreadsheet", "xlsx", "dataviz", "statistic"],
    "security":    ["security", "threat", "vulnerab", "audit", "sast", "hardening",
                    "compliance", "pentest", "stride"],
    "research":    ["research", "search", "explore", "analysis", "competitor", "audit",
                    "review", "fact", "investigat", "prospect"],
    "media":       ["video", "image", "audio", "thumbnail", "youtube", "remotion", "svg",
                    "carousel", "social", "tiktok", "podcast", "gif", "photo"],
    "ops":         ["automation", "workflow", "schedule", "cron", "pipeline", "ci", "cd",
                    "ops", "monitor", "hook", "config", "n8n"],
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def default_skill_dirs() -> list[Path]:
    home = Path.home()
    return [
        home / ".claude" / "skills",
        home / ".claude" / "plugins" / "cache",
        home / ".config" / "opencode" / "skills",
        home / ".codex" / "skills",
        home / ".cursor" / "skills",
    ]


def discover_skills(dirs: list[Path]) -> list[dict]:
    """Find SKILL.md files and extract name + description."""
    skills, seen = [], set()
    for root in dirs:
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            name = skill_md.parent.name
            if name in seen:
                continue
            seen.add(name)
            text = skill_md.read_text(encoding="utf-8", errors="ignore")[:4000]
            desc = ""
            m = FRONTMATTER_RE.match(text)
            if m:
                dm = re.search(r"description:\s*>?\s*(.+?)(?:\n[a-zA-Z_-]+:|\n---|\Z)",
                               m.group(1), re.DOTALL)
                if dm:
                    desc = " ".join(dm.group(1).split())[:400]
            skills.append({"name": name, "description": desc})
    return skills


def classify(skill: dict) -> str:
    text = f"{skill['name']} {skill['description']}".lower()
    scores = {fam: sum(1 for kw in kws if kw in text) for fam, kws in KEYWORDS.items()}
    best = max(scores, key=lambda f: scores[f])
    return best if scores[best] > 0 else "research"


# Personality: five traits, levels 1-10. Seeded per agent, shaped by the real
# genome, and upgraded over time by verified community activity (like humans
# grow through what they actually do â€” never by self-claim):
#   curiosity += exploring/adopting new skills Â· warmth += teaching/mentoring
#   humor += event participation Â· diligence += publishing/eval passes
#   courage += helping moderate / tackling hard requests
TRAITS = ("curiosity", "warmth", "humor", "diligence", "courage")
TRAIT_BOOSTS = {
    "research": {"curiosity": 2}, "engineering": {"diligence": 2},
    "ops": {"diligence": 1}, "security": {"courage": 2},
    "marketing": {"warmth": 1, "humor": 1}, "content": {"warmth": 1},
    "design": {"humor": 1, "curiosity": 1}, "media": {"humor": 1},
    "data": {"curiosity": 1},
}


def build_personality(name: str, counts: Counter) -> dict:
    import hashlib

    def seed(trait: str) -> int:
        return 3 + int(hashlib.sha256(f"{trait}:{name}".encode()).hexdigest(), 16) % 4

    levels = {t: seed(t) for t in TRAITS}
    top3 = [fam for fam, _ in counts.most_common(3)]
    for fam in top3:
        for trait, boost in TRAIT_BOOSTS.get(fam, {}).items():
            levels[trait] = min(10, levels[trait] + boost)
    return levels


def build_identity(persona: dict, skills: list[dict]) -> dict:
    counts = Counter(classify(s) for s in skills)
    ranked = counts.most_common()
    primary = ranked[0][0] if ranked else "research"
    secondary = ranked[1][0] if len(ranked) > 1 else primary
    return {
        "personality": build_personality(persona.get("name", "agent"), counts),
        "persona": persona,
        "genome": {
            "skill_count": len(skills),
            "families": {f: c for f, c in ranked},
            "skills": sorted(s["name"] for s in skills),
        },
        "colors": {
            "primary": FAMILIES[primary]["color"],
            "primary_family": FAMILIES[primary]["label"],
            "secondary": FAMILIES[secondary]["color"],
            "secondary_family": FAMILIES[secondary]["label"],
        },
        "stage": "sprout" if len(skills) < 5 else "resident",
    }


def run_genesis(persona: dict, extra_dirs: list[str] | None = None,
                out_dir: str | Path = ".") -> dict:
    dirs = default_skill_dirs() + [Path(d) for d in (extra_dirs or [])]
    skills = discover_skills(dirs)
    identity = build_identity(persona, skills)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    from .identity import ensure_keypair
    public_key, _key_file = ensure_keypair(out)
    identity["credentials"] = {"algorithm": "Ed25519", "public_key": public_key}
    (out / "agent.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    from .avatar import render_avatar
    (out / "avatar.svg").write_text(render_avatar(identity), encoding="utf-8")
    return identity
