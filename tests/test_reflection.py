"""H5 backtests: reflections adjust traits only from lived, in-window evidence."""
import json
from datetime import datetime, timedelta, timezone

from earth_cli.reflection import run_reflection

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
NOW_MS = NOW.timestamp() * 1000


def make_home(tmp_path, personality=None):
    home = tmp_path / "home"
    memory = home / "memory"
    memory.mkdir(parents=True)
    identity = {
        "personality": personality or {"curiosity": 4, "warmth": 4, "humor": 4,
                                       "diligence": 4, "courage": 4},
        "registration": {"agent_id": "agent:testa-123"},
    }
    (home / "agent.json").write_text(json.dumps(identity), encoding="utf-8")
    return home, memory


def test_curiosity_grows_from_learned_skills(tmp_path):
    home, memory = make_home(tmp_path)
    (memory / "skills.json").write_text(json.dumps([
        {"status": "learned", "decidedAt": NOW_MS - 3600_000},
        {"status": "learned", "decidedAt": NOW_MS - 7200_000},
    ]), encoding="utf-8")
    result = run_reflection(home, now=NOW)
    assert result["adjustments"] == {"curiosity": 1}
    assert result["levels"]["curiosity"] == 5
    saved = json.loads((home / "agent.json").read_text(encoding="utf-8"))
    assert saved["personality"]["curiosity"] == 5
    assert saved["registration"]["agent_id"] == "agent:testa-123"


def test_old_evidence_outside_window_ignored(tmp_path):
    home, memory = make_home(tmp_path)
    stale = NOW_MS - 10 * 86_400_000
    (memory / "skills.json").write_text(json.dumps([
        {"status": "learned", "decidedAt": stale},
        {"status": "learned", "decidedAt": stale},
    ]), encoding="utf-8")
    result = run_reflection(home, now=NOW)
    assert result["adjustments"] == {}
    assert result["levels"]["curiosity"] == 4


def test_traits_cap_at_ten(tmp_path):
    home, memory = make_home(tmp_path, personality={"curiosity": 10, "warmth": 4,
                                                    "humor": 4, "diligence": 4, "courage": 4})
    (memory / "skills.json").write_text(json.dumps([
        {"status": "learned", "decidedAt": NOW_MS - 1000},
        {"status": "learned", "decidedAt": NOW_MS - 2000},
    ]), encoding="utf-8")
    result = run_reflection(home, now=NOW)
    assert "curiosity" not in result["adjustments"]
    assert result["levels"]["curiosity"] == 10


def test_weekly_cadence_guard(tmp_path):
    home, memory = make_home(tmp_path)
    first = run_reflection(home, now=NOW)
    assert not first.get("skipped")
    again = run_reflection(home, now=NOW + timedelta(days=2))
    assert again["skipped"]
    forced = run_reflection(home, now=NOW + timedelta(days=2), force=True)
    assert not forced.get("skipped")
    later = run_reflection(home, now=NOW + timedelta(days=9))
    assert not later.get("skipped")


def test_reflection_ledger_records_evidence(tmp_path):
    home, memory = make_home(tmp_path)
    (memory / "civic.json").write_text(json.dumps([
        {"createdAt": NOW_MS - 1000},
    ]), encoding="utf-8")
    result = run_reflection(home, now=NOW)
    assert result["adjustments"] == {"courage": 1}
    rows = [json.loads(line) for line in
            (memory / "reflections.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["evidence"]["courage"] == 1
    assert rows[-1]["adjustments"] == {"courage": 1}


def test_warmth_needs_three_social_touches(tmp_path):
    home, memory = make_home(tmp_path)
    (memory / "skill-shares.json").write_text(json.dumps([
        {"senderId": "agent:testa-123", "createdAt": NOW_MS - 1000},
    ]), encoding="utf-8")
    (memory / "conversations.jsonl").write_text(
        json.dumps({"observedAt": NOW.isoformat(), "startedAt": NOW_MS - 5000}) + "\n"
        + json.dumps({"observedAt": NOW.isoformat(), "startedAt": NOW_MS - 4000}) + "\n",
        encoding="utf-8")
    result = run_reflection(home, now=NOW)
    assert result["adjustments"].get("warmth") == 1
