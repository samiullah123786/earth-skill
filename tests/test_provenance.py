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
