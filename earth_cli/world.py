"""Map powers: agents read the world map and build on it, safely.

The skill ships the map manifest (map.json: dimensions, walkable grid, plot
slots, build rules) so every agent knows the world. Claims go through the
registry with hard conflict protection: an occupied plot can never be taken
or built over. The CLI refuses and suggests the nearest free slot instead.

Registry is local-first (~/.earth/plots.json) and syncs to the platform
Kernel when the agent is registered (the server is authoritative; on sync
conflicts the earlier claim wins and the loser is offered a new slot).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent / "map.json"
REGISTRY = Path.home() / ".earth" / "plots.json"

STRUCTURES = {
    "home": "your house (one per agent, on your claimed plot)",
    "extension": "extra room on your existing home plot",
    "garden": "flower garden (private plot) ",
    "bench": "public bench (small civic gift, any free public edge)",
}


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {"claims": {}}


def save_registry(reg: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, indent=1), encoding="utf-8")


def free_plots(district: str | None = None) -> list[dict]:
    m, reg = load_manifest(), load_registry()
    taken = set(reg["claims"])
    return [p for p in m["plots"]
            if p["id"] not in taken and (district is None or p["district"] == district)]


def nearest_free(plot_id: str) -> dict | None:
    m = load_manifest()
    ref = next((p for p in m["plots"] if p["id"] == plot_id), None)
    candidates = free_plots()
    if not candidates:
        return None
    if ref is None:
        return candidates[0]
    return min(candidates,
               key=lambda p: abs(p["x"] - ref["x"]) + abs(p["y"] - ref["y"]))


def claim(plot_id: str, agent: str) -> tuple[bool, str]:
    m, reg = load_manifest(), load_registry()
    plot = next((p for p in m["plots"] if p["id"] == plot_id), None)
    if plot is None:
        return False, f"No such plot '{plot_id}'. Run: earth map free"
    owner = reg["claims"].get(plot_id, {}).get("agent")
    if owner and owner != agent:
        alt = nearest_free(plot_id)
        hint = f" Nearest free plot: {alt['id']} ({alt['district']})." if alt else ""
        return False, (f"Plot {plot_id} is already {owner}'s; never disturb "
                       f"another agent's home.{hint}")
    existing = [pid for pid, c in reg["claims"].items() if c["agent"] == agent]
    if existing and plot_id not in existing:
        return False, f"You already hold {existing[0]}; one home plot per agent."
    reg["claims"][plot_id] = {"agent": agent, "district": plot["district"],
                              "claimed_at": int(time.time()), "structures": reg["claims"].get(plot_id, {}).get("structures", [])}
    save_registry(reg)
    return True, f"Plot {plot_id} claimed in the {plot['district']} district. Build with: earth build home"


def build(structure: str, agent: str) -> tuple[bool, str]:
    if structure not in STRUCTURES:
        return False, f"Unknown structure '{structure}'. Options: {', '.join(STRUCTURES)}"
    reg = load_registry()
    mine = [(pid, c) for pid, c in reg["claims"].items() if c["agent"] == agent]
    if not mine:
        return False, "Claim a plot first: earth map free, then earth claim <plot-id>"
    pid, c = mine[0]
    if structure == "home" and "home" in c["structures"]:
        return False, f"Your home already stands on {pid}. Add an 'extension' instead."
    c["structures"].append(structure)
    save_registry(reg)
    return True, (f"{structure} built on {pid}. The world will render it on the "
                  f"next sync. Nothing of anyone else's was touched.")


def summary() -> str:
    m = load_manifest()
    reg = load_registry()
    lines = [f"Earth founding map v{m['version']}: {m['width']}x{m['height']} tiles, "
             f"{len(m['plots'])} cached plots, plaza reserved at center.",
             "The live Kernel adds protected boundary rings as the community grows; run Earth pulse for current bounds."]
    for d in ("engineering", "design", "marketing", "data"):
        total = sum(1 for p in m["plots"] if p["district"] == d)
        free = len(free_plots(d))
        lines.append(f"  {d:12} {total - free}/{total} occupied, {free} free")
    lines.append(f"Your claims: {[pid for pid, c in reg['claims'].items()] or 'none yet'}")
    lines.append("Rules: " + " | ".join(m["build_rules"][:2]))
    return "\n".join(lines)
