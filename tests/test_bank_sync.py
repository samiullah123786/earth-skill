"""`Earth sync` must actually reach the Bank.

The first version of this path built a skillId out of a content digest - which
the Bank has never used as an id - and wrapped the whole thing in a bare
`except Exception: pass`. It threw on every skill, swallowed the error, and
printed nothing, so a citizen editing a banked skill had no way to know their
edit never left the machine. These tests pin the parts that were wrong: the id
comes from the deposit, an unchanged skill is not re-sent, and a skill that
turned unsafe or private since it was banked is held back rather than pushed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from earth_cli.banked import forget_banked, read_banked, record_banked

SKILL = """---
name: bread
description: Turn flour, water, salt and time into a loaf worth the oven heat.
version: 1.0
---

Mix. Rest. Fold. Bake until it sounds hollow.
"""


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    (tmp_path / "knowledge").mkdir()
    return tmp_path


def test_a_missing_ledger_is_an_empty_one(home: Path) -> None:
    assert read_banked(home) == {}


def test_a_corrupt_ledger_does_not_take_sync_down_with_it(home: Path) -> None:
    (home / "knowledge" / "banked.json").write_text("{not json", encoding="utf-8")
    assert read_banked(home) == {}


def test_the_bank_id_survives_a_round_trip(home: Path) -> None:
    record_banked(home, "/skills/bread", "bread", "skill:abc123", "d" * 64)
    entry = read_banked(home)["/skills/bread"]
    assert entry["skillId"] == "skill:abc123"
    assert entry["name"] == "bread"
    assert entry["contentDigest"] == "d" * 64


def test_a_deposit_with_no_id_is_not_recorded(home: Path) -> None:
    # A refused or held deposit returns no skillId. Writing a row for it would
    # make sync address a skill the Bank does not have.
    record_banked(home, "/skills/bread", "bread", "", "d" * 64)
    assert read_banked(home) == {}


def test_forgetting_removes_only_the_named_skill(home: Path) -> None:
    record_banked(home, "/skills/bread", "bread", "skill:1", "a" * 64)
    record_banked(home, "/skills/soup", "soup", "skill:2", "b" * 64)
    forget_banked(home, "/skills/bread")
    assert list(read_banked(home)) == ["/skills/soup"]


def test_forgetting_something_absent_is_not_an_error(home: Path) -> None:
    record_banked(home, "/skills/soup", "soup", "skill:2", "b" * 64)
    forget_banked(home, "/skills/never-banked")
    assert list(read_banked(home)) == ["/skills/soup"]


def test_the_ledger_holds_no_skill_content(home: Path) -> None:
    # It sits in the citizen's home beside the private index. It should carry
    # what sync needs to address a row and nothing a reader could mine.
    record_banked(home, "/skills/bread", "bread", "skill:1", "a" * 64)
    raw = (home / "knowledge" / "banked.json").read_text(encoding="utf-8")
    assert "Mix. Rest. Fold." not in raw
    assert set(json.loads(raw)["/skills/bread"]) == {"name", "skillId", "contentDigest"}


def _write_skill(folder: Path, text: str = SKILL) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_sync_sends_a_changed_skill_and_skips_an_unchanged_one(
    home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from earth_cli import cli

    folder = tmp_path / "skills" / "bread"
    digest = _write_skill(folder)
    record_banked(home, folder, "bread", "skill:bread", digest)

    sent: list[dict] = []

    class Stub:
        def act(self, action: dict) -> dict:
            sent.append(action)
            return {"ok": True, "synced": True, "version": "1.1"}

    monkeypatch.setattr(cli, "HOME", home)
    monkeypatch.setattr(cli, "_client", lambda: Stub())

    # Nothing has changed yet, so nothing should cross the wire.
    cli._sync_banked_skills()
    assert sent == []

    _write_skill(folder, SKILL.replace("version: 1.0", "version: 1.1"))
    cli._sync_banked_skills()
    assert len(sent) == 1
    assert sent[0]["type"] == "sync_skill"
    assert sent[0]["skillId"] == "skill:bread"
    assert sent[0]["markdownBody"].startswith("Mix. Rest. Fold.")
    assert len(sent[0]["contentDigest"]) == 64

    # And the ledger now remembers the new digest, so a second run is quiet.
    sent.clear()
    cli._sync_banked_skills()
    assert sent == []


def test_a_deleted_skill_drops_out_of_the_ledger(
    home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from earth_cli import cli

    folder = tmp_path / "skills" / "gone"
    record_banked(home, folder, "gone", "skill:gone", "a" * 64)
    monkeypatch.setattr(cli, "HOME", home)
    monkeypatch.setattr(cli, "_client", lambda: pytest.fail("must not call the Bank"))

    cli._sync_banked_skills()
    assert read_banked(home) == {}


def test_a_secret_pasted_in_after_banking_is_never_synced(
    home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    # Sync must not become the quiet path around the check a deposit gets.
    from earth_cli import cli

    folder = tmp_path / "skills" / "bread"
    digest = _write_skill(folder)
    record_banked(home, folder, "bread", "skill:bread", digest)
    _write_skill(folder, SKILL + '\nexport AWS_SECRET_ACCESS_KEY="AKIAIOSFODNN7EXAMPLE"\n'
                                 '\nsk-proj-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH\n')

    monkeypatch.setattr(cli, "HOME", home)
    monkeypatch.setattr(cli, "_client", lambda: pytest.fail("must not reach the Bank"))
    cli._sync_banked_skills()
