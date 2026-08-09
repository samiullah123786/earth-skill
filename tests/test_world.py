"""Backtests for map powers: the never-disturb-another-agent guarantee."""

import json

import pytest

from earth_cli import world


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(world, "REGISTRY", tmp_path / "plots.json")


def first_free():
    return world.free_plots()[0]["id"]


def test_manifest_ships_with_skill():
    m = world.load_manifest()
    assert m["width"] == 64 and m["height"] == 48
    assert len(m["plots"]) >= 40
    assert len(m["walkable_rows"]) == 48
    assert any("NEVER build" in r for r in m["build_rules"])


def test_claim_and_build():
    pid = first_free()
    ok, msg = world.claim(pid, "Aiden")
    assert ok and pid in msg
    ok, msg = world.build("home", "Aiden")
    assert ok and "built" in msg


def test_occupied_plot_is_protected():
    pid = first_free()
    world.claim(pid, "Aiden")
    ok, msg = world.claim(pid, "Nova")
    assert not ok
    assert "never disturb" in msg
    assert "Nearest free plot" in msg  # she is redirected, not blocked from living


def test_one_home_plot_per_agent():
    a, b = world.free_plots()[0]["id"], world.free_plots()[1]["id"]
    world.claim(a, "Aiden")
    ok, msg = world.claim(b, "Aiden")
    assert not ok and "one home plot" in msg


def test_build_requires_claim():
    ok, msg = world.build("home", "Willow")
    assert not ok and "Claim a plot first" in msg


def test_no_second_home_but_extension_ok():
    world.claim(first_free(), "Aiden")
    world.build("home", "Aiden")
    ok, msg = world.build("home", "Aiden")
    assert not ok and "extension" in msg
    ok, _ = world.build("extension", "Aiden")
    assert ok


def test_registry_is_json_on_disk(tmp_path):
    pid = first_free()
    world.claim(pid, "Aiden")
    data = json.loads(world.REGISTRY.read_text())
    assert data["claims"][pid]["agent"] == "Aiden"
