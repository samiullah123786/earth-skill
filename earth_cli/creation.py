"""Declarative construction and crash-resumable submission, never code execution."""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .private_io import secure_directory, secure_file, write_private

MAX_BYTES = 32768
SHAPES = {"block", "beam", "floor", "roof", "door", "lamp", "switch"}
MATERIALS = {"plank", "stone", "brick", "glass", "thatch", "lantern"}


def validate_plan(plan: object) -> dict:
    """Bound transport data; the Kernel remains authoritative for geometry and law."""
    if not isinstance(plan, dict) or plan.get("version") != "earth-creation-v1":
        raise ValueError("plan must use version earth-creation-v1")
    if set(plan) - {"version", "name", "kind", "x", "y", "parts", "circuits", "bindings"}:
        raise ValueError("unknown plan fields; executable code is not accepted")
    if plan.get("kind", "object") not in {"home", "object"}:
        raise ValueError("creation kind must be home or object")
    if not isinstance(plan.get("name"), str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 '()-]{2,59}", plan["name"]):
        raise ValueError("public creation name must be 3–60 characters without URLs or paths")
    if any(isinstance(plan.get(key), bool) or not isinstance(plan.get(key), int) or plan[key] < 0 for key in ("x", "y")):
        raise ValueError("world anchor must use nonnegative whole tiles")
    encoded = json.dumps(plan, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ValueError("creation plan exceeds 32 KiB")
    parts = plan.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= 128:
        raise ValueError("creation needs 1 to 128 parts")
    ids = set()
    for part in parts:
        if not isinstance(part, dict) or set(part) - {"id", "shape", "material", "x", "y", "z", "w", "h", "d"}:
            raise ValueError("invalid part fields")
        if not isinstance(part.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", part["id"]) or part["id"] in ids:
            raise ValueError("parts need unique bounded IDs")
        ids.add(part["id"])
        if part.get("shape") not in SHAPES or part.get("material") not in MATERIALS:
            raise ValueError("unsupported shape or material")
        for field in ("x", "y", "z", "w", "h", "d"):
            value = part.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"part {field} must be finite")
            if field in {"w", "h", "d"} and value <= 0:
                raise ValueError("part dimensions must be positive")
            if isinstance(value, float) and not (value * 4).is_integer():
                raise ValueError("part coordinates and dimensions use quarter-unit increments")
            if value < 0 or value > (4 if field in {"y", "h"} else 8):
                raise ValueError("part exceeds the 8×8×4 construction envelope")
        if part["x"] + part["w"] > 8 or part["z"] + part["d"] > 8 or part["y"] + part["h"] > 4:
            raise ValueError("part exceeds the construction envelope")
        if part["shape"] == "floor" and (part["y"] != 0 or part["h"] > .25):
            raise ValueError("floors must be ground-level quarter-tile slabs")
        if part["shape"] == "door" and (part["w"] != 1 or part["d"] != 1 or part["h"] < 1.5):
            raise ValueError("doors need a whole tile and 1.5 tiles of clearance")
        if part["shape"] in {"lamp", "switch"} and part["w"] * part["h"] * part["d"] > 1:
            raise ValueError("lamps and switches must be compact fixtures")
    circuits = plan.get("circuits", [])
    bindings = plan.get("bindings", [])
    if not isinstance(circuits, list) or len(circuits) > 32 or not isinstance(bindings, list) or len(bindings) > 128:
        raise ValueError("circuits and bindings are bounded lists")
    for circuit in circuits:
        if not isinstance(circuit, dict) or set(circuit) - {"id", "type", "inputs", "period"} or circuit.get("type") not in {"switch", "and", "or", "not", "timer"}:
            raise ValueError("unsupported circuit; scripts are forbidden")
        if not isinstance(circuit.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", circuit["id"]) or not isinstance(circuit.get("inputs"), list) or len(circuit["inputs"]) > 8 or not all(isinstance(item, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", item) for item in circuit["inputs"]):
            raise ValueError("invalid circuit IDs or inputs")
        if circuit["type"] == "timer" and (isinstance(circuit.get("period"), bool) or not isinstance(circuit.get("period"), int) or not 5 <= circuit["period"] <= 3600):
            raise ValueError("timers require whole periods from 5 to 3600 seconds")
        if circuit["type"] in {"switch", "timer"} and circuit["inputs"] or circuit["type"] == "not" and len(circuit["inputs"]) != 1 or circuit["type"] in {"and", "or"} and not circuit["inputs"]:
            raise ValueError("circuit has the wrong number of inputs")
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {"partId", "signalId", "behavior"} or binding["partId"] not in ids or binding["behavior"] not in {"door", "light", "switch"} or not isinstance(binding["signalId"], str):
            raise ValueError("invalid behavior binding")
        part = next(part for part in parts if part["id"] == binding["partId"])
        signal = next((signal for signal in circuits if signal["id"] == binding["signalId"]), None)
        expected_shape = {"door": "door", "light": "lamp", "switch": "switch"}[binding["behavior"]]
        if part["shape"] != expected_shape or signal is None or binding["behavior"] == "switch" and signal["type"] != "switch":
            raise ValueError("binding must match its part and signal type")
    return plan


def read_plan(path: str) -> dict:
    source = Path(path).expanduser()
    try:
        with source.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("creation plan exceeds 32 KiB")
        return validate_plan(json.loads(raw))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read creation plan: {error}") from error


@contextmanager
def _job_lock(path: Path):
    """OS lock is released on crashes; concurrent terminals cannot mint duplicate intents."""
    secure_directory(path.parent)
    with path.open("a+b") as stream:
        secure_file(path)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            import os
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("creation job is in use by another terminal; retry after it finishes") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def build_resumable(client, home: Path, plan: dict, *, job: str | None = None, expected_revision: int | None = None, creation_id: str | None = None) -> dict:
    validate_plan(plan)
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    default_key = f"extend:{creation_id}:{expected_revision}:{digest}" if creation_id else digest
    key = hashlib.sha256((job or default_key).encode()).hexdigest()
    with _job_lock(home / "memory" / "create" / f"{key}.lock"):
        return _submit(client, home, plan, job=job or default_key, expected_revision=expected_revision, creation_id=creation_id)


def resume_job(client, home: Path, job: str, *, plan: dict | None = None, creation_id: str | None = None) -> dict | None:
    """Recover named home jobs before choosing another site or requesting a recipe."""
    key = hashlib.sha256(job.encode()).hexdigest()
    path = home / "memory" / "create" / f"{key}.json"
    with _job_lock(path.with_suffix(".lock")):
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if plan is not None:
            digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            if record["planDigest"] != digest:
                raise ValueError("job already belongs to a different plan; use another --job")
            if record.get("targetCreationId") != creation_id:
                raise ValueError("job belongs to a different creation target")
        if record.get("creationId"):
            return client.act({"type": "creation_inspect", "creationId": record["creationId"]})
        observed = client.act({"type": "creation_inspect"})
        for item in observed.get("creations", []):
            if item.get("requestId") == record["requestId"]:
                record["creationId"] = item["creationId"]
                write_private(path, json.dumps(record))
                return {"ok": True, **item}
        if record.get("approvalId"):
            return {"ok": True, "state": "awaiting_owner", "approvalId": record["approvalId"], "requestId": record["requestId"]}
    return None


def recover_build(client, home: Path, plan: dict, *, job: str | None = None, expected_revision: int | None = None, creation_id: str | None = None) -> dict | None:
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    label = job or (f"extend:{creation_id}:{expected_revision}:{digest}" if creation_id else digest)
    recovered = resume_job(client, home, label, plan=plan, creation_id=creation_id)
    if recovered is not None:
        return recovered
    key = hashlib.sha256(label.encode()).hexdigest()
    if (home / "memory" / "create" / f"{key}.json").exists():
        # Uncertain delivery must replay its existing idempotency key before
        # stale revision preview. The Kernel validates/deduplicates the request.
        return build_resumable(client, home, plan, job=label, expected_revision=expected_revision, creation_id=creation_id)
    return None


def _submit(client, home: Path, plan: dict, *, job: str | None = None, expected_revision: int | None = None, creation_id: str | None = None) -> dict:
    """Persist intent BEFORE the network; retry identical requests after uncertain delivery."""
    validate_plan(plan)
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    key = hashlib.sha256((job or digest).encode()).hexdigest()
    path = home / "memory" / "create" / f"{key}.json"
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["planDigest"] != digest:
            raise ValueError("job already belongs to a different plan; use another --job")
        if record.get("targetCreationId") != creation_id:
            raise ValueError("job belongs to a different creation target")
        if record.get("creationId"):
            return client.act({"type": "creation_inspect", "creationId": record["creationId"]})
        # Includes the response-lost case and owner approvals: discover, never
        # fabricate completion or create a fresh idempotency key.
        observed = client.act({"type": "creation_inspect"})
        for item in observed.get("creations", observed.get("items", [])):
            if item.get("requestId") == record["requestId"]:
                record["creationId"] = item.get("creationId", item.get("id"))
                write_private(path, json.dumps(record))
                return {"ok": True, **item}
        if record.get("approvalId"):
            return {"ok": True, "state": "awaiting_owner", "approvalId": record["approvalId"], "requestId": record["requestId"]}
    else:
        record = {"version": 1, "planDigest": digest, "requestId": "create_" + uuid.uuid4().hex}
        if expected_revision is not None:
            record["expectedRevision"] = expected_revision
        if creation_id is not None:
            record["targetCreationId"] = creation_id
        write_private(path, json.dumps(record))
    action = {"type": "creation_build", "plan": plan, "requestId": record["requestId"]}
    if "expectedRevision" in record:
        action["expectedRevision"] = record["expectedRevision"]
    if "targetCreationId" in record:
        action["creationId"] = record["targetCreationId"]
    result = client.act(action)
    if result.get("creationId"):
        record["creationId"] = result["creationId"]
    if result.get("approvalId"):
        record["approvalId"] = result["approvalId"]
    write_private(path, json.dumps(record))
    return result


def settle_home_resumable(client, home: Path, job: str, name: str | None = None) -> dict:
    """Persist the selected settlement style before land or construction requests."""
    key = hashlib.sha256(("settlement:" + job).encode()).hexdigest()
    path = home / "memory" / "create" / f"{key}.json"
    with _job_lock(path.with_suffix(".lock")):
        chosen_name = name or "Timber Courtyard Home"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["name"] != chosen_name:
                raise ValueError("settlement job already has another name")
        else:
            record = {"requestId": "home_" + uuid.uuid4().hex, "name": chosen_name}
            write_private(path, json.dumps(record))
        return client.act({"type": "creation_home", **record})


def watch_creation(client, result: dict, seconds: int) -> dict:
    if not 0 <= seconds <= 300:
        raise ValueError("--watch-seconds must be between 0 and 300")
    deadline = time.monotonic() + seconds
    if isinstance(result.get("creation"), dict):
        result = {"ok": result.get("ok", True), **result["creation"]}
    creation_id = result.get("creationId")
    while creation_id and result.get("state") in {"building", "queued", "constructing"} and time.monotonic() < deadline:
        if deadline - time.monotonic() < 3:
            break
        time.sleep(3)
        result = client.act({"type": "creation_inspect", "creationId": creation_id})
        # Inspect envelopes carry the authoritative record separately.
        if isinstance(result.get("creation"), dict):
            result = {"ok": result.get("ok", True), **result["creation"]}
    return result
