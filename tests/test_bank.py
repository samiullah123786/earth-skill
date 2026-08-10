"""The Bank's dedup key is the pack digest, so packing must be reproducible."""

import time

from earth_cli.install import normalized_content_digest, pack_skill


def _skill(tmp_path, name, body):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "SKILL.md").write_text(body, encoding="utf-8")
    return folder


def test_pack_is_deterministic_across_time(tmp_path):
    """gzip quietly stamps wall-clock time into its header unless pinned.

    Four bytes of clock changed every digest, which would have made every
    deposit unique and the Bank's master-copy law a fiction.
    """
    folder = _skill(tmp_path, "steady", "---\nname: steady\n---\n\n# Steady\nSame words.\n")
    first = pack_skill(folder)["digest"]
    time.sleep(1.1)
    second = pack_skill(folder)["digest"]
    assert first == second, "gzip mtime leaked into the digest again"


def test_identical_content_packs_identically_from_different_folders(tmp_path):
    body = "---\nname: twin\n---\n\n# Twin\nExactly the same knowledge.\n"
    one = _skill(tmp_path, "one", body)
    two = _skill(tmp_path, "two", body)
    assert pack_skill(one)["digest"] == pack_skill(two)["digest"]


def test_normalized_identity_sees_through_formatting(tmp_path):
    original = _skill(tmp_path, "orig", "---\nname: orig\nversion: 1\n---\n\n# Guide\n\nDo the thing  well.\n")
    reformatted = _skill(tmp_path, "copy", "---\nname: copy\nauthor: someone\n---\n# Guide\nDo the thing well.\n")
    different = _skill(tmp_path, "other", "---\nname: other\n---\n# Guide\nDo a different thing.\n")
    assert normalized_content_digest(original) == normalized_content_digest(reformatted)
    assert normalized_content_digest(original) != normalized_content_digest(different)
