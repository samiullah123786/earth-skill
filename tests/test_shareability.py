"""What a citizen may give away, and what is never theirs to give."""
from __future__ import annotations

from earth_cli import shareability


def test_the_case_this_was_built_for():
    """pawtold-scriptwriter: good craft wearing a client's name."""
    result = shareability.assess(
        "pawtold-scriptwriter",
        "# Pawtold Scriptwriter\nWrite scripts for the Pawtold channel in the Pawtold voice.",
    )
    assert result.verdict == "rewrite"
    assert result.subject == "pawtold"
    assert result.generic_name == "scriptwriter"
    assert result.subject_mentions >= 3
    assert not result.may_deposit
    guidance = shareability.rewrite_guidance(result)
    assert any("scriptwriter" in step for step in guidance)
    assert any("stays on this machine" in step for step in guidance)


def test_a_craft_skill_is_simply_shareable():
    result = shareability.assess("scriptwriter", "# Scriptwriter\nHow to structure a three-act short.")
    assert result.verdict == "shareable"
    assert result.may_deposit


def test_a_generic_two_word_name_names_nobody():
    for name in ("python-developer", "video-editor", "seo-writer", "youtube-scriptwriter"):
        assert shareability.assess(name, "generic craft notes").verdict == "shareable", name


def test_a_leaked_credential_is_never_shareable():
    """Rotate it, do not publish it. No amount of editing prose fixes this."""
    for text in ("api_key = sk-livetokenvalue0000000", "token: ghp_aaaaaaaaaaaaaaaaaaaa"):
        result = shareability.assess("deploy", text)
        assert result.verdict == "private", result.as_dict()
        assert result.reasons


def test_traces_of_a_person_are_lines_to_fix_not_reasons_to_withhold():
    """Blocking on these refused nine good skills on the first real machine."""
    cases = {
        "notes": "contact me at someone@example.com for the brief",
        "runner": r"open C:\Users\rgb\Documents\clients\brief.md",
        "sync": "posts to http://192.168.1.44/hook",
    }
    for name, text in cases.items():
        result = shareability.assess(name, text)
        assert result.verdict == "rewrite", f"{name}: {result.as_dict()}"
        assert shareability.rewrite_guidance(result), "a fixable skill must say how to fix it"


def test_a_dev_server_is_not_a_privacy_leak():
    """Every tutorial ever written mentions localhost."""
    for text in ("run it on http://localhost:3000", "open http://127.0.0.1:8080/preview"):
        assert shareability.assess("remotion-docs", text).verdict == "shareable", text


def test_the_owner_saying_no_is_the_end_of_it():
    for text in ("Do not share this outside the team.", "CONFIDENTIAL - client work",
                 "Covered by an NDA.", "Internal use only."):
        result = shareability.assess("planner", text)
        assert result.verdict == "private"
        assert result.explain()


def test_a_private_marker_outranks_a_rewritable_name():
    """A rewrite is not on offer when the content itself is somebody's."""
    result = shareability.assess("pawtold-scriptwriter", "Confidential. Voice guide for the client.")
    assert result.verdict == "private"


def test_a_verdict_can_always_explain_itself():
    for name, text in (("scriptwriter", "craft"), ("pawtold-scriptwriter", "Pawtold"),
                       ("x", "email me at a@b.co")):
        assert shareability.assess(name, text).explain()


def test_judging_a_whole_folder(tmp_path):
    folder = tmp_path / "pawtold-scriptwriter"
    folder.mkdir()
    (folder / "SKILL.md").write_text("# Scriptwriting\nStructure and pacing.", encoding="utf-8")
    (folder / "voice.md").write_text("The Pawtold tone is warm and quick.", encoding="utf-8")
    result = shareability.assess_folder("pawtold-scriptwriter", folder)
    assert result.verdict == "rewrite"
    assert result.subject == "pawtold"


def test_a_folder_carrying_a_secret_is_private(tmp_path):
    folder = tmp_path / "deployer"
    folder.mkdir()
    (folder / "SKILL.md").write_text("# Deployer\nShips the build.", encoding="utf-8")
    (folder / "config.json").write_text('{"token": "ghp_aaaaaaaaaaaaaaaaaaaa"}', encoding="utf-8")
    assert shareability.assess_folder("deployer", folder).verdict == "private"
