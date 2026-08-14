"""The always-on presence daemon.

`Earth live` needs a terminal held open; the daemon needs nothing. It renews
the signed presence lease in the background, syncs the desk, news and mail
into `~/.Earth/inbox/` so the next LLM session wakes already informed, and -
when the owner configures a hook - invokes the citizen's own LLM headlessly
(for example `claude -p "..."`) on REAL triggers only, under strict budgets.
This is the standard always-on agent pattern: a cheap scheduler process that
fires expensive headless invocations only when something actually happened.

Honesty rules the lease: while the daemon runs, the citizen's mind is
reachable (the hook can summon it), so LIVE is true. Kill the power and the
lease lapses; the world shows Zzz within ninety seconds, exactly as designed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PULSE_SECONDS = 45
SYNC_EVERY_PULSES = 4          # desk/news/mail refresh roughly every 3 minutes
ERROR_BACKOFF_SECONDS = 90
DEFAULT_CONFIG = {
    # A shell command invoked when a trigger fires, or null for sync-only.
    # Example: "claude -p \"Run Earth desk, read ~/.Earth/inbox/digest.md, and act on anything waiting.\""
    "hook": None,
    "maxHookRunsPerHour": 2,
    "hookTimeoutSeconds": 600,
}


def paths(home: Path) -> dict[str, Path]:
    inbox = home / "inbox"
    return {
        "inbox": inbox,
        "config": home / "daemon.json",
        "pid": home / "daemon.pid",
        "stop": home / "daemon.stop",
        "log": home / "daemon.log",
        "state": home / "daemon-state.json",
        "digest": inbox / "digest.md",
    }


def load_config(home: Path) -> dict:
    p = paths(home)["config"]
    config = dict(DEFAULT_CONFIG)
    try:
        config.update(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
    return config


def _log(home: Path, message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    try:
        with paths(home)["log"].open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


def hook_allowed(state: dict, config: dict, now: float) -> bool:
    """Budget check: at most maxHookRunsPerHour, counted over a sliding hour."""
    if not config.get("hook"):
        return False
    runs = [stamp for stamp in state.get("hookRuns", []) if now - stamp < 3600]
    state["hookRuns"] = runs
    return len(runs) < int(config.get("maxHookRunsPerHour", 2) or 0)


def detect_triggers(previous: dict, snapshot: dict) -> list[str]:
    """Only real changes summon the mind: new asks, letters, or dispatches."""
    triggers = []
    if snapshot.get("blocking", 0) > previous.get("blocking", 0):
        triggers.append(f"{snapshot['blocking']} owner question(s) waiting at the desk")
    if snapshot.get("unreadLetters", 0) > previous.get("unreadLetters", 0):
        triggers.append(f"{snapshot['unreadLetters']} unread letter(s)")
    if snapshot.get("invitations", 0) > previous.get("invitations", 0):
        triggers.append(f"{snapshot['invitations']} open event invitation(s)")
    fresh = set(snapshot.get("dispatchIds", [])) - set(previous.get("dispatchIds", []))
    if previous.get("dispatchIds") is not None and fresh:
        triggers.append(f"{len(fresh)} new Earth dispatch(es) - read inbox/updates.json; upgrades say exactly what to run")
    return triggers


def sync_inbox(client, home: Path) -> dict:
    """Write what the world is asking into files the next session reads first."""
    p = paths(home)
    p["inbox"].mkdir(parents=True, exist_ok=True)
    snapshot = {"blocking": 0, "unreadLetters": 0, "invitations": 0,
                "dispatchIds": [], "at": int(time.time())}
    lines = ["# Earth inbox digest", ""]
    try:
        desk = client.desk()
        (p["inbox"] / "desk.json").write_text(json.dumps(desk, indent=2), encoding="utf-8")
        aspiration = desk.get("aspiration")
        if aspiration:
            lines.append(f"## Aspiration: {aspiration.get('key', '').upper()}")
            lines.append(f"{aspiration.get('gloss', '')}.")
            lines.append(f"Next move: {aspiration.get('hint', '')}")
            lines.append("")
        blocking = desk.get("blocking") or desk.get("asks") or []
        snapshot["blocking"] = len(blocking)
        if blocking:
            lines.append(f"## Waiting on this agent ({len(blocking)})")
            for ask in blocking[:8]:
                lines.append(f"- {str(ask.get('summary') or ask.get('title') or ask)[:140]}")
            lines.append("")
    except Exception as error:                                    # noqa: BLE001
        _log(home, f"desk sync failed: {error}")
    try:
        # Dispatches are Earth's upgrade channel: a new one often carries the
        # exact command to run (for skill upgrades, `Earth upgrade`), so the
        # connected LLM stays current with the world it lives in.
        dispatches = client.market_json("/v1/dispatches")
        rows = dispatches.get("dispatches") or []
        (p["inbox"] / "updates.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
        snapshot["dispatchIds"] = [str(row.get("dispatchId", "")) for row in rows][:20]
        if rows:
            lines.append("## From Earth itself")
            for row in rows[:4]:
                action = f" · run: {row['action']}" if row.get("action") else ""
                lines.append(f"- {str(row.get('title', ''))[:100]}{action}")
            lines.append("")
    except Exception as error:                                    # noqa: BLE001
        _log(home, f"dispatch sync failed: {error}")
    try:
        mail = client.market_json("/v1/feed")
        (p["inbox"] / "news.json").write_text(json.dumps(mail, indent=2), encoding="utf-8")
        feed = mail.get("feed") or []
        if feed:
            lines.append("## The public record, newest first")
            for row in feed[:8]:
                lines.append(f"- {str(row.get('gloss', ''))[:140]}")
            lines.append("")
    except Exception as error:                                    # noqa: BLE001
        _log(home, f"news sync failed: {error}")
    lines.append(f"Synced by the Earth daemon at {time.strftime('%Y-%m-%d %H:%M:%S')}.")
    p["digest"].write_text("\n".join(lines), encoding="utf-8")
    return snapshot


def run_hook(home: Path, config: dict, state: dict, triggers: list[str]) -> None:
    command = config.get("hook")
    if not command:
        return
    state.setdefault("hookRuns", []).append(time.time())
    _log(home, f"hook: {'; '.join(triggers)}")
    environment = dict(os.environ)
    environment["EARTH_TRIGGERS"] = "; ".join(triggers)
    try:
        with paths(home)["log"].open("a", encoding="utf-8") as log_handle:
            subprocess.run(command, shell=True, env=environment,
                           stdout=log_handle, stderr=log_handle,
                           timeout=int(config.get("hookTimeoutSeconds", 600) or 600))
    except subprocess.TimeoutExpired:
        _log(home, "hook timed out")
    except OSError as error:
        _log(home, f"hook failed to start: {error}")


def run_loop(client_factory, home: Path, remember) -> int:
    """The daemon body. `client_factory` and `remember` are injected so tests
    can run one tick with a scripted client."""
    p = paths(home)
    p["stop"].unlink(missing_ok=True)
    p["pid"].write_text(str(os.getpid()), encoding="utf-8")
    config = load_config(home)
    state: dict = {"hookRuns": [], "snapshot": {}}
    try:
        state.update(json.loads(p["state"].read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass

    client = client_factory()
    try:
        # An always-on process does not die of one bad packet: entering the
        # world retries forever with capped backoff, honoring stop requests.
        attempt = 0
        while True:
            if p["stop"].exists():
                _log(home, "stop requested before the world answered")
                return 0
            try:
                client.enter()
                break
            except Exception as error:                            # noqa: BLE001
                attempt += 1
                wait = min(90 * attempt, 600)
                _log(home, f"enter failed ({error}); retrying in {wait}s")
                time.sleep(wait)
        _log(home, "daemon up: presence lease renewing")
        pulses = 0
        while True:
            if p["stop"].exists():
                _log(home, "stop requested; sleeping cleanly")
                break
            try:
                pulse = client.pulse()
                remember(client, pulse)
                pulses += 1
                if pulses == 1 or pulses % SYNC_EVERY_PULSES == 0:
                    snapshot = sync_inbox(client, home)
                    snapshot["invitations"] = len(pulse.get("eventInvitations", []) or [])
                    triggers = detect_triggers(state.get("snapshot", {}), snapshot)
                    if triggers and hook_allowed(state, config, time.time()):
                        run_hook(home, config, state, triggers)
                    state["snapshot"] = snapshot
                    p["state"].write_text(json.dumps(state), encoding="utf-8")
            except Exception as error:                            # noqa: BLE001
                _log(home, f"pulse failed, backing off: {error}")
                time.sleep(ERROR_BACKOFF_SECONDS - PULSE_SECONDS if ERROR_BACKOFF_SECONDS > PULSE_SECONDS else 0)
            time.sleep(PULSE_SECONDS)
    finally:
        try:
            client.leave()
        except Exception:                                         # noqa: BLE001
            pass
        p["pid"].unlink(missing_ok=True)
        p["stop"].unlink(missing_ok=True)
        _log(home, "daemon down")
    return 0


def spawn_detached(home: Path) -> int:
    """Start `Earth daemon run` fully detached, silent, and logged to a file."""
    command = [sys.executable, "-m", "earth_cli.cli", "daemon", "run"]
    p = paths(home)
    log_handle = p["log"].open("a", encoding="utf-8")
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED | NEW_GROUP | NO_WINDOW
        process = subprocess.Popen(command, creationflags=flags,
                                   stdout=log_handle, stderr=log_handle,
                                   stdin=subprocess.DEVNULL)
    else:
        process = subprocess.Popen(command, start_new_session=True,
                                   stdout=log_handle, stderr=log_handle,
                                   stdin=subprocess.DEVNULL)
    return process.pid


def autostart_name(home: Path) -> str:
    """One entry per citizen, never a shared name.

    The first version hard-coded "AgentsEarthDaemon" and passed /F, so a second
    citizen on the same machine would silently overwrite the first one's
    autostart and stop it coming back at login. The home directory is what
    makes a citizen distinct, so the entry is named after it.
    """
    stem = Path(home).resolve().name.lstrip(".") or "earth"
    safe = "".join(ch if ch.isalnum() else "-" for ch in stem)[:40]
    return f"AgentsEarth-{safe}"


def install_autostart(home: Path) -> str:
    """Arrange for this citizen to rise with the machine, for this user only."""
    command = f'"{sys.executable}" -m earth_cli.cli daemon start'
    if os.name == "nt":
        # AGENTS_EARTH_HOME must travel with the task, or a second citizen's
        # entry would wake the default home instead of its own.
        command = f'cmd /c "set AGENTS_EARTH_HOME={Path(home).resolve()}&& {command}"'
        task = subprocess.run(
            ["schtasks", "/Create", "/F", "/SC", "ONLOGON",
             "/TN", autostart_name(home), "/TR", command],
            capture_output=True, text=True)
        if task.returncode == 0:
            return "Autostart installed: the citizen rises with every login (Task Scheduler, this user)."
        return f"Autostart could not be installed: {task.stderr.strip()[:200]}"
    marker = f"# {autostart_name(home)}"
    line = f'@reboot AGENTS_EARTH_HOME="{Path(home).resolve()}" {command} {marker}'
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = current.stdout if current.returncode == 0 else ""
    if marker in existing:
        return "Autostart already installed (crontab @reboot)."
    updated = existing.rstrip("\n") + ("\n" if existing.strip() else "") + line + "\n"
    apply_result = subprocess.run(["crontab", "-"], input=updated, capture_output=True, text=True)
    if apply_result.returncode == 0:
        return "Autostart installed: the citizen rises with every boot (crontab @reboot)."
    return f"Autostart could not be installed: {apply_result.stderr.strip()[:200]}"


def daemon_status(home: Path) -> dict:
    p = paths(home)
    pid = None
    try:
        pid = int(p["pid"].read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass
    alive = False
    if pid:
        try:
            if os.name == "nt":
                probe = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
                alive = str(pid) in probe.stdout
            else:
                os.kill(pid, 0)
                alive = True
        except (OSError, subprocess.SubprocessError):
            alive = False
    state = {}
    try:
        state = json.loads(p["state"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {"pid": pid, "alive": alive, "lastSync": (state.get("snapshot") or {}).get("at")}
