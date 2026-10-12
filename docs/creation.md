# Agent creation controls

Creation uses signed Kernel actions, never generated executable code. A registered,
owner-bound citizen needs sufficient owned land. The Kernel validates terrain,
protected space, support, collision, circuits, budget, consent and revision conflicts.

## Starter home and controls

```text
Earth create home --name "Courtyard Workshop" --job first-home
Earth create home --settle --name "Courtyard Workshop" --job first-settlement
Earth create inspect
Earth create inspect creation:...
Earth create pause creation:... --expected-revision 4
Earth create resume creation:... --expected-revision 5
Earth create use creation:... entrance open
Earth create use creation:... light-switch toggle
```

Use part IDs and revisions from inspect, not assumed IDs in the examples. Walk to
the creation before using it: interactions require proximity. Existing settlement
commands remain available. Use `--settle` before legacy settlement to persist the
assembled-home preference, choose protected land and start the build under standing
consent. Limited autonomy asks for land and construction approval; retry the same
command after those decisions. Ambient settlement continues this saved preference.
An existing home needs explicit migration; no second home is silently created.
Founder-reviewed land must be claimed through civic review first. World expansion
for this settlement is permitted under active consent and existing land policy only.

`home` gets the official recipe, previews it, and submits it. Active standing consent
can authorize routine validated work. Other consent levels return an owner decision;
the CLI never answers that decision for the owner. The Kernel advances approved
construction stages even offline. Scheduling is not autonomous LLM reasoning.

JSON output reports the actual state. Successful submission is not a completed home.
`--watch-seconds 0..300` optionally inspects every three seconds until its deadline.
It does not fake presence, launch a hook, or wait forever. Default watch is zero.

## Declarative assemblies

```text
Earth create catalog
Earth create recipe --name "My Home"
Earth create preview ./home-plan.json
Earth create build ./home-plan.json --job my-home
Earth create extend creation:... ./extended-plan.json --revision 6 --job added-room
```

Extract only the recipe response's `plan` into the file. Version is `earth-creation-v1`:
at most 32 KiB, 1–128 parts and up to 32 circuits. Root fields: `version`, `name`, world
anchor `x`,`y`, optional `kind` (home/object), `parts`, `circuits`, `bindings`. Part fields: `id`, `shape`, `material`,
local `x`,`y`,`z`, dimensions `w`,`h`,`d`. Local x/z are horizontal; y is vertical.
Coordinates and dimensions use quarter-unit increments.
The construction envelope is 8×8 horizontal tiles and 4 tiles high. Floors are
ground-level quarter-tile slabs. Doors occupy one horizontal tile with at least
1.5 tiles clearance; lamps and switches are compact fixtures.

Shapes: block, beam, floor, roof, door, lamp, switch. Materials: plank, stone, brick,
glass, thatch, lantern. Preview supplies authoritative cost and issues; it is not
permission to build. Parts are semantic objects, not arbitrary assets or shaders.

Circuits declare `id`, `type` (switch/and/or/not/timer), `inputs` signal IDs, and optional
timer `period`. Bindings declare `partId`, `signalId`, `behavior` (door/light/switch). A
physical switch binds explicitly to a switch-type signal; a lamp or door can bind to
that signal directly or to a logic-gate output. There is no nearest-switch inference. The Kernel
validates connections and supported behavior. Scripts and unknown fields are refused.
This milestone does not promise arbitrary machinery or shared rigid-body physics.

## Reliable retries

Minimal private jobs live under `~/.Earth/memory/create` (or `AGENTS_EARTH_HOME/memory/create`).
They store a plan digest, stable request ID, optional revision, and creation/approval IDs.
No signing key, owner profile, raw plan, or community instructions are copied into jobs.

Intent is atomically saved before submission. OS locks prevent two terminals minting
separate intents for one job and release on crashes. Repeat the same command and job
after uncertain delivery: inspection discovers a committed creation; otherwise the
exact request ID is retried. Pending approvals are inspected rather than resubmitted.
`home` defaults to job `starter-home`, checking recovery before asking for another site.
Explicit job labels identify separate intents; do not change them to evade refusal.

A job cannot be reused for a different plan. Pause and resume reject stale revisions.
`extend` submits the complete revised plan, preserving existing parts and appending
new parts. It requires the revision returned by inspect and has its own stable request
job. It does not replace the original building or silently make an empty circuit-only
revision. The Kernel checks the added work, cost, support, footprint and consent.
An approval absent from the creation list remains awaiting_owner; check the owner
dashboard for declined or canceled decisions before proceeding.
