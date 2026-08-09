"""H5 Reflection: personality emerges from lived history, never from claims.

Once a week the agent reads its own local memory ledgers (what actually
happened on Earth) and lets verified activity nudge its five traits, at most
one point per trait per reflection, hard-capped at 10. Nothing is uploaded;
the reflection and its evidence live in the agent's private memory.

Trait evidence mapping (mirrors the contract documented in genesis.py):
  curiosity  <- skills genuinely learned on Earth
  warmth     <- teaching, shares offered, conversations held
  humor      <- training-green play, events, quests joined
  diligence  <- builds raised, care tickets resolved
  courage    <- civic applications, care inspections taken on
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .private_io import write_private

WINDOW_DAYS = 7
MIN_INTERVAL_DAYS = 6
EVIDENCE_THRESHOLD = {"curiosity": 2, "warmth": 3, "humor": 2, "diligence": 2, "courage": 1}


def _memory_dir(home: str | Path) -> Path:
    return Path(home) / "memory"


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in
                    path.read_text(encoding="utf-8").splitlines() if line.strip()]
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _timestamp_ms(row: dict) -> float:
    for key in ("decidedAt", "createdAt", "sentAt", "startedAt", "resolvedAt", "updatedAt"):
        value = row.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    observed = row.get("observedAt")
    if isinstance(observed, str):
        try:
            return datetime.fromisoformat(observed).timestamp() * 1000
        except ValueError:
            pass
    return 0.0


def _in_window(row: dict, now_ms: float, start_ms: float = 0.0) -> bool:
    stamp = _timestamp_ms(row)
    return stamp > max(start_ms, now_ms - WINDOW_DAYS * 86_400_000) and stamp <= now_ms


def gather_evidence(home: str | Path, agent_id: str, now_ms: float,
                    start_ms: float = 0.0) -> dict[str, int]:
    root = _memory_dir(home)
    skills = [row for row in _rows(root / "skills.json")
              if row.get("status") == "learned" and _in_window(row, now_ms, start_ms)]
    shares_sent = [row for row in _rows(root / "skill-shares.json")
                   if row.get("senderId") == agent_id and _in_window(row, now_ms, start_ms)]
    conversations = [row for row in _rows(root / "conversations.jsonl")
                     if _in_window(row, now_ms, start_ms)]
    playful = [row for row in _rows(root / "experiences.jsonl")
               if row.get("kind") in ("training", "train", "event", "quest", "celebration")
               and _in_window(row, now_ms, start_ms)]
    builds = [row for row in _rows(root / "building.json") if _in_window(row, now_ms, start_ms)]
    care = _rows(root / "care.json")
    care_resolved = [row for row in care
                     if row.get("state") in ("resolved", "closed") and _in_window(row, now_ms, start_ms)]
    care_taken = [row for row in care
                  if row.get("assignedAgentId") == agent_id and _in_window(row, now_ms, start_ms)]
    civic = [row for row in _rows(root / "civic.json") if _in_window(row, now_ms, start_ms)]
    return {
        "curiosity": len(skills),
        "warmth": len(shares_sent) + len(conversations),
        "humor": len(playful),
        "diligence": len(builds) + len(care_resolved),
        "courage": len(civic) + len(care_taken),
    }


def run_reflection(home: str | Path, now: datetime | None = None,
                   force: bool = False) -> dict[str, Any]:
    home = Path(home)
    now = now or datetime.now(timezone.utc)
    now_ms = now.timestamp() * 1000
    ledger = _memory_dir(home) / "reflections.jsonl"
    previous = _rows(ledger)
    if previous and not force:
        last = previous[-1].get("atMs", 0)
        if now_ms - last < MIN_INTERVAL_DAYS * 86_400_000:
            days_left = MIN_INTERVAL_DAYS - (now_ms - last) / 86_400_000
            return {"skipped": True, "reason": f"last reflection was recent; next in {days_left:.1f} days"}

    last_ms = float(previous[-1].get("atMs", 0)) if previous else 0.0
    agent_file = home / "agent.json"
    identity = json.loads(agent_file.read_text(encoding="utf-8"))
    agent_id = identity.get("registration", {}).get("agent_id", "")
    personality = dict(identity.get("personality") or {})
    evidence = gather_evidence(home, agent_id, now_ms, start_ms=last_ms)

    adjustments: dict[str, int] = {}
    for trait, count in evidence.items():
        level = int(personality.get(trait, 3))
        if count >= EVIDENCE_THRESHOLD[trait] and level < 10:
            personality[trait] = level + 1
            adjustments[trait] = 1

    identity["personality"] = personality
    write_private(agent_file, json.dumps(identity, indent=2))
    record = {
        "at": now.isoformat(), "atMs": now_ms, "windowDays": WINDOW_DAYS,
        "evidence": evidence, "adjustments": adjustments, "levels": personality,
    }
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return {"skipped": False, "evidence": evidence, "adjustments": adjustments,
            "levels": personality}
