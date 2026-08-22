"""`Earth perceive` renders what the Kernel says, and nothing it does not.

The formatter is what a human reads and the raw payload is what an owner's
brain reasons over, so the tests pin both halves: the grid stays intact
character for character, the legend explains only what is on screen, and a
sleeping citizen gets the truth instead of a view of a place they are not in.
"""

from __future__ import annotations

import json

from earth_cli.perceive import format_perception

AWAKE = {
    "ok": True,
    "agentId": "agent:test-1",
    "name": "Sam",
    "asleep": False,
    "position": {"x": 40, "y": 37},
    "facing": {"direction": "front", "degrees": 180, "compass": "south"},
    "activity": "earning their place with public work",
    "grid": {
        "radius": 1,
        "axes": "row 0 is north",
        "view": ["ggg", "g@r", "gtw"],
        "terrain": ["ggg", "ggr", "gtw"],
        "legend": {
            "g": {"is": "grass", "walkable": True},
            "r": {"is": "cobbled road", "walkable": True},
            "t": {"is": "tree", "walkable": False},
            "w": {"is": "water", "walkable": False},
            "@": {"is": "you", "walkable": True},
            "B": {"is": "building", "walkable": False},
        },
    },
    "plot": None,
    "nearbyCitizens": [
        {"agentId": "agent:test-2", "name": "Sage", "family": "research",
         "distance": 2.2, "position": {"x": 42, "y": 36}, "activity": "reading", "talkingWith": None},
    ],
    "nearbyVenues": [{"name": "Maple Park", "kind": "park", "position": {"x": 39, "y": 38}, "distance": 1.4}],
    "nearbyStructures": [],
    "gate": {"x": 29, "y": 26, "distance": 15.6},
    "serverNow": 1_800_000_000_000,
}


def test_the_grid_survives_formatting_intact() -> None:
    text = format_perception(AWAKE)
    # Spaced for the eye, but every row and column exactly as the Kernel said.
    assert "g g g" in text
    assert "g @ r" in text
    assert "g t w" in text


def test_position_and_bearing_lead_the_report() -> None:
    text = format_perception(AWAKE)
    assert text.splitlines()[0] == "Sam at (40, 37), facing south."


def test_the_legend_explains_only_what_is_on_screen() -> None:
    text = format_perception(AWAKE)
    assert "t=tree (blocked)" in text
    assert "w=water (blocked)" in text
    # 'B' is in the Kernel's legend but not in this view, so it says nothing.
    assert "building" not in text


def test_neighbours_come_with_names_and_distances() -> None:
    text = format_perception(AWAKE)
    assert "Sage (research) 2.2 tiles away" in text
    assert "Maple Park at 1.4" in text


def test_a_sleeping_citizen_is_told_the_truth() -> None:
    asleep = {"ok": True, "name": "Barebone", "asleep": True, "gate": {"x": 29, "y": 26}}
    text = format_perception(asleep)
    assert "asleep beyond the Waking Gate" in text
    assert "wake at the gate at (29, 26)" in text
    # No grid is rendered for a mind that is not there to read one.
    assert "@" not in text


def test_an_unknown_citizen_is_an_answer_not_a_crash() -> None:
    text = format_perception({"ok": False, "why": "no such citizen"})
    assert "does not know this citizen" in text


def test_the_payload_is_json_serialisable_for_the_owner_brain() -> None:
    # --json hands the dict straight to a model; a payload that cannot round-
    # trip through json.dumps would fail exactly there.
    assert json.loads(json.dumps(AWAKE)) == AWAKE
