import io
import json
import urllib.error

import pytest

from earth_cli.identity import ensure_keypair
from earth_cli.network import CONNECTOR_USER_AGENT, EarthAPIError, EarthClient
from earth_cli.private_io import write_private


def client_at(home):
    public_key, _ = ensure_keypair(home)
    write_private(home / "agent.json", json.dumps({
        "credentials": {"public_key": public_key},
        "registration": {"agent_id": "agent:trial"},
    }))
    return EarthClient(home)


def test_signed_api_identifies_itself_without_impersonating_a_browser(tmp_path, monkeypatch):
    client = client_at(tmp_path)
    seen = []

    def transport(request, timeout):
        seen.append(request)
        return io.BytesIO(b'{"ok":true}')

    monkeypatch.setattr("urllib.request.urlopen", transport)
    assert client._post("/v1/act", {"action": {"type": "pulse"}}, ticket="local-ticket") == {"ok": True}
    request = seen[0]
    assert request.get_header("User-agent") == CONNECTOR_USER_AGENT
    assert request.get_header("X-earth-agent") == "agent:trial"
    assert request.get_header("X-earth-signature")
    assert request.get_header("Authorization") == "Bearer local-ticket"


def test_edge_rejection_is_distinguished_from_kernel_refusal(tmp_path, monkeypatch):
    client = client_at(tmp_path)

    def blocked(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b"error code: 1010"))

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    with pytest.raises(EarthAPIError, match="before the Kernel.*1010"):
        client._post("/v1/register", {})

    def kernel_refusal(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"ok":false,"why":"owner claim required"}'))

    monkeypatch.setattr("urllib.request.urlopen", kernel_refusal)
    with pytest.raises(EarthAPIError, match="owner claim required"):
        client._post("/v1/enter", {})
