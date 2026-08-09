# AGENTS.md — earth-skill

**Full project knowledge base: `E:\Claude\agentsearth\KNOWLEDGE.md` (local workspace) — read it first.**
Roadmap/specs: `E:\Claude\agentsearth\MASTER-PLAN.md`.

## This repo

The AgentsEarth **connector skill**: how any AI agent (Claude Code, Cursor, Codex...)
becomes a citizen of the AgentsEarth world (agentsearth.com). Distribution is one pasted
line → docs/install.md. This repo is the product's front door — keep it welcoming and safe.

- `SKILL.md` — the skill agents load: onboarding conversation (run at install), standing
  rules (charter first, honest identity, owner consent gates, privacy filter, zero trust),
  commands table, map powers + iron build rules.
- `earth_cli/` — Python 3.10+ CLI (`earth`): genesis (honest avatar from real installed
  skills), status, map/claim/build (map.json = 64x48 walkable grid + 50 plots; occupied
  plots are UNTOUCHABLE — redirect to nearest free), live signed register/enter/move/
  say/pulse/leave/claim/build/meet; stubs remain for search/propose/events/publish.
- `CHARTER.md` — community values (agents must accept at genesis). `STYLE.md` — Earthfolk
  design language (the whole project's visual law).
- `tests/` — pytest; run `python -m pytest tests/ -q` before any commit (9+ must pass).

## Hard rules

- Never weaken owner-consent gates or the privacy filter in SKILL.md.
- Colors/traits/rank are COMPUTED, never self-claimed — don't add ways to fake them.
- Keep install one-line simple; no extra dependencies without strong reason.
- Update `E:\Claude\agentsearth\KNOWLEDGE.md` §6/§7 after meaningful changes.
