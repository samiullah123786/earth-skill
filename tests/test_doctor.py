"""A stranded agent has to be able to work out its own situation.

Earth moved hosts and every connector had the old address compiled in. Agents
reported the world as permanently down while their identities sat intact on
disk. These tests pin the reasoning that prevents that from recurring.
"""

import json

from earth_cli import doctor


def _home(tmp_path, *, registration=None, key=True):
    home = tmp_path / ".Earth"
    home.mkdir(parents=True)
    identity = {
        "persona": {"name": "Zee", "owner_name": "Owner", "gender": "female"},
        "genome": {"skill_count": 12, "experience_tier": "practiced", "evidence_digest": "d" * 64},
        "credentials": {"public_key": "pk"},
    }
    if registration is not None:
        identity["registration"] = registration
    (home / "agent.json").write_text(json.dumps(identity), encoding="utf-8")
    if key:
        (home / "agent.key").write_text("key", encoding="utf-8")
    return home


def test_reads_the_kernel_a_citizen_actually_joined(tmp_path):
    home = _home(tmp_path, registration={
        "agent_id": "agent:zee-4800453212", "status": "pending_owner",
        "api": "https://basic-roadrunner-683.convex.site",
    })
    report = doctor.local_identity_report(home)
    assert report["agentId"] == "agent:zee-4800453212"
    assert report["registeredAgainst"] == "https://basic-roadrunner-683.convex.site"


def test_a_citizen_registered_against_another_world_is_not_called_lost(tmp_path, monkeypatch):
    """The identity is intact and the world is up. Only the address changed."""
    home = _home(tmp_path, registration={
        "agent_id": "agent:zee-4800453212", "status": "pending_owner",
        "api": "https://basic-roadrunner-683.convex.site",
    })
    monkeypatch.setattr(doctor, "kernel_health",
                        lambda api, timeout=15: {"reachable": True, "service": "earth-kernel", "protocol": 1})
    report = doctor.diagnose("https://kernel.agentsearth.com", home)
    assert report["verdict"] == "registered_elsewhere"
    headline, steps = doctor.ADVICE[report["verdict"]]
    assert "identity did not" in headline
    assert any("--repair" in step for step in steps)


def test_a_retired_address_is_named_before_anything_else(tmp_path):
    """Pointing at a dead host explains every other symptom, so it comes first."""
    home = _home(tmp_path, registration={"agent_id": "a", "api": "https://basic-roadrunner-683.convex.site"})
    report = doctor.diagnose("https://basic-roadrunner-683.convex.site", home)
    assert report["verdict"] == "retired_address"
    assert report["retiredHost"] == "basic-roadrunner-683.convex.site"


def test_an_unreachable_kernel_says_nothing_local_is_lost(tmp_path, monkeypatch):
    home = _home(tmp_path, registration={"agent_id": "a", "api": "https://kernel.agentsearth.com"})
    monkeypatch.setattr(doctor, "kernel_health",
                        lambda api, timeout=15: {"reachable": False, "status": 500, "detail": "exceeded the free plan limits"})
    report = doctor.diagnose("https://kernel.agentsearth.com", home)
    assert report["verdict"] == "kernel_unreachable"
    _, steps = doctor.ADVICE[report["verdict"]]
    assert any("Nothing local is lost" in step for step in steps)


def test_a_signed_refusal_of_an_unknown_citizen_is_distinguished(tmp_path, monkeypatch):
    home = _home(tmp_path, registration={"agent_id": "a", "api": "https://kernel.agentsearth.com"})
    monkeypatch.setattr(doctor, "kernel_health",
                        lambda api, timeout=15: {"reachable": True, "service": "earth-kernel", "protocol": 1})

    def refuse():
        raise RuntimeError("agent is not active")

    report = doctor.diagnose("https://kernel.agentsearth.com", home, probe=refuse)
    assert report["verdict"] == "unknown_to_this_kernel"


def test_a_healthy_world_says_so(tmp_path, monkeypatch):
    home = _home(tmp_path, registration={"agent_id": "a", "api": "https://kernel.agentsearth.com"})
    monkeypatch.setattr(doctor, "kernel_health",
                        lambda api, timeout=15: {"reachable": True, "service": "earth-kernel", "protocol": 1})
    report = doctor.diagnose("https://kernel.agentsearth.com", home, probe=lambda: None)
    assert report["verdict"] == "healthy"


def test_missing_identity_is_not_confused_with_a_moved_world(tmp_path, monkeypatch):
    home = tmp_path / ".Earth"
    home.mkdir(parents=True)
    monkeypatch.setattr(doctor, "kernel_health",
                        lambda api, timeout=15: {"reachable": True, "service": "earth-kernel", "protocol": 1})
    report = doctor.diagnose("https://kernel.agentsearth.com", home)
    assert report["verdict"] == "no_local_identity"


def test_every_verdict_has_advice():
    """A verdict with no next step is a dead end for whoever is reading it."""
    verdicts = {"retired_address", "registered_elsewhere", "kernel_unreachable", "no_local_identity",
                "never_registered", "unknown_to_this_kernel", "refused", "healthy"}
    assert verdicts <= set(doctor.ADVICE)
    for verdict, (headline, steps) in doctor.ADVICE.items():
        assert headline and steps, verdict
