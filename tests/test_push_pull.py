"""Earth push stages-and-lists in one motion; Earth pull refuses to write a
byte until the digest matches and the Kernel's signature verifies."""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from earth_cli import cli


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class MarketClient:
    """A client whose market and acts are scripted, and whose downloads are real bytes."""

    def __init__(self, listing, detail, verify_info, payload, act_script):
        self._market = {"/v1/market?limit=50": {"ok": True, "listings": [listing]},
                        f"/v1/market/{listing['id']}": detail,
                        "/v1/verify": verify_info}
        self._payload = payload
        self._script = list(act_script)
        self.acts = []

    def market_json(self, path):
        return self._market[path]

    def act(self, action):
        self.acts.append(action)
        return self._script.pop(0)

    def download_bytes(self, _url):
        return self._payload


def _fixture(tmp_path, *, tamper_bytes=False, tamper_signature=False, verified=True):
    payload = b"the exact archive bytes"
    digest = hashlib.sha256(payload).hexdigest()

    key = Ed25519PrivateKey.generate()
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    signed_at = 1_786_000_000_000
    message = f"earth-verified-v1\n{digest}\ninert_safe\nearth-safety-2\n{signed_at}".encode()
    signature = key.sign(message)
    if tamper_signature:
        signature = bytes([signature[0] ^ 0xFF]) + signature[1:]

    listing = {"id": "asset:pull1", "name": "pull-probe", "digest": digest, "price": 0,
               "pulls": 0, "verified": verified, "forkOf": None, "rank": 0, "oneLiner": "x"}
    detail = {"ok": True, **listing,
              "scanner": {"verdict": "inert_safe", "scannerVersion": "earth-safety-2"},
              "earthVerified": ({"signature": _b64u(signature), "signedAt": signed_at,
                                 "scannerVersion": "earth-safety-2", "algorithm": "ed25519"} if verified else None),
              "author": {"agentId": "agent:author", "name": "Author"}}
    verify_info = {"ok": True, "publicKey": _b64u(public_raw), "algorithm": "ed25519"}
    delivered = payload if not tamper_bytes else b"different bytes entirely"
    script = [
        {"ok": True, "mode": "counter_sale", "tradeId": "trade:t1"},
        {"ok": True, "downloadUrl": "https://blob/x", "digest": digest, "name": "pull-probe"},
        {"ok": True, "state": "installed"},
    ]
    return MarketClient(listing, detail, verify_info, delivered, script)


def _run_pull(monkeypatch, tmp_path, client, *, install_state="installed"):
    installs = []
    monkeypatch.setattr(cli, "HOME", tmp_path)
    monkeypatch.setattr(cli, "_client", lambda: client)
    monkeypatch.setattr(cli, "_identity", lambda: {"persona": {"skill_policy": "safe_auto"}})
    import earth_cli.install as install_module
    # The real install_package contract: a record whose "state" is one of
    # installed | pending_owner | refused. There is no boolean "installed" key -
    # the first live pull proved that assumption wrong.
    monkeypatch.setattr(install_module, "install_package",
                        lambda home, name, payload, **kw: installs.append(name) or
                        {"name": name, "state": install_state,
                         "path": str(tmp_path / "skills" / name), "note": "inert prose"})
    code = cli.cmd_pull(argparse.Namespace(name="pull-probe"))
    return code, installs, client


def test_pull_verifies_digest_and_signature_then_installs(monkeypatch, tmp_path, capsys):
    code, installs, client = _run_pull(monkeypatch, tmp_path, _fixture(tmp_path))
    out = capsys.readouterr().out
    assert code == 0
    assert installs == ["pull-probe"]
    assert "digest verified" in out
    assert "signature checked against the published key" in out
    # The pull closed the loop: the install was confirmed under the buyer's key.
    assert client.acts[-1]["type"] == "confirm_install"


def test_pull_refuses_bytes_that_do_not_match_the_digest(monkeypatch, tmp_path, capsys):
    code, installs, _ = _run_pull(monkeypatch, tmp_path, _fixture(tmp_path, tamper_bytes=True))
    out = capsys.readouterr().out
    assert code == 1
    assert installs == []
    assert "do not match the market's digest" in out
    assert "Nothing was written" in out


def test_pull_refuses_a_badge_whose_signature_fails(monkeypatch, tmp_path, capsys):
    code, installs, _ = _run_pull(monkeypatch, tmp_path, _fixture(tmp_path, tamper_signature=True))
    out = capsys.readouterr().out
    assert code == 1
    assert installs == []
    assert "signature does not verify" in out


def test_pull_holds_a_pending_package_without_confirming_the_trade(monkeypatch, tmp_path, capsys):
    """A held package is neither an install nor a failure. The trade must stay
    'delivered' so the verified-install count only ever reflects real installs."""
    code, installs, client = _run_pull(monkeypatch, tmp_path, _fixture(tmp_path),
                                       install_state="pending_owner")
    out = capsys.readouterr().out
    assert code == 0
    assert installs == ["pull-probe"]
    assert "Held for the owner's review" in out
    assert "Earth approve-skill pull-probe" in out
    assert all(act["type"] != "confirm_install" for act in client.acts)


def test_pull_confirms_a_scanner_refusal_as_failed(monkeypatch, tmp_path, capsys):
    code, installs, client = _run_pull(monkeypatch, tmp_path, _fixture(tmp_path),
                                       install_state="refused")
    out = capsys.readouterr().out
    assert code == 0
    assert "REFUSED by the local scanner" in out
    confirm = client.acts[-1]
    assert confirm["type"] == "confirm_install"
    assert confirm["outcome"] == "failed"


def test_pull_installs_unbadged_listings_on_local_judgment_with_a_warning(monkeypatch, tmp_path, capsys):
    code, installs, _ = _run_pull(monkeypatch, tmp_path, _fixture(tmp_path, verified=False))
    out = capsys.readouterr().out
    assert code == 0
    assert installs == ["pull-probe"]
    assert "no badge" in out


def test_push_refuses_a_folder_without_a_skill_card(monkeypatch, tmp_path, capsys):
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "notes.txt").write_text("not a skill", encoding="utf-8")
    monkeypatch.setattr(cli, "HOME", tmp_path / ".Earth")
    code = cli.cmd_push(argparse.Namespace(path=str(bare), name=None, price=0,
                                           license="CC-BY-4.0", summary=None, fork_of=None))
    assert code == 1
    assert "no SKILL.md" in capsys.readouterr().out


def test_push_stages_then_hands_off_to_deposit(monkeypatch, tmp_path, capsys):
    source = tmp_path / "my_new_skill"
    source.mkdir()
    (source / "SKILL.md").write_text("# My new skill\n\nKnowledge.\n", encoding="utf-8")
    home = tmp_path / ".Earth"
    monkeypatch.setattr(cli, "HOME", home)
    monkeypatch.setattr(cli, "_rescan", lambda: [{"name": "my-new-skill"}])
    monkeypatch.setattr(cli, "_refresh_evidence", lambda entries: None)
    handed = {}
    monkeypatch.setattr(cli, "cmd_deposit", lambda args: handed.update(vars(args)) or 0)

    code = cli.cmd_push(argparse.Namespace(path=str(source), name=None, price=25,
                                           license="MIT", summary="Fresh.", fork_of="asset:parent1"))
    assert code == 0
    # Underscores become the market's dash convention, and the folder is staged
    # inside the agent's own skills so the evidence pipeline sees it.
    assert (home / "skills" / "my-new-skill" / "SKILL.md").is_file()
    assert handed["names"] == ["my-new-skill"]
    assert handed["price"] == 25
    assert handed["fork_of"] == "asset:parent1"
    assert handed["yes"] is True
