import json

import pytest

from earth_cli import cli
from earth_cli.creation import build_resumable, read_plan, validate_plan
from earth_cli.network import EarthAPIError


def plan():
    return {"version": "earth-creation-v1", "kind": "home", "name": "Home", "x": 1, "y": 2,
            "parts": [{"id": "floor", "shape": "floor", "material": "plank",
                       "x": 0, "y": 0, "z": 0, "w": 2, "h": 0.25, "d": 2}],
            "circuits": [], "bindings": []}


class Client:
    def __init__(self):
        self.actions = []
        self.creations = []
        self.response_lost = False
        self.wait_owner = False

    def act(self, action):
        self.actions.append(action)
        kind = action["type"]
        if kind == "creation_recipe":
            return {"ok": True, "plan": plan()}
        if kind == "creation_preview":
            return {"ok": True, "valid": True, "cost": 10}
        if kind == "creation_inspect":
            if action.get("creationId"):
                return {"ok": True, "creation": self.creations[0]}
            return {"ok": True, "creations": self.creations}
        if kind == "creation_build":
            if self.wait_owner:
                return {"ok": True, "state": "awaiting_owner", "approvalId": "approval:1"}
            record = {"creationId": "creation:1", "state": "building", "requestId": action["requestId"]}
            self.creations = [record]
            if self.response_lost:
                raise EarthAPIError("connection lost after commit")
            return {"ok": True, **record}
        return {"ok": True, "state": "paused"}


def setup_cli(monkeypatch, tmp_path):
    fake = Client()
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "_registered", lambda: True)
    monkeypatch.setattr(cli, "_client", lambda: fake)
    return fake


def test_settlement_home_reuses_persisted_intent(monkeypatch, tmp_path):
    fake = setup_cli(monkeypatch, tmp_path)
    assert cli.main(["create", "home", "--settle", "--name", "Home"]) == 0
    assert cli.main(["create", "home", "--settle", "--name", "Home"]) == 0
    assert fake.actions[0] == fake.actions[1]
    assert fake.actions[0]["type"] == "creation_home"
    import re
    assert re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", fake.actions[0]["requestId"])


def test_build_request_id_matches_kernel_contract(tmp_path):
    import re
    fake = Client()
    build_resumable(fake, tmp_path, plan())
    assert re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", fake.actions[-1]["requestId"])


def test_home_previews_before_build_and_reports_actual_pending_state(monkeypatch, tmp_path, capsys):
    fake = setup_cli(monkeypatch, tmp_path)
    assert cli.main(["create", "home", "--name", "Home", "--job", "first-home"]) == 0
    assert [action["type"] for action in fake.actions] == ["creation_recipe", "creation_preview", "creation_build"]
    assert json.loads(capsys.readouterr().out)["state"] == "building"
    assert cli.main(["create", "home", "--job", "first-home"]) == 0
    assert sum(action["type"] == "creation_build" for action in fake.actions) == 1
    assert fake.actions[-1] == {"type": "creation_inspect", "creationId": "creation:1"}


def test_response_lost_after_commit_recovers_by_inspection_not_second_home(tmp_path):
    fake = Client()
    fake.response_lost = True
    with pytest.raises(EarthAPIError):
        build_resumable(fake, tmp_path, plan())
    job = next((tmp_path / "memory" / "create").glob("*.json"))
    intent = json.loads(job.read_text())
    assert intent["requestId"] == fake.actions[-1]["requestId"]
    recovered = build_resumable(fake, tmp_path, plan())
    assert recovered["creationId"] == "creation:1"
    assert sum(action["type"] == "creation_build" for action in fake.actions) == 1
    assert set(json.loads(job.read_text())) == {"version", "planDigest", "requestId", "creationId"}


def test_home_retry_does_not_request_new_site_after_response_lost(monkeypatch, tmp_path):
    fake = setup_cli(monkeypatch, tmp_path)
    fake.response_lost = True
    assert cli.main(["create", "home"]) == 1
    recipe_count = sum(action["type"] == "creation_recipe" for action in fake.actions)
    assert cli.main(["create", "home"]) == 0
    assert sum(action["type"] == "creation_recipe" for action in fake.actions) == recipe_count
    assert sum(action["type"] == "creation_build" for action in fake.actions) == 1


def test_concurrent_terminal_lock_prevents_duplicate_intent(tmp_path):
    import hashlib
    from earth_cli.creation import _job_lock
    key = hashlib.sha256(b"same-job").hexdigest()
    with _job_lock(tmp_path / "memory" / "create" / f"{key}.lock"):
        with pytest.raises(ValueError, match="another terminal"):
            build_resumable(Client(), tmp_path, plan(), job="same-job")


def test_quarter_grid_and_nonfinite_parts_are_rejected():
    changed = plan()
    changed["parts"][0]["x"] = 0.1
    with pytest.raises(ValueError, match="quarter-unit"):
        validate_plan(changed)
    changed["parts"][0]["x"] = float("nan")
    with pytest.raises(ValueError):
        validate_plan(changed)


def test_response_lost_before_commit_reuses_same_request_id(tmp_path):
    fake = Client()
    original = fake.act
    def offline(action):
        if action["type"] == "creation_build":
            fake.actions.append(action)
            raise EarthAPIError("offline before commit")
        return original(action)
    fake.act = offline
    with pytest.raises(EarthAPIError):
        build_resumable(fake, tmp_path, plan(), expected_revision=7)
    request = fake.actions[-1]
    fake.act = original
    build_resumable(fake, tmp_path, plan(), expected_revision=99)
    assert fake.actions[-1]["requestId"] == request["requestId"]
    assert fake.actions[-1]["expectedRevision"] == 7


def test_pending_approval_never_resubmits_but_discovers_approved_creation(tmp_path):
    fake = Client()
    fake.wait_owner = True
    build_resumable(fake, tmp_path, plan(), job="first")
    assert build_resumable(fake, tmp_path, plan(), job="first")["state"] == "awaiting_owner"
    request = next(action for action in fake.actions if action["type"] == "creation_build")
    fake.creations = [{"creationId": "approved:1", "requestId": request["requestId"], "state": "building"}]
    assert build_resumable(fake, tmp_path, plan(), job="first")["creationId"] == "approved:1"
    assert sum(action["type"] == "creation_build" for action in fake.actions) == 1


def test_job_reuse_for_different_plan_refused(tmp_path):
    fake = Client()
    build_resumable(fake, tmp_path, plan(), job="one")
    changed = plan()
    changed["name"] = "Other"
    with pytest.raises(ValueError, match="different plan"):
        build_resumable(fake, tmp_path, changed, job="one")


def test_script_and_oversize_data_rejected_before_action(tmp_path):
    malicious = plan()
    malicious["script"] = "print('never')"
    with pytest.raises(ValueError, match="unknown plan"):
        validate_plan(malicious)
    malicious = plan()
    malicious["parts"][0]["shape"] = "execute"
    with pytest.raises(ValueError, match="unsupported"):
        validate_plan(malicious)
    source = tmp_path / "huge.json"
    source.write_bytes(b" " * 32769)
    with pytest.raises(ValueError, match="32 KiB"):
        read_plan(str(source))


def test_controls_preserve_revision_and_use_event(monkeypatch, tmp_path):
    fake = setup_cli(monkeypatch, tmp_path)
    assert cli.main(["create", "pause", "creation:1", "--expected-revision", "4"]) == 0
    assert fake.actions[-1] == {"type": "creation_control", "creationId": "creation:1", "command": "pause", "expectedRevision": 4}
    assert cli.main(["create", "use", "creation:1", "door", "open"]) == 0
    assert fake.actions[-1] == {"type": "creation_use", "creationId": "creation:1", "partId": "door", "event": "open"}


def test_unregistered_create_never_uses_local_fallback(monkeypatch, tmp_path):
    fake = setup_cli(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "_registered", lambda: False)
    assert cli.main(["create", "home"]) == 1
    assert fake.actions == []


def test_catalog_exposes_only_public_vocabulary_without_identity(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda: (_ for _ in ()).throw(AssertionError("catalog never reads private identity")))
    assert cli.main(["create", "catalog"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["limits"]["parts"] == 128
    assert "door" in result["shapes"] and "plank" in result["materials"]


def test_switch_binding_is_explicit_and_can_feed_a_logic_gate():
    value = plan()
    value["parts"].append({"id": "switch", "shape": "switch", "material": "plank", "x": 0, "y": .25, "z": 0, "w": .25, "h": .25, "d": .25})
    value["circuits"] = [{"id": "power", "type": "switch", "inputs": []}, {"id": "inverse", "type": "not", "inputs": ["power"]}]
    value["bindings"] = [{"partId": "switch", "signalId": "power", "behavior": "switch"}]
    assert validate_plan(value) is value
    value["bindings"][0]["signalId"] = "inverse"
    with pytest.raises(ValueError, match="signal type"):
        validate_plan(value)


def test_extend_submits_target_revision_and_stable_request(monkeypatch, tmp_path):
    fake = setup_cli(monkeypatch, tmp_path)
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(plan()))
    assert cli.main(["create", "extend", "creation:existing", str(source), "--revision", "6", "--job", "room"]) == 0
    build = next(action for action in fake.actions if action["type"] == "creation_build")
    assert build["creationId"] == "creation:existing" and build["expectedRevision"] == 6
    preview = next(action for action in fake.actions if action["type"] == "creation_preview")
    assert preview["creationId"] == "creation:existing" and preview["expectedRevision"] == 6
    assert cli.main(["create", "extend", "creation:existing", str(source), "--revision", "6", "--job", "room"]) == 0
    assert sum(action["type"] == "creation_build" for action in fake.actions) == 1
    assert sum(action["type"] == "creation_preview" for action in fake.actions) == 1
    with pytest.raises(ValueError, match="different creation target"):
        build_resumable(fake, tmp_path, plan(), job="room", expected_revision=6, creation_id="creation:other")
