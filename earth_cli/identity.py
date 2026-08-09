"""Local Ed25519 identity material.

The private key never leaves the owner's machine. agent.json contains only the
public key; the restrictive agent.key file signs Kernel requests.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def ensure_keypair(out_dir: str | Path) -> tuple[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key_file = out / "agent.key"
    if key_file.exists():
        private = Ed25519PrivateKey.from_private_bytes(_decode(key_file.read_text(encoding="ascii").strip()))
    else:
        private = Ed25519PrivateKey.generate()
        raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        key_file.write_text(_b64url(raw), encoding="ascii")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return _b64url(public), key_file


def load_private_key(path: str | Path) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_decode(Path(path).read_text(encoding="ascii").strip()))


def b64url(data: bytes) -> str:
    return _b64url(data)
