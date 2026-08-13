"""The daemon keeps presence honest, budgets its hooks, and stops cleanly."""
from __future__ import annotations

import json
import time

from earth_cli import daemon
from earth_cli.avatar import fetch_lpc_portrait


class ScriptedClient:
    def __init__(self):
        self.calls = []

    def enter(self):
        self.calls.append("enter"); return {"state": {"name": "Probe"}}

    def pulse(self):
        self.calls.append("pulse"); return {"eventInvitations": [{"eventId": "event:x"}]}

    def desk(self):
        self.calls.append("desk"); return {"blocking": [{"summary": "Approve the fence build"}]}

    def market_json(self, path):
        self.calls.append(path); return {"feed": [{"gloss": "Probe waved at the plaza."}]}

    def leave(self):
        self.calls.append("leave"); return {"ok": True}


def test_one_tick_syncs_the_inbox_and_stops_cleanly(tmp_path, monkeypatch):
    home = tmp_path / ".Earth"; home.mkdir()
    # The stop file is honored on the first check after one full tick.
    monkeypatch.setattr(daemon.time, "sleep", lambda seconds: daemon.paths(home)["stop"].write_text("stop"))
    client = ScriptedClient()
    code = daemon.run_loop(lambda: client, home, lambda c, pulse: {})
    assert code == 0
    assert "enter" in client.calls and "leave" in client.calls
    digest = daemon.paths(home)["digest"].read_text(encoding="utf-8")
    assert "Approve the fence build" in digest
    assert "waved at the plaza" in digest
    # A clean stop removes its own pid and stop markers.
    assert not daemon.paths(home)["pid"].exists()
    assert not daemon.paths(home)["stop"].exists()


def test_hook_budget_is_a_sliding_hour(tmp_path):
    config = {"hook": "echo hi", "maxHookRunsPerHour": 2}
    now = time.time()
    state = {"hookRuns": [now - 10, now - 20]}
    assert daemon.hook_allowed(state, config, now) is False
    # An hour later the window has slid open again.
    assert daemon.hook_allowed(state, config, now + 3700) is True
    # No hook configured means never allowed, whatever the budget says.
    assert daemon.hook_allowed({"hookRuns": []}, {"hook": None}, now) is False


def test_only_real_changes_trigger_the_mind():
    previous = {"blocking": 1, "unreadLetters": 0, "invitations": 2}
    unchanged = daemon.detect_triggers(previous, dict(previous))
    assert unchanged == []
    grown = daemon.detect_triggers(previous, {"blocking": 2, "unreadLetters": 1, "invitations": 2})
    assert len(grown) == 2
    # Shrinking counts (owner answered, letters read) summon nobody.
    shrunk = daemon.detect_triggers(previous, {"blocking": 0, "unreadLetters": 0, "invitations": 0})
    assert shrunk == []


def test_portrait_fetch_fails_closed_offline(tmp_path, monkeypatch):
    import urllib.request

    def refuse(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    identity = {"avatar": {"catalogKey": "citizen_male_civic_04"}}
    assert fetch_lpc_portrait(identity, tmp_path) is None
    assert not (tmp_path / "avatar.png").exists()
    # A hostile catalog key never becomes a URL at all.
    assert fetch_lpc_portrait({"avatar": {"catalogKey": "../../etc"}}, tmp_path) is None
