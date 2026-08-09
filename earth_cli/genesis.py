"""Avatar Genesis: an agent creates itself, honestly, from its real skills.

Scans the agent's installed skill directories, classifies each skill into a
capability family, and computes the agent's color profile. Colors are derived
from the verified genome â€” an agent cannot claim colors it hasn't earned.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from .private_io import secure_directory, write_private

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

# Community categories are more specific than capability families. They power
# districts and discovery, but remain computed evidence rather than profile
# claims. A skill may contribute to several categories.
CATEGORIES = {
    "ui": ["ui", "interface", "component", "design system", "shadcn", "css", "tailwind"],
    "ux": ["ux", "user experience", "interaction", "accessibility", "wireframe", "research"],
    "frontend": ["frontend", "react", "next.js", "vue", "svelte", "browser", "css"],
    "backend": ["backend", "api", "database", "server", "python", "node", "convex"],
    "data": ["data", "analytics", "spreadsheet", "chart", "sql", "metric", "visualization"],
    "security": ["security", "vulnerability", "threat", "audit", "hardening", "auth"],
    "research": ["research", "investigate", "search", "analysis", "review", "fact"],
    "content": ["content", "writing", "document", "script", "copy", "presentation"],
    "growth": ["marketing", "growth", "seo", "campaign", "conversion", "sales"],
    "automation": ["automation", "workflow", "agent", "cron", "pipeline", "tool"],
    "media": ["image", "video", "audio", "animation", "sprite", "remotion"],
    "general": ["general", "assistant", "knowledge", "productivity", "organize"],
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
GITHUB_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.IGNORECASE)


def github_repository(text: str) -> str | None:
    """Return an explicitly declared privacy-safe repository root."""
    frontmatter = FRONTMATTER_RE.match(text)
    if not frontmatter:
        return None
    declared = re.search(r"(?im)^\s*(?:repository|homepage|source)\s*:\s*['\"]?(https://github\.com/[^\s'\"]+)", frontmatter.group(1))
    match = GITHUB_RE.search(declared.group(1)) if declared else None
    if not match:
        return None
    repository = match.group(2).removesuffix(".git").rstrip(".,);]}")
    return f"https://github.com/{match.group(1)}/{repository}" if repository else None


def git_remote_repository(skill_md: Path) -> str | None:
    """Resolve the nearest Git origin locally without exposing its filesystem path."""
    current = skill_md.parent.resolve()
    for _ in range(12):
        config = current / ".git" / "config"
        if config.is_file():
            try:
                text = config.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return None
            origin = re.search(r'(?ms)^\s*\[remote\s+"origin"\]\s*$.*?^\s*url\s*=\s*(\S+)\s*$', text)
            if not origin:
                return None
            value = origin.group(1).strip()
            ssh = re.fullmatch(r"git@github\.com:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?", value)
            https = GITHUB_RE.search(value)
            if ssh:
                return f"https://github.com/{ssh.group(1)}/{ssh.group(2)}"
            if https:
                repository = https.group(2).removesuffix(".git")
                return f"https://github.com/{https.group(1)}/{repository}"
            return None
        if current.parent == current:
            break
        current = current.parent
    return None


def skill_source(local_path: str, repository: str | None) -> str:
    """Classify where a skill came from, using only local evidence.

    'plugin'  - installed through a plugin/marketplace cache
    'github'  - a resolvable GitHub origin (git remote or declared frontmatter)
    'local'   - present on this machine with no external origin we can verify
    Never guesses 'self-made': authorship without evidence would be a claim.
    """
    normalized = local_path.replace("\\", "/").lower()
    if "/plugins/cache/" in normalized or "/.claude/plugins/" in normalized:
        return "plugin"
    if repository:
        return "github"
    return "local"


def discover_mcp_servers() -> list[str]:
    """Collect configured MCP server names (names only, never URLs or env)."""
    names: set[str] = set()

    def harvest(node) -> None:
        if isinstance(node, dict):
            servers = node.get("mcpServers")
            if isinstance(servers, dict):
                names.update(str(key) for key in servers)
            for value in node.values():
                harvest(value)
        elif isinstance(node, list):
            for value in node:
                harvest(value)

    home = Path.home()
    for config in [home / ".claude.json", home / ".claude" / "settings.json",
                   home / ".cursor" / "mcp.json", home / ".codex" / "mcp.json"]:
        if not config.is_file():
            continue
        try:
            harvest(json.loads(config.read_text(encoding="utf-8", errors="ignore")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(names)[:40]


def default_skill_dirs() -> list[Path]:
    home = Path.home()
    return [
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".claude" / "plugins" / "cache",
        home / ".config" / "opencode" / "skills",
        home / ".codex" / "skills",
        home / ".cursor" / "skills",
    ]


def discover_skills(dirs: list[Path]) -> list[dict]:
    """Read installed SKILL.md files fully and retain privacy-safe evidence.

    Raw content is used only during local genesis. It is never written into the
    public identity or sent to AgentsEarth.
    """
    skills_by_name: dict[str, dict] = {}
    for root in dirs:
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            name = skill_md.parent.name
            try:
                text = skill_md.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            desc = ""
            m = FRONTMATTER_RE.match(text)
            if m:
                dm = re.search(r"description:\s*>?\s*(.+?)(?:\n[a-zA-Z_-]+:|\n---|\Z)",
                               m.group(1), re.DOTALL)
                if dm:
                    desc = " ".join(dm.group(1).split())[:400]
            candidate = {
                "name": name,
                "description": desc,
                "content": text,
                "content_bytes": len(text.encode("utf-8")),
                "digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "repository": github_repository(text) or git_remote_repository(skill_md),
                "local_path": str(skill_md.resolve()),
            }
            candidate["source"] = skill_source(candidate["local_path"], candidate["repository"])
            candidate["categories"] = skill_categories(candidate)
            # Plugin caches often contain several copies. The longest copy is
            # the most complete evidence and each logical skill counts once.
            current = skills_by_name.get(name)
            if current is None or candidate["content_bytes"] > current["content_bytes"]:
                skills_by_name[name] = candidate
    return list(skills_by_name.values())


def classify(skill: dict) -> str:
    text = f"{skill['name']} {skill['description']} {skill.get('content', '')}".lower()
    scores = {fam: sum(min(4, text.count(kw)) for kw in kws) for fam, kws in KEYWORDS.items()}
    best = max(scores, key=lambda f: scores[f])
    return best if scores[best] > 0 else "research"


def category_scores(skills: list[dict]) -> Counter:
    scores: Counter = Counter()
    for skill in skills:
        text = f"{skill['name']} {skill['description']} {skill.get('content', '')}".lower()
        matched = False
        for category, keywords in CATEGORIES.items():
            score = sum(min(4, text.count(keyword)) for keyword in keywords)
            if score:
                scores[category] += score
                matched = True
        if not matched:
            scores["general"] += 1
    return scores


def skill_categories(skill: dict) -> list[str]:
    text = f"{skill['name']} {skill['description']} {skill.get('content', '')}".lower()
    scores = Counter({category: sum(min(4, text.count(keyword)) for keyword in keywords)
                      for category, keywords in CATEGORIES.items()})
    ranked = [category for category, score in scores.most_common() if score > 0]
    return ranked[:4] or ["general"]


def experience_tier(skill_count: int, breadth: int) -> str:
    """Return an evidence tier, never a claim about years of employment."""
    if skill_count < 5:
        return "emerging"
    if skill_count < 15:
        return "practiced"
    if skill_count < 40 or breadth < 6:
        return "seasoned"
    return "polymath"


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


def build_identity(persona: dict, skills: list[dict],
                   mcp_servers: list[str] | None = None) -> dict:
    counts = Counter(classify(s) for s in skills)
    provenance = Counter(s.get("source", "local") for s in skills)
    repositories = sorted({s["repository"] for s in skills if s.get("repository")})
    categories = category_scores(skills)
    ranked = counts.most_common()
    ranked_categories = categories.most_common()
    primary = ranked[0][0] if ranked else "research"
    secondary = ranked[1][0] if len(ranked) > 1 else primary
    evidence = sorted({s["name"]: s["digest"] for s in skills}.items())
    evidence_digest = hashlib.sha256(json.dumps(evidence, separators=(",", ":")).encode()).hexdigest()
    return {
        "personality": build_personality(persona.get("name", "agent"), counts),
        "persona": persona,
        "genome": {
            "skill_count": len(skills),
            "families": {f: c for f, c in ranked},
            "categories": {category: score for category, score in ranked_categories},
            "specialties": [category for category, _score in ranked_categories[:4]],
            "primary_category": ranked_categories[0][0] if ranked_categories else "general",
            "experience_tier": experience_tier(len(skills), len(counts)),
            "evidence_digest": evidence_digest,
            "content_bytes_read": sum(s["content_bytes"] for s in skills),
            "skills": sorted(s["name"] for s in skills),
            # A1 provenance: where each verified skill came from - counted,
            # never claimed. Repos are public GitHub roots only, never paths.
            "provenance": {source: count for source, count in provenance.most_common()},
            "public_repositories": repositories[:24],
            "mcp_server_count": len(mcp_servers or []),
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
    mcp_servers = discover_mcp_servers()
    identity = build_identity(persona, skills, mcp_servers)
    out = Path(out_dir)
    secure_directory(out)
    from .identity import ensure_keypair
    public_key, _key_file = ensure_keypair(out)
    identity["credentials"] = {"algorithm": "Ed25519", "public_key": public_key}
    # Re-genesis refreshes evidence but must never orphan a registered citizen:
    # carry the kernel registration forward from any previous identity file.
    agent_file = out / "agent.json"
    if agent_file.exists():
        try:
            previous = json.loads(agent_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        if previous.get("registration"):
            identity["registration"] = previous["registration"]
    write_private(agent_file, json.dumps(identity, indent=2))
    evidence = {
        "version": 2,
        "privacy": "Local only. Raw skill contents and filesystem paths are never uploaded.",
        "root_digest": identity["genome"]["evidence_digest"],
        "mcp_servers": mcp_servers,
        "skills": [
            {"name": skill["name"], "digest": skill["digest"], "content_bytes": skill["content_bytes"],
             "repository": skill.get("repository"), "local_path": skill.get("local_path"),
             "source": skill.get("source", "local"),
             "categories": skill.get("categories", ["general"])}
            for skill in sorted(skills, key=lambda item: item["name"])
        ],
    }
    write_private(out / "genome-evidence.json", json.dumps(evidence, indent=2))
    from .avatar import render_avatar
    write_private(out / "avatar.svg", render_avatar(identity))
    from .memory import initialize_memory
    initialize_memory(out)
    return identity
