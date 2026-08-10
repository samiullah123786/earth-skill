"""Packing, unpacking, and installing knowledge packages - inside one folder.

Everything Earth installs lands under `~/.Earth/skills/`, which Earth owns.
Making that knowledge live in the owner's actual coding agent is a separate,
explicit choice per environment (`Earth mirror --enable claude`), because
copying a stranger's instructions into `~/.claude/skills` changes what the
owner's agent will read tomorrow.

Extraction refuses any member that could write outside the destination, so a
crafted archive cannot reach the rest of the machine.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import re
import tarfile
import time
from pathlib import Path

from .private_io import secure_directory, write_private
from .safety import scan_package, unsafe_member

MIRROR_TARGETS = {
    "claude": Path.home() / ".claude" / "skills",
    "cursor": Path.home() / ".cursor" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "agents": Path.home() / ".agents" / "skills",
}
PACKABLE_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml",
                               ".csv", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
                               ".py", ".sh", ".ps1", ".js", ".ts", ".toml"})
MAX_PACKAGE_BYTES = 25 * 1024 * 1024


def skills_root(home: str | Path) -> Path:
    return Path(home) / "skills"


# --- packing -------------------------------------------------------------

def pack_skill(source: str | Path) -> dict:
    """Build a deterministic tar.gz of a skill folder plus its manifest facts."""
    root = Path(source).resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a folder to publish")
    members = sorted(
        path for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in PACKABLE_SUFFIXES
    )
    if not members:
        raise ValueError("that folder holds nothing publishable")

    buffer = io.BytesIO()
    # Determinism is load-bearing: the Bank deduplicates by this digest, so the
    # same folder must pack to the same bytes on any machine, on any day. Tar
    # member metadata is pinned below, and gzip is driven directly with mtime=0
    # because tarfile's "w:gz" quietly stamps the current time into the gzip
    # header - four bytes of wall clock that changed every digest until it was
    # caught by packing the same folder twice, two seconds apart.
    import gzip as gzip_module
    gz = gzip_module.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0)
    with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in members:
            info = archive.gettarinfo(str(path), arcname=path.relative_to(root).as_posix())
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
            info.mode = 0o644
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    gz.close()
    payload = buffer.getvalue()
    if len(payload) > MAX_PACKAGE_BYTES:
        raise ValueError(f"packed to {len(payload)} bytes, above the {MAX_PACKAGE_BYTES} byte cap; "
                         "publish it as a verified GitHub repository root instead")
    return {
        "payload": payload,
        "digest": hashlib.sha256(payload).hexdigest(),
        "sizeBytes": len(payload),
        "fileCount": len(members),
    }


def unpack(payload: bytes, destination: str | Path) -> list[str]:
    """Extract a package, refusing any member that could escape the folder."""
    target = Path(destination).resolve()
    secure_directory(target)
    written: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"{member.name} is not a regular file and was refused")
            escape = unsafe_member(member.name)
            if escape:
                raise ValueError(f"{member.name} {escape}")
            resolved = (target / member.name).resolve()
            if not resolved.is_relative_to(target):
                raise ValueError(f"{member.name} resolves outside the install folder and was refused")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            resolved.write_bytes(source.read())
            written.append(member.name)
    return written


# --- installing ----------------------------------------------------------

def install_package(home: str | Path, name: str, payload: bytes, *,
                    declared_digest: str, policy: str = "safe_auto",
                    provider: str = "", trade_id: str = "") -> dict:
    """Unpack into a staging folder, review it, then install or quarantine.

    Never installs on a `refused` verdict. Installs without asking only when the
    package is inert AND the owner chose safe_auto. Everything else is held for
    the owner to read and decide.
    """
    base = secure_directory(skills_root(home))
    staging = base / ".staging" / name
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    unpack(payload, staging)

    actual = hashlib.sha256(payload).hexdigest()
    review = scan_package(staging, declared_digest=declared_digest, actual_digest=actual)
    record = {
        "name": name, "provider": provider, "tradeId": trade_id,
        "digest": actual, "verdict": review.verdict, "flags": review.flags,
        "note": review.note(name), "fileCount": review.file_count,
        "sizeBytes": review.total_bytes, "at": int(time.time() * 1000),
    }

    if review.verdict == "refused":
        shutil.rmtree(staging, ignore_errors=True)
        record["state"] = "refused"
        _record(home, record)
        return record

    if not (review.safe and policy == "safe_auto"):
        held = base / ".pending" / name
        if held.exists():
            shutil.rmtree(held, ignore_errors=True)
        held.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(held))
        record["state"] = "pending_owner"
        record["path"] = str(held)
        _record(home, record)
        return record

    installed = base / name
    if installed.exists():
        shutil.rmtree(installed, ignore_errors=True)
    shutil.move(str(staging), str(installed))
    record["state"] = "installed"
    record["path"] = str(installed)
    record["mirroredTo"] = mirror(home, name)
    _record(home, record)
    return record


def approve_pending(home: str | Path, name: str) -> dict:
    """Move an owner-approved package out of quarantine and into service."""
    base = skills_root(home)
    held = base / ".pending" / name
    if not held.is_dir():
        raise ValueError(f"{name!r} is not waiting for review")
    installed = base / name
    if installed.exists():
        shutil.rmtree(installed, ignore_errors=True)
    shutil.move(str(held), str(installed))
    record = {"name": name, "state": "installed", "approvedByOwner": True,
              "path": str(installed), "at": int(time.time() * 1000),
              "mirroredTo": mirror(home, name)}
    _record(home, record)
    return record


def pending(home: str | Path) -> list[dict]:
    index = load_installs(home)
    installed = {row["name"] for row in index["installs"] if row.get("state") == "installed"}
    seen: dict[str, dict] = {}
    for row in index["installs"]:
        if row.get("state") == "pending_owner" and row["name"] not in installed:
            seen[row["name"]] = row
    return list(seen.values())


# --- mirroring into the owner's real coding agents -----------------------

def _mirror_file(home: str | Path) -> Path:
    return Path(home) / "skills" / "mirrors.json"


def mirrors(home: str | Path) -> list[str]:
    path = _mirror_file(home)
    if not path.is_file():
        return []
    try:
        return [name for name in json.loads(path.read_text(encoding="utf-8")).get("enabled", [])
                if name in MIRROR_TARGETS]
    except (OSError, json.JSONDecodeError):
        return []


def set_mirror(home: str | Path, environment: str, enabled: bool) -> list[str]:
    if environment not in MIRROR_TARGETS:
        raise ValueError(f"unknown environment {environment!r}; choose from {', '.join(sorted(MIRROR_TARGETS))}")
    current = set(mirrors(home))
    current.add(environment) if enabled else current.discard(environment)
    write_private(_mirror_file(home), json.dumps({"enabled": sorted(current)}, indent=2))
    return sorted(current)


def mirror(home: str | Path, name: str) -> list[str]:
    """Copy an installed package into every environment the owner enabled."""
    source = skills_root(home) / name
    copied: list[str] = []
    for environment in mirrors(home):
        target = MIRROR_TARGETS[environment] / name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(source, target)
            copied.append(environment)
        except OSError:
            continue
    return copied


# --- the private install index -------------------------------------------

def _index_file(home: str | Path) -> Path:
    return Path(home) / "skills" / "index.json"


def load_installs(home: str | Path) -> dict:
    path = _index_file(home)
    if not path.is_file():
        return {"version": 1, "installs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "installs": []}


def _record(home: str | Path, record: dict) -> None:
    index = load_installs(home)
    index["installs"] = ([row for row in index["installs"]
                          if not (row["name"] == record["name"] and row.get("state") == record.get("state"))]
                         + [record])[-200:]
    write_private(_index_file(home), json.dumps(index, indent=2))


FRONTMATTER = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def normalized_content_digest(source: str | Path) -> str:
    """Identity of a skill's words rather than its bytes.

    Strips markdown frontmatter and folds every whitespace run, so a copy that
    differs only in metadata, line endings, or indentation deduplicates against
    the original in the Bank instead of banking twice.
    """
    root = Path(source).resolve()
    members = sorted(
        path for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in PACKABLE_SUFFIXES
    )
    parts: list[str] = []
    for path in members:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix.lower() in {".md", ".markdown"}:
            text = FRONTMATTER.sub("", text, count=1)
        folded = " ".join(text.split())
        parts.append(path.relative_to(root).as_posix() + "\x01" + folded)
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
