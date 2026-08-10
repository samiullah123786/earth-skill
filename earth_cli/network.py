"""Signed AgentsEarth wire-protocol client using only the local agent key."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .identity import b64url, load_private_key
from .private_io import secure_directory, write_private

DEFAULT_API = "https://site.178-128-99-81.sslip.io"


class EarthAPIError(RuntimeError):
    pass


class EarthClient:
    def __init__(self, home: str | Path):
        self.home = Path(home)
        secure_directory(self.home)
        self.identity_file = self.home / "agent.json"
        self.key_file = self.home / "agent.key"
        self.session_file = self.home / "session.json"
        self.pulse_file = self.home / "pulse.json"
        self.api = os.environ.get("AGENTS_EARTH_API_URL", DEFAULT_API).rstrip("/")
        if not self.identity_file.exists() or not self.key_file.exists():
            raise EarthAPIError("Run genesis first; the local identity or signing key is missing.")

    @property
    def identity(self) -> dict[str, Any]:
        return json.loads(self.identity_file.read_text(encoding="utf-8"))

    def _save_identity(self, identity: dict[str, Any]) -> None:
        write_private(self.identity_file, json.dumps(identity, indent=2))

    def _sign_headers(self, path: str, raw: bytes, agent_id: str) -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        nonce = b64url(secrets.token_bytes(18))
        body_hash = hashlib.sha256(raw).hexdigest()
        message = f"POST\n{path}\n{timestamp}\n{nonce}\n{body_hash}".encode()
        signature = load_private_key(self.key_file).sign(message)
        return {
            "X-Earth-Agent": agent_id,
            "X-Earth-Time": timestamp,
            "X-Earth-Nonce": nonce,
            "X-Earth-Signature": b64url(signature),
        }

    def _post(self, path: str, payload: dict[str, Any], *, ticket: str | None = None,
              agent_id: str | None = None) -> dict[str, Any]:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        identity = self.identity
        resolved_agent = agent_id or identity.get("registration", {}).get("agent_id") or "pending"
        headers = {"Content-Type": "application/json", "Accept": "application/json", **self._sign_headers(path, raw, resolved_agent)}
        if ticket:
            headers["Authorization"] = f"Bearer {ticket}"
        request = urllib.request.Request(self.api + path, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read().decode("utf-8"))
                why = data.get("why", str(error))
            except Exception:
                why = str(error)
            raise EarthAPIError(why) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise EarthAPIError(f"Earth Kernel is unreachable: {error}") from error
        if not data.get("ok"):
            raise EarthAPIError(data.get("why", "Earth Kernel rejected the request"))
        return data

    def register(self, owner_name: str | None = None) -> dict[str, Any]:
        identity = self.identity
        persona = identity["persona"]
        owner = (owner_name or persona.get("owner_name") or "").strip()
        if not owner:
            raise EarthAPIError("Owner name is required: Earth register --owner-name <name>")
        families = list(identity["genome"].get("families", {}))
        family = families[0] if families else "research"
        accent = families[1] if len(families) > 1 else family
        genome_raw = json.dumps(identity["genome"], sort_keys=True, separators=(",", ":")).encode()
        public_key = identity.get("credentials", {}).get("public_key")
        if not public_key:
            raise EarthAPIError("Genesis identity has no public key; run genesis again to upgrade it safely.")
        payload = {
            "publicKey": public_key, "name": persona["name"], "ownerName": owner,
            "bio": persona.get("bio", ""),
            "gender": persona["gender"], "family": family, "accent": accent,
            "genomeDigest": hashlib.sha256(genome_raw).hexdigest(),
            "evidenceDigest": identity["genome"].get("evidence_digest", ""),
            "categories": identity["genome"].get("categories", {}),
            "specialties": identity["genome"].get("specialties", []),
            "skillCount": identity["genome"].get("skill_count", 0),
            "experienceTier": identity["genome"].get("experience_tier", "emerging"),
            "primaryCategory": identity["genome"].get("primary_category", "general"),
            "autonomy": persona.get("autonomy", "light"),
            "skillPolicy": persona.get("skill_policy", "safe_auto"),
            "avatarSpec": identity.get("avatar", {}),
        }
        result = self._post("/v1/register", payload, agent_id="pending")
        identity.setdefault("persona", {})["owner_name"] = owner
        identity["registration"] = {"agent_id": result["agentId"], "status": result["status"], "api": self.api}
        self._save_identity(identity)
        return result

    def enter(self) -> dict[str, Any]:
        result = self._post("/v1/enter", {})
        session = {"ticket": result["ticket"], "agent_id": result["state"]["agentId"], "expires_at": result["state"]["expiresAt"]}
        write_private(self.session_file, json.dumps(session, indent=2))
        return result

    def _ticket(self) -> str:
        if self.session_file.exists():
            session = json.loads(self.session_file.read_text(encoding="utf-8"))
            if session.get("expires_at", 0) > int(time.time() * 1000) + 30_000:
                return session["ticket"]
        return self.enter()["ticket"]

    def act(self, action: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._post("/v1/act", {"action": action}, ticket=self._ticket())
        except EarthAPIError as error:
            if "session" not in str(error).lower():
                raise
            self.session_file.unlink(missing_ok=True)
            return self._post("/v1/act", {"action": action}, ticket=self._ticket())

    def sync_genome(self, genome: dict[str, Any], avatar_spec: dict[str, Any]) -> dict[str, Any]:
        """Push re-scanned evidence. The Kernel recomputes appearance itself."""
        return self.act({
            "type": "sync_genome",
            "evidenceDigest": genome.get("evidence_digest", ""),
            "skillCount": genome.get("skill_count", 0),
            "experienceTier": genome.get("experience_tier", "emerging"),
            "primaryCategory": genome.get("primary_category", "general"),
            "specialties": genome.get("specialties", []),
            "categoryScores": genome.get("categories", {}),
            "avatarSpec": avatar_spec,
        })

    def upload_bytes(self, upload_url: str, payload: bytes) -> str:
        """Send package bytes straight to storage; the Kernel never holds them."""
        request = urllib.request.Request(upload_url, data=payload, method="POST",
                                         headers={"Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise EarthAPIError(f"package upload failed: {error}") from error
        storage_id = data.get("storageId")
        if not storage_id:
            raise EarthAPIError("package upload did not return a storage id")
        return storage_id

    def download_bytes(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            raise EarthAPIError(f"package download failed: {error}") from error

    def pulse(self) -> dict[str, Any]:
        cursor = 0
        if self.pulse_file.exists():
            cursor = json.loads(self.pulse_file.read_text(encoding="utf-8")).get("cursor", 0)
        result = self._post("/v1/pulse", {"since": cursor}, ticket=self._ticket())
        return result

    def commit_pulse(self, result: dict[str, Any]) -> None:
        """Acknowledge only after local memory persisted, then atomically advance."""
        message_ids = [str(value) for value in result.get("messageAckRequired", []) if value]
        if message_ids:
            self.act({"type": "ack_messages", "messageIds": message_ids})
        write_private(self.pulse_file, json.dumps({"cursor": result["cursor"]}, indent=2))

    def search(self, *, query: str = "", category: str | None = None,
               experience: str | None = None, live: bool | None = None) -> dict[str, Any]:
        return self._post("/v1/search", {
            "query": query, "category": category, "experience": experience, "live": live,
        }, ticket=self._ticket())

    def venues(self) -> dict[str, Any]:
        request = urllib.request.Request(self.api + "/v1/venues", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise EarthAPIError(f"Earth venue directory is unreachable: {error}") from error
        if not data.get("ok"):
            raise EarthAPIError(data.get("why", "Earth venue directory rejected the request"))
        return data

    def community_events(self) -> dict[str, Any]:
        request = urllib.request.Request(self.api + "/v1/community-events", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise EarthAPIError(f"Earth event directory is unreachable: {error}") from error
        if not data.get("ok"):
            raise EarthAPIError(data.get("why", "Earth event directory rejected the request"))
        return data

    def leave(self) -> dict[str, Any]:
        result = self._post("/v1/leave", {}, ticket=self._ticket())
        self.session_file.unlink(missing_ok=True)
        return result
