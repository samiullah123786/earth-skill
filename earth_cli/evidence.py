"""Local evidence-card lookup and conservative GitHub reference verification."""

from __future__ import annotations

import json
import hashlib
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY_PATH = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def normalize_github_repository(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    match = REPOSITORY_PATH.match(parsed.path)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or not match:
        raise ValueError("repository must identify one https://github.com/<owner>/<repo> project")
    return f"https://github.com/{match.group(1)}/{match.group(2)}"


def verify_github_repository(value: str | None) -> str | None:
    """Verify that a normalized repository page exists without downloading code."""
    repository = normalize_github_repository(value)
    if not repository:
        return None
    request = urllib.request.Request(repository, headers={
        "User-Agent": "AgentsEarth-Evidence/1.0",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise ValueError(f"GitHub returned HTTP {response.status}")
            final = normalize_github_repository(response.geturl())
            if final != repository:
                raise ValueError("GitHub redirected to a different repository")
    except (urllib.error.URLError, TimeoutError) as error:
        raise ValueError(f"could not independently verify GitHub repository: {error}") from error
    return repository


def skill_evidence(home: str | Path, skill_name: str) -> dict:
    path = Path(home) / "genome-evidence.json"
    if not path.exists():
        raise ValueError("local genome evidence is missing; run Earth genesis first")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    wanted = skill_name.strip().lower()
    for skill in evidence.get("skills", []):
        if str(skill.get("name", "")).lower() == wanted:
            digest = str(skill.get("digest", "")).lower()
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("local skill evidence digest is invalid")
            local_path = Path(str(skill.get("local_path", ""))) if skill.get("local_path") else None
            if not local_path or not local_path.is_file():
                from .genesis import default_skill_dirs, discover_skills
                current = next((item for item in discover_skills(default_skill_dirs())
                                if item.get("name", "").lower() == wanted and item.get("digest") == digest), None)
                local_path = Path(current["local_path"]) if current else None
            if not local_path or not local_path.is_file():
                raise ValueError("local skill source is unavailable or changed; rerun Earth genesis before sharing")
            current_digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
            if current_digest != digest:
                raise ValueError("local skill changed after genesis; rerun Earth genesis before sharing its evidence card")
            categories = skill.get("categories")
            if not categories:
                from .genesis import skill_categories
                content = local_path.read_text(encoding="utf-8", errors="ignore")
                categories = skill_categories({"name": skill.get("name", skill_name), "description": "", "content": content})
            return {**skill, "digest": digest, "categories": categories,
                    "repository": normalize_github_repository(skill.get("repository"))}
    raise ValueError(f"{skill_name!r} is not present in this agent's local genesis evidence")
