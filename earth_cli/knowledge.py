"""Owner-consented local knowledge bank: roots, scanning, and a private index.

Genesis has always read installed `SKILL.md` files. The bank widens that to the
markdown knowledge an owner explicitly points at — and no further. Three laws
hold everywhere in this module:

1. Nothing outside a consented root is ever opened. There is no home sweep and
   no drive sweep (owner decision D3).
2. A hard denylist refuses secret-shaped files *before* the first read.
3. Digests hash `read_text(...).encode('utf-8')`, never raw bytes, so a CRLF
   file on Windows keeps the same digest as its genesis evidence
   (KNOWLEDGE.md 7e).

Raw content stays local. The index records digests and counts, never bodies.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .private_io import write_private

# Filenames that count as skill evidence anywhere, exactly as genesis reads them.
SKILL_FILENAMES = frozenset({"skill.md", "skills.md"})
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})

# Directories that never hold owner knowledge, only machinery.
DENIED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv",
                         ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode"})
DENIED_SUFFIXES = frozenset({".key", ".pem", ".pfx", ".p12", ".crt", ".keystore"})
DENIED_NAME_PARTS = ("secret", "credential", "password", "id_rsa", "id_ed25519",
                     ".npmrc", ".pypirc", ".htpasswd")


@dataclass(frozen=True)
class ScanLimits:
    """Bounds that stop a scan honestly rather than truncating it silently."""

    max_file_bytes: int = 2_000_000
    max_files: int = 20_000
    max_total_bytes: int = 200_000_000


@dataclass
class ScanReport:
    """What a scan *would* read. Built from directory metadata, never content."""

    roots: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    file_count: int = 0
    total_bytes: int = 0
    skipped: int = 0
    capped: bool = False
    cap_reason: str = ""

    def as_dict(self) -> dict:
        return {
            "roots": self.roots, "paths": self.paths, "file_count": self.file_count,
            "total_bytes": self.total_bytes, "skipped": self.skipped,
            "capped": self.capped, "cap_reason": self.cap_reason,
        }


def denied_reason(path: str | Path) -> str | None:
    """Return why a path must never be opened, or None when it is safe to read."""
    candidate = Path(path)
    lowered = candidate.name.lower()
    if lowered.startswith(".env"):
        return "environment files can hold live credentials"
    if candidate.suffix.lower() in DENIED_SUFFIXES:
        return f"{candidate.suffix} files are key material"
    for part in DENIED_NAME_PARTS:
        if part in lowered:
            return f"the name contains {part!r}"
    for parent in candidate.parts[:-1]:
        if parent.lower() in DENIED_DIRS:
            return f"{parent} is machinery, not owner knowledge"
    return None


def _is_evidence(name: str, *, include_markdown: bool) -> bool:
    lowered = name.lower()
    if lowered in SKILL_FILENAMES:
        return True
    return include_markdown and Path(lowered).suffix in MARKDOWN_SUFFIXES


def _walk(root: Path, *, include_markdown: bool):
    """Yield candidate files, pruning denied directories before descending."""
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name.lower() not in DENIED_DIRS)
        for name in sorted(files):
            if not _is_evidence(name, include_markdown=include_markdown):
                continue
            candidate = Path(current) / name
            if denied_reason(candidate) is None:
                yield candidate


def _sources(skill_dirs, knowledge_roots) -> list[tuple[Path, bool]]:
    sources: list[tuple[Path, bool]] = [(Path(d), False) for d in (skill_dirs or [])]
    sources += [(Path(d), True) for d in (knowledge_roots or [])]
    return [(path, markdown) for path, markdown in sources if path.is_dir()]


def plan_scan(skill_dirs, *, knowledge_roots=(), limits: ScanLimits = ScanLimits()) -> ScanReport:
    """Describe the scan from directory metadata alone — no file is opened."""
    report = ScanReport(roots=[str(Path(d).resolve()) for d, _ in
                               _sources(skill_dirs, knowledge_roots)])
    for root, include_markdown in _sources(skill_dirs, knowledge_roots):
        for candidate in _walk(root, include_markdown=include_markdown):
            try:
                size = candidate.stat().st_size
            except OSError:
                report.skipped += 1
                continue
            if size > limits.max_file_bytes:
                report.skipped += 1
                continue
            if report.file_count + 1 > limits.max_files:
                report.capped = True
                report.cap_reason = (f"stopped at the {limits.max_files} file scan cap; "
                                     "narrow the root or raise the cap")
                return report
            if report.total_bytes + size > limits.max_total_bytes:
                report.capped = True
                report.cap_reason = (f"stopped at the {limits.max_total_bytes} byte scan cap; "
                                     "narrow the root or raise the cap")
                return report
            report.file_count += 1
            report.total_bytes += size
            report.paths.append(str(candidate))
    return report


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(8192)
    except OSError:
        return True


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _description(text: str) -> str:
    frontmatter = _FRONTMATTER.match(text)
    if frontmatter:
        declared = re.search(r"description:\s*>?\s*(.+?)(?:\n[a-zA-Z_-]+:|\n---|\Z)",
                             frontmatter.group(1), re.DOTALL)
        if declared:
            return " ".join(declared.group(1).split())[:400]
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped and not stripped.startswith("---"):
            return stripped[:400]
    return ""


def _entry_name(path: Path) -> str:
    return path.parent.name if path.name.lower() in SKILL_FILENAMES else path.stem


def _read_entry(path: Path) -> dict | None:
    """Read one consented file into an evidence entry, or None when unusable."""
    if _looks_binary(path):
        return None
    try:
        # read_text normalizes CRLF -> LF; the digest must hash that same text
        # or every Windows file would mismatch its genesis evidence (7e).
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    import hashlib

    from .genesis import git_remote_repository, github_repository, skill_categories, skill_source

    entry = {
        "name": _entry_name(path),
        "description": _description(text),
        "content": text,
        "content_bytes": len(text.encode("utf-8")),
        "digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "repository": github_repository(text) or git_remote_repository(path),
        "local_path": str(path.resolve()),
    }
    entry["source"] = skill_source(entry["local_path"], entry["repository"])
    entry["categories"] = skill_categories(entry)
    return entry


def discover_knowledge(skill_dirs, *, knowledge_roots=(),
                       limits: ScanLimits = ScanLimits()) -> list[dict]:
    """Read consented evidence into genesis-shaped entries.

    `skill_dirs` contribute SKILL.md/skills.md only. `knowledge_roots` are the
    owner's explicit additions and also contribute plain markdown.
    """
    by_name: dict[str, dict] = {}
    file_count = total_bytes = 0
    for root, include_markdown in _sources(skill_dirs, knowledge_roots):
        for candidate in _walk(root, include_markdown=include_markdown):
            try:
                size = candidate.stat().st_size
            except OSError:
                continue
            if size > limits.max_file_bytes:
                continue
            if file_count + 1 > limits.max_files or total_bytes + size > limits.max_total_bytes:
                return _ranked(by_name)
            entry = _read_entry(candidate)
            if entry is None:
                continue
            file_count += 1
            total_bytes += size
            # A skill's identity is its name, never its bytes: two skills may
            # legitimately share boilerplate. Plugin caches hold several copies
            # of one skill, so the longest copy wins and each name counts once.
            current = by_name.get(entry["name"])
            if current is None or entry["content_bytes"] > current["content_bytes"]:
                by_name[entry["name"]] = entry
    return _ranked(by_name)


def _ranked(by_name: dict[str, dict]) -> list[dict]:
    return [by_name[name] for name in sorted(by_name)]


# --- owner-added roots ---------------------------------------------------

def _roots_file(home: str | Path) -> Path:
    return Path(home) / "knowledge" / "roots.json"


def load_roots(home: str | Path) -> list[dict]:
    path = _roots_file(home)
    if not path.is_file():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("roots", []))
    except (OSError, json.JSONDecodeError):
        return []


def root_paths(home: str | Path) -> list[Path]:
    return [Path(entry["path"]) for entry in load_roots(home) if entry.get("consented")]


def add_root(home: str | Path, path: str | Path) -> dict:
    """Record an owner-consented knowledge root after refusing the dangerous ones."""
    resolved = Path(path).expanduser().resolve()
    if str(resolved) == resolved.anchor:
        raise ValueError("a drive root is never scanned; choose a specific folder")
    if not resolved.is_dir():
        raise ValueError(f"{resolved} does not exist as a folder")
    user_home = Path.home().resolve()
    if resolved == user_home or user_home.is_relative_to(resolved):
        raise ValueError("scanning the whole home folder is refused; choose a specific folder")
    roots = load_roots(home)
    if any(entry["path"] == str(resolved) for entry in roots):
        return next(entry for entry in roots if entry["path"] == str(resolved))
    entry = {"path": str(resolved), "added_at": int(time.time() * 1000), "consented": True}
    roots.append(entry)
    write_private(_roots_file(home), json.dumps({"version": 1, "roots": roots}, indent=2))
    return entry


def remove_root(home: str | Path, path: str | Path) -> bool:
    resolved = str(Path(path).expanduser().resolve())
    roots = load_roots(home)
    remaining = [entry for entry in roots if entry["path"] != resolved]
    if len(remaining) == len(roots):
        return False
    write_private(_roots_file(home), json.dumps({"version": 1, "roots": remaining}, indent=2))
    return True


# --- the private index ---------------------------------------------------

def _index_file(home: str | Path) -> Path:
    return Path(home) / "knowledge" / "index.json"


def write_index(home: str | Path, entries: list[dict]) -> Path:
    """Persist digests and counts. Bodies never reach the index."""
    payload = {
        "version": 1,
        "privacy": "Local only. Raw knowledge bodies are never written here or uploaded.",
        "scanned_at": int(time.time() * 1000),
        "entry_count": len(entries),
        "total_bytes": sum(entry["content_bytes"] for entry in entries),
        "entries": [
            {"name": entry["name"], "digest": entry["digest"],
             "content_bytes": entry["content_bytes"], "source": entry.get("source", "local"),
             "repository": entry.get("repository"), "local_path": entry.get("local_path"),
             "categories": entry.get("categories", ["general"])}
            for entry in sorted(entries, key=lambda item: item["name"])
        ],
    }
    return write_private(_index_file(home), json.dumps(payload, indent=2))


def load_index(home: str | Path) -> dict:
    path = _index_file(home)
    if not path.is_file():
        return {"version": 1, "entry_count": 0, "entries": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entry_count": 0, "entries": []}
