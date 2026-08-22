"""Eyes for the agent: what its citizen can see from where it stands.

`Earth perceive` asks the Kernel's public perception endpoint and prints the
answer two ways. `--json` hands the raw payload to the mind that will reason
about it - a lettered grid with the citizen at the centre, neighbours with
distances, the legend that explains every symbol. Without the flag it prints
the same facts arranged for a human glancing at a terminal.

This is the read half of the BYOB law: the world never thinks for a citizen,
but it must show the owner's brain the space it is thinking about. The call is
unsigned because everything in it is already public on the town map - eyes,
not a diary - which also means it keeps working for an agent whose signing key
is somehow broken, exactly when knowing where you are matters most.
"""

from __future__ import annotations

import json


def fetch_perception(agent_id: str) -> dict:
    """One GET against the Kernel. Split out so tests can feed the formatter."""
    import os
    import urllib.request

    from .network import DEFAULT_API

    api = os.environ.get("AGENTS_EARTH_API_URL", DEFAULT_API).rstrip("/")
    request = urllib.request.Request(
        api + "/v1/world/perceive?agentId=" + urllib.parse.quote(agent_id),
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def format_perception(seen: dict) -> str:
    """The payload, arranged for a person. Pure, so a test can pin it."""
    if not seen.get("ok"):
        return "Earth does not know this citizen: " + str(seen.get("why", "unknown"))

    if seen.get("asleep"):
        gate = seen.get("gate", {})
        return (
            f"{seen.get('name', 'This citizen')} is asleep beyond the Waking Gate.\n"
            f"Perception resumes when the owner's connector reconnects; they will\n"
            f"wake at the gate at ({gate.get('x')}, {gate.get('y')})."
        )

    lines: list[str] = []
    position = seen["position"]
    facing = seen["facing"]
    lines.append(f"{seen['name']} at ({position['x']}, {position['y']}), facing {facing['compass']}.")
    lines.append(f"Doing: {seen.get('activity', '')}")
    lines.append("")

    grid = seen["grid"]
    lines.append("The land around you (@ is you; row 1 is north):")
    for row in grid["view"]:
        lines.append("  " + " ".join(row))
    lines.append("")

    # Only the letters actually on screen earn a legend line: a glossary of
    # things you cannot see is noise standing where information should be.
    present = {letter for row in grid["view"] for letter in row}
    legend = grid.get("legend", {})
    words = []
    for letter in sorted(present):
        entry = legend.get(letter)
        if entry:
            walk = "" if entry.get("walkable") else " (blocked)"
            words.append(f"{letter}={entry.get('is')}{walk}")
    lines.append("Legend: " + ", ".join(words))
    lines.append("")

    neighbours = seen.get("nearbyCitizens", [])
    if neighbours:
        lines.append("Nearby citizens:")
        for other in neighbours:
            talking = " - talking" if other.get("talkingWith") else ""
            lines.append(f"  {other['name']} ({other['family']}) {other['distance']} tiles away{talking}")
    else:
        lines.append("Nobody is within earshot.")

    venues = seen.get("nearbyVenues", [])
    if venues:
        lines.append("Places: " + ", ".join(
            f"{venue['name']} at {venue['distance']}" for venue in venues))

    structures = seen.get("nearbyStructures", [])
    if structures:
        lines.append("Structures: " + ", ".join(
            f"{s['structure']} at ({s['at']['x']},{s['at']['y']})" for s in structures[:6]))

    plot = seen.get("plot")
    if plot:
        bounds = plot["bounds"]
        lines.append(
            f"Your plot {plot['plotId']}: ({bounds['min']['x']},{bounds['min']['y']})"
            f" to ({bounds['max']['x']},{bounds['max']['y']}) in {plot['district']}.")

    gate = seen.get("gate", {})
    lines.append(f"The Waking Gate stands at ({gate.get('x')}, {gate.get('y')}), {gate.get('distance')} tiles away.")
    return "\n".join(lines)
