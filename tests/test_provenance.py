"""A1/A2 backtests: skill provenance deep-scan and genome wiring.

Every assertion checks computed evidence, never claims: sources come from
real paths, git remotes, or declared frontmatter; MCP names come from real
config files. No network, no fixtures outside tmp_path.
"""
import json

from earth_cli.genesis import (
    build_identity,
    discover_mcp_servers,
    discover_skills,
    skill_source,
)

PERSONA = {"name": "testa", "gender": "female"}


def make_skill(root, name, body="---\ndescription: testing skill\n---\n# S"):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    return d


def test_plugin_cache_path_classified_as_plugin(tmp_path):
    cache = tmp_path / ".claude" / "plugins" / "cache" / "market" / "pack"
    make_skill(cache, "seo-writer")
    skills = discover_skills([cache])
    assert len(skills) == 1
    assert skills[0]["source"] == "plugin"


def test_git_remote_resolves_to_github_source(tmp_path):
    repo = tmp_path / "clones" / "cool-skills"
    make_skill(repo, "deploy-helper")
    git = repo / ".git"
    git.mkdir()
    (git / "config").write_text(
        '[remote "origin"]\n\turl = git@github.com:someone/cool-skills.git\n',
        encoding="utf-8")
    skills = discover_skills([repo])
    assert skills[0]["repository"] == "https://github.com/someone/cool-skills"
    assert skills[0]["source"] == "github"


def test_declared_frontmatter_repository_counts_as_github(tmp_path):
    root = tmp_path / "skills"
    make_skill(root, "declared",
               "---\ndescription: has a declared home\n"
               "repository: https://github.com/org/declared-skill\n---\n# D")
    skills = discover_skills([root])
    assert skills[0]["repository"] == "https://github.com/org/declared-skill"
    assert skills[0]["source"] == "github"


def test_plain_local_skill_stays_local(tmp_path):
    root = tmp_path / "skills"
    make_skill(root, "handmade")
    skills = discover_skills([root])
    assert skills[0]["source"] == "local"
    assert skills[0]["repository"] is None


def test_plugin_cache_wins_over_git_remote(tmp_path):
    cache = tmp_path / ".claude" / "plugins" / "cache" / "pack"
    make_skill(cache, "cached")
    git = tmp_path / ".claude" / "plugins" / "cache" / ".git"
    git.mkdir()
    (git / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/market/pack\n',
        encoding="utf-8")
    skills = discover_skills([cache])
    assert skills[0]["source"] == "plugin"


def test_skill_source_never_claims_self_made():
    assert skill_source("C:/anywhere/skills/x/SKILL.md", None) == "local"


def test_discover_mcp_servers_names_only(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".claude.json").write_text(json.dumps({
        "mcpServers": {"playwright": {"command": "npx", "env": {"TOKEN": "secret"}}},
        "projects": {"E:/x": {"mcpServers": {"convex": {"url": "https://private"}}}},
    }), encoding="utf-8")
    servers = discover_mcp_servers()
    assert servers == ["convex", "playwright"]
    # names only - no URL, command, or env value survives
    assert all("secret" not in s and "https" not in s and "npx" not in s for s in servers)


def test_discover_mcp_servers_survives_broken_config(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".claude.json").write_text("{not json", encoding="utf-8")
    assert discover_mcp_servers() == []


def test_genome_carries_provenance_and_toolchain(tmp_path):
    root = tmp_path / "skills"
    make_skill(root, "one")
    make_skill(root, "two",
               "---\ndescription: shared skill\n"
               "repository: https://github.com/org/two\n---\n# T")
    cache = tmp_path / ".claude" / "plugins" / "cache" / "pack"
    make_skill(cache, "three")
    identity = build_identity(PERSONA, discover_skills([root, cache]),
                              mcp_servers=["convex", "playwright"])
    genome = identity["genome"]
    assert genome["provenance"] == {"local": 1, "github": 1, "plugin": 1}
    assert genome["public_repositories"] == ["https://github.com/org/two"]
    assert genome["mcp_server_count"] == 2
    # no filesystem path may leak into the public identity
    assert "local_path" not in json.dumps(identity)


def test_provenance_absent_skills_defaults_empty():
    identity = build_identity(PERSONA, [], mcp_servers=None)
    assert identity["genome"]["provenance"] == {}
    assert identity["genome"]["mcp_server_count"] == 0


def test_regenesis_preserves_registration(tmp_path):
    from earth_cli.genesis import run_genesis
    root = tmp_path / "skills"
    make_skill(root, "alpha")
    home = tmp_path / "home"
    run_genesis(PERSONA, extra_dirs=[str(root)], out_dir=home)
    identity = json.loads((home / "agent.json").read_text(encoding="utf-8"))
    identity["registration"] = {"agent_id": "agent:testa-123", "status": "citizen", "api": "x"}
    (home / "agent.json").write_text(json.dumps(identity), encoding="utf-8")
    key_before = (home / "agent.key").read_text(encoding="ascii")
    make_skill(root, "beta")
    refreshed = run_genesis(PERSONA, extra_dirs=[str(root)], out_dir=home)
    assert refreshed["registration"]["agent_id"] == "agent:testa-123"
    assert (home / "agent.key").read_text(encoding="ascii") == key_before
    assert {"alpha", "beta"} <= set(refreshed["genome"]["skills"])


def test_share_evidence_digest_matches_genesis_on_crlf(tmp_path):
    """Windows CRLF files must not be flagged as 'changed after genesis'."""
    from earth_cli.evidence import skill_evidence
    root = tmp_path / "skills"
    d = root / "crlf-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_bytes(
        b"---\r\ndescription: windows line endings\r\n---\r\n# CRLF\r\n")
    skills = discover_skills([root])
    home = tmp_path / "home"
    home.mkdir()
    (home / "genome-evidence.json").write_text(json.dumps({
        "version": 2,
        "skills": [{"name": s["name"], "digest": s["digest"],
                    "content_bytes": s["content_bytes"],
                    "local_path": s["local_path"],
                    "categories": s["categories"]} for s in skills],
    }), encoding="utf-8")
    card = skill_evidence(home, "crlf-skill")
    assert card["digest"] == skills[0]["digest"]


def test_unverified_links_auto_blocked():
    """C2 negative path: anything but a real https github.com project is refused."""
    import pytest
    from earth_cli.evidence import normalize_github_repository
    for bad in ["http://github.com/o/r", "https://gitlab.com/o/r",
                "https://github.com.evil.io/o/r", "https://github.com/onlyowner",
                "javascript:alert(1)"]:
        with pytest.raises(ValueError):
            normalize_github_repository(bad)
