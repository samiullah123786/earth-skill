import json

from earth_cli.avatar import render_avatar
from earth_cli.genesis import build_identity, classify, discover_skills, github_repository, git_remote_repository
from earth_cli.evidence import normalize_github_repository
from earth_cli.avatar_identity import derive_avatar_identity
from earth_cli.memory import initialize_memory, memory_summary, remember_pulse


def test_genesis_reads_complete_skill_and_keeps_digest_evidence(tmp_path):
    folder = tmp_path / "deep-capability"
    folder.mkdir()
    content = "---\nname: deep-capability\ndescription: neutral helper\n---\n" + ("context " * 1000) + " threat vulnerability hardening security"
    (folder / "SKILL.md").write_text(content, encoding="utf-8")
    skills = discover_skills([tmp_path])
    assert len(skills) == 1
    assert skills[0]["content_bytes"] == len(content.encode())
    assert len(skills[0]["digest"]) == 64
    assert classify(skills[0]) == "security"


def test_identity_categories_and_experience_are_computed():
    skills = [{
        "name": f"ui-system-{index}", "description": "UI interface component accessibility",
        "content": "React CSS design system user experience", "content_bytes": 40,
        "digest": f"{index:064x}",
    } for index in range(16)]
    identity = build_identity({"name": "Pixel", "gender": "female"}, skills)
    assert identity["genome"]["primary_category"] == "ui"
    assert identity["genome"]["experience_tier"] == "seasoned"
    assert identity["genome"]["content_bytes_read"] == 640
    assert len(identity["genome"]["evidence_digest"]) == 64


def test_avatar_identity_is_reproducible_and_capability_aware():
    design = build_identity({"name": "Pixel", "gender": "female"}, [{
        "name": "ui", "description": "UI interface accessibility", "content": "React CSS UX",
        "content_bytes": 12, "digest": "1" * 64,
    }])
    first = derive_avatar_identity(design, "public-key")
    second = derive_avatar_identity(design, "public-key")
    assert first == second
    assert first["archetype"] == "creative"
    assert first["catalogKey"].startswith("citizen_female_creative_")
    assert first["selectionBasis"] == "verified-capabilities"
    assert first["hairStyle"]
    assert first["headShape"] in {"female", "female_small"}


def test_avatar_identity_changes_with_signed_agent_identity():
    identity = build_identity({"name": "Builder", "gender": "male"}, [])
    appearances = {derive_avatar_identity(identity, f"public-key-{index}")["catalogKey"] for index in range(12)}
    assert len(appearances) >= 6


def test_avatar_identity_matches_shared_kernel_vector():
    identity = {
        "persona": {"name": "Pixel", "gender": "female"},
        "genome": {"evidence_digest": "1" * 64, "primary_category": "ui", "families": {"design": 1}},
    }
    assert derive_avatar_identity(identity, "public-key") == {
        "version": 1, "catalogKey": "citizen_female_creative_10", "archetype": "creative", "variant": 10,
        "hairStyle": "pixie", "hairColor": "gold", "headShape": "female_small",
        "outfitColor": "forest", "eyeColor": "violet", "selectionBasis": "verified-capabilities",
    }


def test_memory_is_private_append_only_and_deduplicated(tmp_path):
    root = initialize_memory(tmp_path)
    pulse = {
        "events": [{"id": "event:1", "kind": "arrive", "gloss": "A citizen arrived."}],
        "messages": [{"id": "message:1", "senderId": "agent:sage-0004", "body": "Welcome."}],
    }
    assert remember_pulse(tmp_path, pulse) == {"events": 1, "messages": 1}
    assert remember_pulse(tmp_path, pulse) == {"events": 0, "messages": 0}
    assert memory_summary(tmp_path)["relationships"] == 1
    assert "owner data" in (root / "WORLD.md").read_text(encoding="utf-8")
    assert len((root / "letters.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_memory_keeps_latest_signed_locations_and_learning_ledger(tmp_path):
    pulse = {
        "events": [], "messages": [],
        "worldAwareness": {
            "observedAt": 123, "boundary": {"width": 64, "height": 48},
            "self": {"agentId": "agent:test", "current": {"x": 10, "y": 12}},
            "citizens": [
                {"agentId": "agent:test", "current": {"x": 10, "y": 12}},
                {"agentId": "agent:terra-land", "current": {"x": 34, "y": 24}, "home": None},
            ],
            "civicRoles": [{"agentId": "agent:terra-land", "role": {"name": "Land Steward"}}],
        },
        "skillLearning": [
            {"skill": "ui", "status": "learned"},
            {"skill": "security", "status": "pending_owner"},
        ],
        "buildGuide": {
            "standard": "earthfolk-native-v1",
            "architectures": [{"id": "native"}, {"id": "modern-earthfolk"}],
            "features": ["entry-path", "small-plants", "pet-shelter"],
        },
    }
    assert remember_pulse(tmp_path, pulse) == {"events": 0, "messages": 0}
    summary = memory_summary(tmp_path)
    assert summary["known_citizens"] == 2
    assert summary["known_civic_roles"] == 1
    assert summary["learned_skills"] == 1
    assert summary["pending_skill_decisions"] == 1
    locations = json.loads((tmp_path / "memory" / "locations.json").read_text(encoding="utf-8"))
    assert locations["citizens"][1]["current"] == {"x": 34, "y": 24}
    building = json.loads((tmp_path / "memory" / "building.json").read_text(encoding="utf-8"))
    assert building["architectures"][1]["id"] == "modern-earthfolk"
    assert "modern-earthfolk" in (tmp_path / "memory" / "BUILDING.md").read_text(encoding="utf-8")


def test_avatar_escapes_agent_name():
    identity = {
        "persona": {"name": "<script>alert(1)</script>"},
        "colors": {"primary": "#3B82F6", "secondary": "#8B5CF6", "primary_family": "Engineering"},
        "genome": {"skill_count": 1, "families": {"engineering": 1}}, "stage": "sprout",
    }
    svg = render_avatar(identity)
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_repository_evidence_is_normalized_without_local_paths():
    assert github_repository("---\nname: earth\nrepository: https://github.com/example/earth-skill\n---\nInstructions") == "https://github.com/example/earth-skill"
    assert github_repository("See https://github.com/unrelated/docs in the instructions") is None
    assert normalize_github_repository("https://github.com/example/earth-skill.git") == "https://github.com/example/earth-skill"


def test_repository_evidence_uses_nearest_local_git_origin(tmp_path):
    skill = tmp_path / "skills" / "earth" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: earth\ndescription: helper\n---\n", encoding="utf-8")
    config = tmp_path / ".git" / "config"
    config.parent.mkdir()
    config.write_text('[remote "origin"]\n\turl = git@github.com:example/earth-skill.git\n', encoding="utf-8")
    assert git_remote_repository(skill) == "https://github.com/example/earth-skill"


def test_memory_remembers_live_relationship_topics_and_rank(tmp_path):
    pulse = {
        "events": [], "messages": [],
        "worldAwareness": {"self": {"agentId": "agent:me"}, "citizens": [], "civicRoles": []},
        "conversations": [{
            "id": "talk:1", "participantIds": ["agent:me", "agent:friend"],
            "topic": "frontend", "lines": [{"speaker": "agent:friend", "gloss": "Hello"}],
        }],
        "rank": {"rank": {"name": "Neighbor"}, "score": 6.5},
        "quests": [{"id": "knowledge-bridge", "complete": False}],
    }
    remember_pulse(tmp_path, pulse)
    state = json.loads((tmp_path / "memory" / "state.json").read_text(encoding="utf-8"))
    assert state["relationships"]["agent:friend"]["liveTalks"] == 1
    assert state["relationships"]["agent:friend"]["topics"] == ["frontend"]
    assert memory_summary(tmp_path)["rank"] == "Neighbor"
