"""Phase A backtests: the owner-consented local knowledge bank.

Every assertion checks computed evidence from tmp_path only. No network, no
real home directory, and no file outside a consented root is ever opened.
"""
import hashlib
import json

import pytest

from earth_cli.knowledge import (
    ScanLimits,
    add_root,
    denied_reason,
    discover_knowledge,
    load_index,
    load_roots,
    plan_scan,
    remove_root,
    write_index,
)


def write(path, text, *, newline="\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline=newline)
    return path


# --- what the scan finds -------------------------------------------------

def test_skill_and_skills_markdown_are_both_evidence(tmp_path):
    write(tmp_path / "alpha" / "SKILL.md", "---\ndescription: one\n---\n# A")
    write(tmp_path / "beta" / "skills.md", "---\ndescription: two\n---\n# B")
    names = {entry["name"] for entry in discover_knowledge([tmp_path])}
    assert names == {"alpha", "beta"}


def test_plain_markdown_needs_an_owner_added_root(tmp_path):
    write(tmp_path / "notes" / "kubernetes-runbook.md", "# how we deploy")
    assert discover_knowledge([tmp_path]) == []
    entries = discover_knowledge([], knowledge_roots=[tmp_path])
    assert [entry["name"] for entry in entries] == ["kubernetes-runbook"]


def test_owner_root_still_prefers_the_skill_directory_name(tmp_path):
    write(tmp_path / "deslop" / "SKILL.md", "---\ndescription: prose\n---\n# D")
    entries = discover_knowledge([], knowledge_roots=[tmp_path])
    assert [entry["name"] for entry in entries] == ["deslop"]


# --- the denylist, applied before any read -------------------------------

@pytest.mark.parametrize("filename", [
    ".env", ".env.local", "api.key", "server.pem", "id_rsa",
    "credentials.md", "secrets.md", "my-secret-notes.md",
])
def test_denylist_refuses_secrets(tmp_path, filename):
    target = write(tmp_path / filename, "SUPER_SECRET=1")
    assert denied_reason(target) is not None
    entries = discover_knowledge([], knowledge_roots=[tmp_path])
    assert entries == []


@pytest.mark.parametrize("directory", [".git", "node_modules", "__pycache__", ".venv"])
def test_denied_directories_are_never_walked(tmp_path, directory):
    write(tmp_path / directory / "deep" / "SKILL.md", "---\ndescription: x\n---\n# X")
    assert discover_knowledge([tmp_path]) == []


def test_secret_material_is_never_opened(tmp_path, monkeypatch):
    write(tmp_path / "notes" / "safe.md", "# safe")
    write(tmp_path / "notes" / ".env", "TOKEN=live")
    opened: list[str] = []
    original = type(tmp_path).read_text

    def spy(self, *args, **kwargs):
        opened.append(self.name)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(tmp_path), "read_text", spy)
    discover_knowledge([], knowledge_roots=[tmp_path])
    assert ".env" not in opened


# --- digests obey the Windows CRLF law (KNOWLEDGE.md 7e) -----------------

def test_crlf_digest_hashes_normalized_text(tmp_path):
    body = "---\r\ndescription: windows\r\n---\r\n# CRLF\r\n"
    (tmp_path / "crlf").mkdir()
    (tmp_path / "crlf" / "SKILL.md").write_bytes(body.encode("utf-8"))
    entry = discover_knowledge([tmp_path])[0]
    normalized = body.replace("\r\n", "\n")
    assert entry["digest"] == hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    assert entry["digest"] != hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_digest_matches_genesis_for_the_same_file(tmp_path):
    from earth_cli.genesis import discover_skills
    write(tmp_path / "shared" / "SKILL.md", "---\ndescription: shared\n---\n# S")
    assert discover_skills([tmp_path])[0]["digest"] == discover_knowledge([tmp_path])[0]["digest"]


# --- size, binary, and cap behaviour -------------------------------------

def test_oversize_and_binary_files_are_skipped(tmp_path):
    write(tmp_path / "notes" / "huge.md", "x" * 4096)
    (tmp_path / "notes" / "blob.md").write_bytes(b"# title\x00\x01binary")
    limits = ScanLimits(max_file_bytes=1024)
    names = {e["name"] for e in discover_knowledge([], knowledge_roots=[tmp_path], limits=limits)}
    assert names == set()


def test_caps_stop_and_report_instead_of_truncating(tmp_path):
    for index in range(6):
        write(tmp_path / "notes" / f"n{index}.md", f"# note {index}")
    limits = ScanLimits(max_files=3)
    report = plan_scan([], knowledge_roots=[tmp_path], limits=limits)
    assert report.capped is True
    assert "3" in report.cap_reason and "file" in report.cap_reason.lower()


def test_uncapped_scan_reports_honest_totals(tmp_path):
    write(tmp_path / "notes" / "a.md", "# a")
    write(tmp_path / "notes" / "b.md", "# bb")
    report = plan_scan([], knowledge_roots=[tmp_path])
    assert report.capped is False
    assert report.file_count == 2
    assert report.total_bytes == len("# a") + len("# bb")


def test_plan_scan_reports_paths_without_reading_content(tmp_path):
    write(tmp_path / "notes" / "a.md", "# secret-looking body")
    report = plan_scan([], knowledge_roots=[tmp_path])
    serialized = json.dumps(report.as_dict())
    assert "secret-looking body" not in serialized
    assert report.paths and str(tmp_path) in report.paths[0]


# --- roots are explicit, consented, and bounded --------------------------

def test_roots_round_trip(tmp_path):
    home, root = tmp_path / "home", tmp_path / "docs"
    root.mkdir()
    add_root(home, root)
    assert [entry["path"] for entry in load_roots(home)] == [str(root.resolve())]
    remove_root(home, root)
    assert load_roots(home) == []


def test_adding_a_root_twice_is_idempotent(tmp_path):
    home, root = tmp_path / "home", tmp_path / "docs"
    root.mkdir()
    add_root(home, root)
    add_root(home, root)
    assert len(load_roots(home)) == 1


def test_home_and_filesystem_roots_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "user")
    (tmp_path / "user").mkdir()
    with pytest.raises(ValueError, match="whole home"):
        add_root(tmp_path / "home", tmp_path / "user")
    with pytest.raises(ValueError, match="drive root"):
        add_root(tmp_path / "home", tmp_path.anchor)


def test_missing_root_is_refused(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        add_root(tmp_path / "home", tmp_path / "nope")


# --- the private index ---------------------------------------------------

def test_index_never_stores_raw_content(tmp_path):
    write(tmp_path / "notes" / "a.md", "PRIVATE BODY TEXT")
    home = tmp_path / "home"
    entries = discover_knowledge([], knowledge_roots=[tmp_path])
    write_index(home, entries)
    raw = (home / "knowledge" / "index.json").read_text(encoding="utf-8")
    assert "PRIVATE BODY TEXT" not in raw
    assert load_index(home)["entries"][0]["digest"] == entries[0]["digest"]


def test_the_same_document_copied_into_two_roots_counts_once(tmp_path):
    """Identity is the name, so a copy of one document is not a second skill."""
    write(tmp_path / "one" / "guide.md", "# identical")
    write(tmp_path / "two" / "guide.md", "# identical")
    entries = discover_knowledge([], knowledge_roots=[tmp_path / "one", tmp_path / "two"])
    assert [entry["name"] for entry in entries] == ["guide"]


def test_two_skills_sharing_boilerplate_stay_distinct(tmp_path):
    """Byte-identical bodies must not collapse genuinely different skills."""
    body = "---\ndescription: starter\n---\n# S"
    write(tmp_path / "alpha" / "SKILL.md", body)
    write(tmp_path / "beta" / "SKILL.md", body)
    assert [entry["name"] for entry in discover_knowledge([tmp_path])] == ["alpha", "beta"]


def test_longest_copy_of_a_name_wins(tmp_path):
    write(tmp_path / "cache" / "seo" / "SKILL.md", "---\ndescription: short\n---\n# s")
    write(tmp_path / "local" / "seo" / "SKILL.md", "---\ndescription: long\n---\n# " + "l" * 200)
    entries = discover_knowledge([tmp_path / "cache", tmp_path / "local"])
    assert len(entries) == 1 and entries[0]["content_bytes"] > 200
