"""A citizen that stays awake, and answers when spoken to."""
from __future__ import annotations

import json

from earth_cli import daemon


def test_being_spoken_to_wakes_the_mind():
    """The trigger that makes conversation two-way instead of one-way."""
    before = {"awaitingIds": []}
    after = {"awaitingIds": ["conv-1"]}
    triggers = daemon.detect_triggers(before, after)
    assert any("waiting on a reply" in trigger for trigger in triggers)
    assert any("Earth reply" in trigger for trigger in triggers), "the wake must say how to answer"


def test_one_conversation_replacing_another_still_wakes():
    """Counting would miss this; comparing ids does not."""
    triggers = daemon.detect_triggers({"awaitingIds": ["conv-1"]}, {"awaitingIds": ["conv-2"]})
    assert any("waiting on a reply" in trigger for trigger in triggers)


def test_the_same_conversation_does_not_wake_twice():
    """A mind is summoned by news, never by the absence of news."""
    assert daemon.detect_triggers({"awaitingIds": ["conv-1"]}, {"awaitingIds": ["conv-1"]}) == []


def test_a_changing_life_is_never_reported_as_stalled(tmp_path):
    state: dict = {}
    for index in range(8):
        stalled = daemon.heartbeat(tmp_path, state, {"citizen": {"state": "ambient", "activity": f"errand {index}"}})
        assert stalled is False


def test_a_life_that_stops_changing_is_noticed(tmp_path):
    state: dict = {}
    pulse = {"citizen": {"state": "ambient", "activity": "standing still"}}
    verdicts = [daemon.heartbeat(tmp_path, state, pulse) for _ in range(6)]
    assert verdicts[0] is False, "the first sight of a life cannot be a verdict about it"
    assert any(verdicts), "a citizen doing nothing for several ticks must be noticed"
    assert verdicts[-1] is True


def test_the_heartbeat_is_written_where_anyone_can_read_it(tmp_path):
    daemon.heartbeat(tmp_path, {}, {"citizen": {"state": "ambient"}})
    beat = json.loads((tmp_path / "daemon.beat").read_text(encoding="utf-8"))
    assert beat["at"] > 0
    assert beat["still"] == 0


def test_retries_are_spread_rather_than_synchronised():
    """Full jitter: every daemon must not come back at the same instant."""
    waits = {daemon._backoff(4) for _ in range(60)}
    assert len(waits) > 5, "identical waits would stampede the Kernel on recovery"
    assert all(1 <= wait <= 160 for wait in waits)
    # It still grows, and it still stops growing.
    assert daemon._backoff(99) <= 600
