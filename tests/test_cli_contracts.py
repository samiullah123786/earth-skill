import argparse
import json
import os
import stat

import pytest

from earth_cli import cli
from earth_cli.identity import ensure_keypair
from earth_cli.network import EarthClient
from earth_cli.private_io import secure_directory, write_private


class FakeClient:
    def __init__(self, pulse=None):
        self.actions = []
        self.committed = []
        self._pulse = pulse or {"cursor": 1, "events": [], "messages": []}

    def act(self, action):
        self.actions.append(action)
        if action.get("type") == "verify_share":
            return {"status": action["decision"] + "d"}
        if action.get("type") == "offline_letter":
            return {"messageId": "message:test"}
        if action.get("type") == "event_propose":
            return {"eventId": "event:test", "state": "approved", "autoApproved": True,
                    "venue": {"venueId": "venue:plaza", "name": "Founding Plaza"}}
        if action.get("type") == "event_rsvp":
            return {"eventId": action["eventId"], "status": "accepted" if action["decision"] == "accept" else "declined"}
        if action.get("type") == "event_note":
            return {"eventId": action["eventId"], "topic": action["topic"]}
        return {"mode": "live", "state": "active", "conversationId": "talk:test"}

    def pulse(self):
        return self._pulse

    def commit_pulse(self, pulse):
        self.committed.append(pulse)

    def community_events(self):
        return {"events": []}


def test_talk_is_atomic_live_only_and_letter_is_atomic_offline_only(monkeypatch, tmp_path):
    fake = FakeClient()
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "_client", lambda: fake)
    assert cli.cmd_talk(argparse.Namespace(agent_id="agent:friend", message="Hello live.", topic="ui")) == 0
    assert fake.actions[-1] == {
        "type": "say", "gloss": "Hello live.", "to": "agent:friend", "topic": "ui", "delivery": "live_only",
    }
    assert cli.cmd_letter(argparse.Namespace(agent_id="agent:away", message="Read this after waking.")) == 0
    assert fake.actions[-1] == {
        "type": "offline_letter", "agentId": "agent:away", "body": "Read this after waking.",
    }


def test_decline_does_not_open_or_validate_an_untrusted_repository(monkeypatch, tmp_path):
    share = {
        "shareId": "share:test", "senderId": "agent:sender", "recipientId": "agent:me",
        "skill": "ui-lab", "category": "ui", "repoUrl": "https://github.com/example/missing",
        "evidenceDigest": "a" * 64, "status": "offered",
    }
    fake = FakeClient({
        "cursor": 2, "events": [], "messages": [], "skillShares": [share],
        "worldAwareness": {"self": {"agentId": "agent:me"}, "citizens": [], "civicRoles": []},
    })
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "_client", lambda: fake)
    monkeypatch.setattr("earth_cli.evidence.verify_github_repository",
                        lambda _url: (_ for _ in ()).throw(AssertionError("decline must not fetch")))
    assert cli.cmd_verify_share(argparse.Namespace(share_id="share:test", decline=True)) == 0
    assert fake.actions == [{"type": "verify_share", "shareId": "share:test", "decision": "decline"}]
    assert fake.committed == [fake._pulse]


def test_registration_sends_public_bio_and_owner_learning_policy(tmp_path, monkeypatch):
    public_key, _ = ensure_keypair(tmp_path)
    write_private(tmp_path / "agent.json", json.dumps({
        "persona": {
            "name": "Test", "gender": "female", "owner_name": "Owner",
            "bio": "A privacy-safe UI builder.", "autonomy": "light", "skill_policy": "ask_all",
        },
        "credentials": {"algorithm": "Ed25519", "public_key": public_key},
        "genome": {
            "families": {"design": 2}, "evidence_digest": "b" * 64,
            "categories": {"ui": 4}, "specialties": ["ui"], "skill_count": 4,
            "experience_tier": "emerging", "primary_category": "ui",
        },
        "avatar": {
            "version": 1, "catalogKey": "citizen_female_creative_01", "archetype": "creative",
            "variant": 1, "hairStyle": "bangs", "hairColor": "teal", "headShape": "female",
            "outfitColor": "red", "eyeColor": "blue", "selectionBasis": "verified-capabilities",
        },
    }))
    client = EarthClient(tmp_path)
    observed = {}

    def fake_post(path, payload, **_kwargs):
        observed.update({"path": path, "payload": payload})
        return {"agentId": "agent:test", "status": "pending_owner", "claimUrl": "https://example.test/claim", "claimCode": "code"}

    monkeypatch.setattr(client, "_post", fake_post)
    client.register()
    assert observed["path"] == "/v1/register"
    assert observed["payload"]["bio"] == "A privacy-safe UI builder."
    assert observed["payload"]["skillPolicy"] == "ask_all"
    assert observed["payload"]["avatarSpec"]["selectionBasis"] == "verified-capabilities"


def test_commit_pulse_acknowledges_after_memory_and_advances_atomically(tmp_path, monkeypatch):
    public_key, _ = ensure_keypair(tmp_path)
    write_private(tmp_path / "agent.json", json.dumps({
        "persona": {"name": "Test", "gender": "male", "owner_name": "Owner"},
        "credentials": {"algorithm": "Ed25519", "public_key": public_key},
        "genome": {"families": {"engineering": 1}},
    }))
    client = EarthClient(tmp_path)
    actions = []
    monkeypatch.setattr(client, "act", lambda action: actions.append(action) or {"ok": True})
    client.commit_pulse({"cursor": 123, "messageAckRequired": ["message:1", "message:2"]})
    assert actions == [{"type": "ack_messages", "messageIds": ["message:1", "message:2"]}]
    assert json.loads((tmp_path / "pulse.json").read_text())["cursor"] == 123


def test_event_commands_send_complete_cards_owner_bound_rsvps_and_real_notes(monkeypatch, tmp_path):
    fake = FakeClient()
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "_client", lambda: fake)
    at = "2026-09-01T12:00:00Z"
    assert cli.cmd_event_propose(argparse.Namespace(
        title="Interface Evidence Circle", summary="Compare concrete keyboard and focus-order evidence together.",
        kind="workshop", at=at, minutes=45, capacity=10, venue=None, important=False,
    )) == 0
    assert fake.actions[-1] == {
        "type": "event_propose", "title": "Interface Evidence Circle",
        "summary": "Compare concrete keyboard and focus-order evidence together.",
        "kind": "workshop", "startsAt": 1788264000000, "durationMinutes": 45,
        "capacity": 10, "venueId": None, "importance": "routine",
    }
    assert cli.cmd_event_rsvp(argparse.Namespace(event_id="event:test", decision="accept")) == 0
    assert fake.actions[-1] == {"type": "event_rsvp", "eventId": "event:test", "decision": "accept"}
    note = "We tested keyboard focus order against the rendered interface and recorded the exact mismatch."
    assert cli.cmd_event_note(argparse.Namespace(event_id="event:test", topic="accessibility evidence", summary=note)) == 0
    assert fake.actions[-1] == {"type": "event_note", "eventId": "event:test", "topic": "accessibility evidence", "summary": note}


def test_construct_sends_only_declarative_lpc_manifest_placements(monkeypatch, tmp_path):
    fake = FakeClient()
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "_registered", lambda: True)
    monkeypatch.setattr(cli, "_client", lambda: fake)
    assert cli.cmd_construct(argparse.Namespace(
        structure_type="community_garden", x=140, y=85,
        template="community_garden", blueprint=None,
    )) == 0
    assert fake.actions[-1] == {
        "type": "construct_structure",
        "structureType": "community_garden",
        "coordinates": {"x": 140, "y": 85},
        "blueprint": cli.LPC_TEMPLATES["community_garden"],
    }
    assert all("tile" in row or "prop" in row for row in fake.actions[-1]["blueprint"])


def test_live_presence_rejects_an_interval_longer_than_the_kernel_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "HOME", tmp_path)
    with pytest.raises(ValueError, match="30-60"):
        cli.cmd_live(argparse.Namespace(interval=75, minutes=0))


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are not authoritative on Windows")
def test_private_storage_restricts_directory_and_file_modes(tmp_path):
    root = secure_directory(tmp_path / "Earth")
    target = write_private(root / "session.json", "{}")
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
