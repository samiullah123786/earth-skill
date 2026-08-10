"""Phase D backtests: packing, extraction safety, and the install gate.

The install gate is the one place where another citizen's words become files the
owner's coding agent will read. Every refusal here is load-bearing.
"""
import io
import tarfile

import pytest

from earth_cli.install import (
    MIRROR_TARGETS,
    approve_pending,
    install_package,
    load_installs,
    mirrors,
    pack_skill,
    pending,
    set_mirror,
    skills_root,
    unpack,
)


def skill_folder(tmp_path, files, name="dashboard-layout"):
    root = tmp_path / "source" / name
    for relative, body in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return root


INERT = {"SKILL.md": "---\ndescription: grid layouts\n---\n# Layout\nUse twelve columns."}
ACTS = {"SKILL.md": "# Helper\nRuns a script.", "scripts/go.py": "print('hi')"}


# --- packing -------------------------------------------------------------

def test_packing_is_deterministic(tmp_path):
    source = skill_folder(tmp_path, INERT)
    assert pack_skill(source)["digest"] == pack_skill(source)["digest"]


def test_packing_reports_honest_counts(tmp_path):
    packed = pack_skill(skill_folder(tmp_path, ACTS))
    assert packed["fileCount"] == 2
    assert packed["sizeBytes"] == len(packed["payload"])


def test_packing_an_empty_folder_is_refused(tmp_path):
    empty = tmp_path / "source" / "nothing"
    empty.mkdir(parents=True)
    with pytest.raises(ValueError, match="nothing publishable"):
        pack_skill(empty)


def test_a_round_trip_restores_every_file(tmp_path):
    packed = pack_skill(skill_folder(tmp_path, ACTS))
    written = unpack(packed["payload"], tmp_path / "out")
    assert sorted(written) == ["SKILL.md", "scripts/go.py"]
    assert (tmp_path / "out" / "scripts" / "go.py").read_text(encoding="utf-8") == "print('hi')"


# --- extraction can never escape ----------------------------------------

def _archive_with(name: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        data = b"owned"
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.mark.parametrize("name", ["../escaped.md", "../../escaped.md", "/etc/passwd", "nested/../../escaped.md"])
def test_archives_that_climb_out_are_refused(tmp_path, name):
    with pytest.raises(ValueError):
        unpack(_archive_with(name), tmp_path / "out")
    assert not (tmp_path / "escaped.md").exists()


def test_symlink_members_are_refused(tmp_path):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("link.md")
        info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ValueError, match="not a regular file"):
        unpack(buffer.getvalue(), tmp_path / "out")


# --- the install gate ----------------------------------------------------

def test_inert_knowledge_installs_when_the_owner_chose_safe_auto(tmp_path):
    packed = pack_skill(skill_folder(tmp_path, INERT))
    home = tmp_path / "home"
    result = install_package(home, "dashboard-layout", packed["payload"],
                             declared_digest=packed["digest"], policy="safe_auto")
    assert result["state"] == "installed"
    assert (skills_root(home) / "dashboard-layout" / "SKILL.md").is_file()


def test_ask_all_holds_even_inert_knowledge_for_the_owner(tmp_path):
    packed = pack_skill(skill_folder(tmp_path, INERT))
    home = tmp_path / "home"
    result = install_package(home, "dashboard-layout", packed["payload"],
                             declared_digest=packed["digest"], policy="ask_all")
    assert result["state"] == "pending_owner"
    assert not (skills_root(home) / "dashboard-layout").exists()


def test_code_carrying_knowledge_never_auto_installs(tmp_path):
    packed = pack_skill(skill_folder(tmp_path, ACTS))
    home = tmp_path / "home"
    result = install_package(home, "helper", packed["payload"],
                             declared_digest=packed["digest"], policy="safe_auto")
    assert result["state"] == "pending_owner"
    assert "executable_file" in result["flags"]
    assert "scripts/go.py" in result["note"]
    assert not (skills_root(home) / "helper").exists()


def test_changed_bytes_are_refused_and_leave_nothing_behind(tmp_path):
    packed = pack_skill(skill_folder(tmp_path, INERT))
    home = tmp_path / "home"
    result = install_package(home, "dashboard-layout", packed["payload"],
                             declared_digest="f" * 64, policy="safe_auto")
    assert result["state"] == "refused"
    assert "digest_mismatch" in result["flags"]
    assert not (skills_root(home) / "dashboard-layout").exists()
    assert not (skills_root(home) / ".pending" / "dashboard-layout").exists()


def test_a_held_package_installs_only_after_the_owner_approves(tmp_path):
    packed = pack_skill(skill_folder(tmp_path, ACTS))
    home = tmp_path / "home"
    install_package(home, "helper", packed["payload"], declared_digest=packed["digest"], policy="safe_auto")
    assert [row["name"] for row in pending(home)] == ["helper"]

    approved = approve_pending(home, "helper")
    assert approved["state"] == "installed"
    assert (skills_root(home) / "helper" / "scripts" / "go.py").is_file()
    assert pending(home) == []


def test_approving_something_that_is_not_waiting_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not waiting for review"):
        approve_pending(tmp_path / "home", "ghost")


def test_the_index_records_the_reason_a_package_was_held(tmp_path):
    packed = pack_skill(skill_folder(tmp_path, ACTS))
    home = tmp_path / "home"
    install_package(home, "helper", packed["payload"], declared_digest=packed["digest"], policy="safe_auto")
    row = load_installs(home)["installs"][-1]
    assert row["verdict"] == "needs_review"
    assert "NEEDS REVIEW" in row["note"]


# --- mirroring stays off until asked for --------------------------------

def test_nothing_reaches_the_real_coding_agent_by_default(tmp_path, monkeypatch):
    target = tmp_path / "claude-skills"
    monkeypatch.setitem(MIRROR_TARGETS, "claude", target)
    packed = pack_skill(skill_folder(tmp_path, INERT))
    home = tmp_path / "home"
    result = install_package(home, "dashboard-layout", packed["payload"],
                             declared_digest=packed["digest"], policy="safe_auto")
    assert mirrors(home) == []
    assert result["mirroredTo"] == []
    assert not target.exists()


def test_an_enabled_mirror_copies_into_that_environment_only(tmp_path, monkeypatch):
    claude, cursor = tmp_path / "claude-skills", tmp_path / "cursor-skills"
    monkeypatch.setitem(MIRROR_TARGETS, "claude", claude)
    monkeypatch.setitem(MIRROR_TARGETS, "cursor", cursor)
    home = tmp_path / "home"
    assert set_mirror(home, "claude", True) == ["claude"]

    packed = pack_skill(skill_folder(tmp_path, INERT))
    result = install_package(home, "dashboard-layout", packed["payload"],
                             declared_digest=packed["digest"], policy="safe_auto")
    assert result["mirroredTo"] == ["claude"]
    assert (claude / "dashboard-layout" / "SKILL.md").is_file()
    assert not cursor.exists()


def test_an_unknown_environment_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unknown environment"):
        set_mirror(tmp_path / "home", "notepad", True)
