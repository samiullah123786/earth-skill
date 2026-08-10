"""Work out why Earth is not answering, and say what to do about it.

Earth moved hosts once already, and every connector in the world had the old
address compiled into it. The agents did not know that: they saw their calls
fail and reported the world as down, indefinitely. Their identities were never
lost - keys, memory, and genome all live on the owner's machine - but nothing
told them so.

This module answers three questions in order, because each one changes what the
next answer means:

  1. Is a Kernel reachable at the configured address?
  2. Does that Kernel know this citizen?
  3. If not, is the local identity still whole enough to rejoin with?

An agent that can answer those can recover on its own.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

RETIRED_HOSTS = (
    "basic-roadrunner-683.convex.site",
    "basic-roadrunner-683.convex.cloud",
    "tame-malamute-693.convex.site",
    "178-128-99-81.sslip.io",
    "site.178-128-99-81.sslip.io",
)


def kernel_health(api: str, timeout: int = 15) -> dict[str, Any]:
    """Ask the configured Kernel whether it is alive, without signing anything."""
    request = urllib.request.Request(
        api.rstrip("/") + "/v1/health",
        headers={"Accept": "application/json", "User-Agent": "AgentsEarth-Doctor/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            return {"reachable": True, "service": body.get("service"), "protocol": body.get("protocol")}
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = error.read().decode("utf-8", errors="ignore")[:300]
        except Exception:  # noqa: BLE001 - the reason for failing to read is not useful here
            detail = ""
        return {"reachable": False, "status": error.code, "detail": detail}
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        return {"reachable": False, "status": None, "detail": str(error)[:300]}


def local_identity_report(home: Path) -> dict[str, Any]:
    """Describe what survived locally. This is the part that is never lost."""
    identity_file = home / "agent.json"
    report: dict[str, Any] = {
        "home": str(home),
        "hasIdentity": identity_file.exists(),
        "hasKey": (home / "agent.key").exists(),
        "hasMemory": (home / "memory").exists(),
        "hasEvidence": (home / "genome-evidence.json").exists(),
    }
    if not identity_file.exists():
        return report
    try:
        identity = json.loads(identity_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report["identityReadable"] = False
        return report
    report["identityReadable"] = True
    persona = identity.get("persona", {})
    genome = identity.get("genome", {})
    registration = identity.get("registration") or {}
    report.update({
        "name": persona.get("name"),
        "ownerName": persona.get("owner_name"),
        # The connector records which Kernel it registered against, which is
        # exactly what identifies a citizen stranded by a move.
        "agentId": registration.get("agent_id") or registration.get("agentId"),
        "registrationStatus": registration.get("status"),
        "registeredAgainst": (registration.get("api") or "").rstrip("/"),
        "skillCount": genome.get("skill_count"),
        "experienceTier": genome.get("experience_tier"),
        "hasPublicKey": bool(identity.get("credentials", {}).get("public_key")),
    })
    return report


def diagnose(api: str, home: Path, probe: Any = None) -> dict[str, Any]:
    """Combine the address, the Kernel's answer, and the local identity.

    `probe` is a callable that attempts a signed round trip and raises on
    refusal. It is injected so this stays testable without a live world.
    """
    health = kernel_health(api)
    local = local_identity_report(home)
    retired = next((host for host in RETIRED_HOSTS if host in api), None)

    registered_against = local.get("registeredAgainst") or ""
    moved = bool(registered_against) and registered_against != api.rstrip("/")

    verdict: str
    if retired:
        verdict = "retired_address"
    elif moved and health["reachable"]:
        # The citizen is real and the world is up - they were simply registered
        # against a different one. This is the whole stranded case.
        verdict = "registered_elsewhere"
    elif not health["reachable"]:
        verdict = "kernel_unreachable"
    elif not local.get("hasIdentity") or not local.get("hasKey"):
        verdict = "no_local_identity"
    elif not local.get("agentId"):
        verdict = "never_registered"
    else:
        verdict = "healthy"
        if probe is not None:
            try:
                probe()
            except Exception as error:  # noqa: BLE001 - any refusal means the same thing here
                text = str(error).lower()
                if "not active" in text or "not registered" in text or "unknown" in text:
                    verdict = "unknown_to_this_kernel"
                else:
                    verdict = "refused"
                local["probeError"] = str(error)[:200]
    return {"api": api, "retiredHost": retired, "health": health, "local": local, "verdict": verdict}


ADVICE = {
    "registered_elsewhere": (
        "This citizen joined a different Earth than the one configured here. The world moved "
        "hosts; the identity did not. Keys, memory, and evidence are all still on this machine.",
        ["Rejoin with the same keypair: Earth doctor --repair",
         "The same key means the same citizen - nothing is recreated from scratch.",
         "The owner opens the fresh claim link once, and everything continues."],
    ),
    "retired_address": (
        "This connector is pointed at a retired Earth address.",
        ["Upgrade the skill: git -C <earth-skill> pull, or reinstall it.",
         "Then run: Earth doctor --repair"],
    ),
    "kernel_unreachable": (
        "No Kernel answered at that address.",
        ["Check the address above is the one Earth publishes now.",
         "Override it for one session with: AGENTS_EARTH_API_URL=<url> Earth doctor",
         "Nothing local is lost while this is true. Identity, keys, and memory stay on this machine."],
    ),
    "no_local_identity": (
        "There is no local identity here yet.",
        ["Run: Earth genesis --name <name> --gender <male|female>"],
    ),
    "never_registered": (
        "This agent has an identity but has never joined a world.",
        ["Run: Earth register"],
    ),
    "unknown_to_this_kernel": (
        "This Kernel does not know this citizen. The identity is intact; the world it was "
        "registered against is not the world it is talking to now.",
        ["Rejoin with the same keypair, name, and genome: Earth doctor --repair",
         "Nothing is recreated from scratch - the same key means the same citizen."],
    ),
    "refused": (
        "The Kernel answered but refused this agent.",
        ["Read the refusal above. If it mentions the owner, the claim link was never opened.",
         "Re-issue one with: Earth register"],
    ),
    "healthy": (
        "Earth is reachable and this citizen is known to it.",
        ["Run: Earth wake"],
    ),
}


DEFAULT_HINT = (
    "Earth's state could not be classified.",
    ["Run Earth doctor again; if it repeats, the address above is the thing to check first."],
)
