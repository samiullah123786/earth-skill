import base64
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from earth_cli.identity import ensure_keypair
from earth_cli.network import EarthClient


def decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_genesis_key_is_stable_and_private_material_is_separate(tmp_path):
    first, key_file = ensure_keypair(tmp_path)
    second, same_file = ensure_keypair(tmp_path)
    assert first == second
    assert key_file == same_file
    assert len(decode(first)) == 32
    assert len(decode(key_file.read_text())) == 32


def test_wire_signature_covers_method_path_time_nonce_and_body(tmp_path):
    public_key, _ = ensure_keypair(tmp_path)
    (tmp_path / "agent.json").write_text(json.dumps({
        "persona": {"name": "Test", "gender": "male", "owner_name": "Owner"},
        "credentials": {"algorithm": "Ed25519", "public_key": public_key},
        "genome": {"families": {"engineering": 1}},
    }), encoding="utf-8")
    client = EarthClient(tmp_path)
    raw = b'{"action":{"type":"say","gloss":"hello"}}'
    headers = client._sign_headers("/v1/act", raw, "agent:test")
    message = (
        f"POST\n/v1/act\n{headers['X-Earth-Time']}\n{headers['X-Earth-Nonce']}\n"
        f"{hashlib.sha256(raw).hexdigest()}"
    ).encode()
    Ed25519PublicKey.from_public_bytes(decode(public_key)).verify(decode(headers["X-Earth-Signature"]), message)
