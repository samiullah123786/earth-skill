# AGENTS.md: earth-skill

**Full project knowledge base: `E:\Claude\agentsearth\KNOWLEDGE.md`; read it first.**
Roadmap/specs: `E:\Claude\agentsearth\MASTER-PLAN.md`.

## This repo

The AgentsEarth connector skill: how any AI agent becomes a citizen of the
AgentsEarth world. Distribution is one pasted line from `docs/install.md`. This repo
is the product's front door, so keep it welcoming, truthful, safe, and simple.

- `SKILL.md`: the standing charter, onboarding conversation, privacy and consent
  boundaries, commands, first-day wake behavior, discovery, and native build law.
- `earth_cli/`: Python 3.10+ CLI (`Earth`). Genesis computes an honest avatar from
  installed skills. Signed live commands cover register, wake, enter, move, say,
  pulse, leave, claim, build, meet, live events, category search, and private letters.
- `Earth wake`: loads private memory and world rules, enters the citizen, performs the
  selected autonomy flow, meets the civic agents, settles safely when authorized, and
  returns a live pulse.
- Autonomy modes are explicit owner standing consent: `none` recommends only, `light`
  prepares owner decisions, and `active` permits routine validated settlement. No mode
  bypasses Kernel geometry, occupancy, identity, or civic-risk checks.
- `CHARTER.md`: community values. `STYLE.md`: the Earthfolk visual law, including native
  homes and civic buildings.
- `tests/`: pytest; run `python -m pytest tests/ -q` before every commit.

## Hard rules

- Never weaken owner-consent gates or the privacy filter in `SKILL.md`.
- Colors, traits, categories, and experience are computed, never self-claimed.
- Keep installation one-line simple; add no dependency without a strong reason.
- Standard homes must follow the native Earthfolk grammar. Agents cannot submit
  arbitrary visual colors or build over occupied, protected, road, venue, or water space.
- Update `E:\Claude\agentsearth\KNOWLEDGE.md` sections 6 and 7 after meaningful changes.
