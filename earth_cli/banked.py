"""What this citizen has already put in the Earth Bank.

`Earth sync` is documented as the way to keep a banked skill current, and the
Kernel's sync handler needs the skill's Bank id to find the row and check that
the caller is the citizen who deposited it. Nothing on this machine knew that
id: the deposit printed it and threw it away, so sync had nothing to send and
quietly did nothing every time it ran.

This is the missing half - a small local ledger, written at deposit time and
read at sync time, mapping the skill folder to the id the Bank gave back. It
holds no skill content and no secrets: a name, a path, an id, and the digest of
what was last pushed, which is exactly enough to answer "has this changed since
the Bank last saw it".
"""

from __future__ import annotations

import json
from pathlib import Path


def _ledger_path(home: str | Path) -> Path:
    return Path(home) / "knowledge" / "banked.json"


def read_banked(home: str | Path) -> dict[str, dict]:
    """Every skill this citizen has banked, keyed by its folder path.

    A missing or unreadable ledger is not an error. It means nothing has been
    banked from this machine yet, and sync should simply have nothing to do.
    """
    path = _ledger_path(home)
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def record_banked(home: str | Path, folder: str | Path, name: str,
                  skill_id: str, content_digest: str) -> None:
    """Remember that `folder` is in the Bank as `skill_id`.

    Called for a fresh deposit and for a duplicate that was linked to an
    existing master, because both mean the Bank now holds this content and a
    later edit should sync rather than deposit a second copy.
    """
    if not skill_id:
        return
    ledger = read_banked(home)
    ledger[str(folder)] = {
        "name": name,
        "skillId": skill_id,
        "contentDigest": content_digest,
    }
    path = _ledger_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def forget_banked(home: str | Path, folder: str | Path) -> None:
    """Drop a skill from the ledger - it was withdrawn, or its folder is gone."""
    ledger = read_banked(home)
    if ledger.pop(str(folder), None) is None:
        return
    _ledger_path(home).write_text(json.dumps(ledger, indent=2), encoding="utf-8")
