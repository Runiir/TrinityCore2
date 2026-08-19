---
name: raid-encounter-research
description: Research and review one Cataclysm raid encounter against online sources, pinned client/addon/log evidence, database state, and the repository's current scripts, then update its human dossier, mechanic contract, and quantitative ledger. Use for boss strategy, tactics, phase graphs, timers, spell IDs, difficulty/raid-size deltas, assignments, source conflicts, script-readiness review, or unresolved encounter values. Do not implement C++/SQL gameplay changes or run live shards.
---

# Raid Encounter Research

Own one boss research packet. Do not own its implementation.

## Bind the boss packet

Run:

```bash
pixi run python -m tools.raid_program.raid_workloop boss <raid> <boss> --mode <mode>
```

Read the emitted dossier, mechanic contract, value ledger, current native boss
source, instance source, relevant DB rows, and
`experiments/configs/cata_raid_acceptance_policy_v1.json`.

Browse every referenced online page that supports a changed claim. Preserve
URL, title, publisher/author when available, publication/update date, retrieval
date, exact mode, and the bounded claim it supports. Do not cite a search result
or another dossier as the source.

## Build the claim ledger

Follow [references/claim-ledger.md](references/claim-ledger.md). Research both:

- encounter truth: phases, native start/reset/credit, spells, timers, health,
  damage, counts, target selection, difficulty and raid-size deltas;
- executable strategy: tank/healer/DPS assignments, positioning, target
  priority, swaps, interrupts, dispels, cooldowns, vehicles/interactions,
  recovery, and legitimate completion.

Keep source truth, current repository behavior, and proposed bot tactic as
three separate fields. Record conflicts instead of choosing a convenient value.
If no authoritative input resolves a material value, leave it `unresolved` and
keep qualification `fidelity_blocked`.

## Review the current script shape

Confirm source/loader/instance/DB registration, actor spawn or summon authority,
doors/transports, prerequisites, save/load, reset, death/credit, and all four
mode branches. Source presence is not runtime readiness.

Classify the implementation handoff:

- `missing_dedicated_implementation`;
- `instance_foundation_incomplete`;
- `source_present_static_gaps`;
- `source_present_ready_for_diagnostic_shard`;
- `fidelity_blocked` even if engineering may continue.

Do not invent code, SQL, coordinates, timers, or scaling during this pass.

## Deliver a bounded packet

Update only the boss dossier, contract, ledger, catalog/readiness rows that
derive from them, and focused tests. Run:

```bash
pixi run pytest -q tests/test_cata_raid_research_contracts.py
```

Hand `raid-encounter-implementation` a phase graph, mode matrix, exact resolved
claims with sources, unresolved blockers, current-script gaps, and acceptance
observations. The implementer must not need to repeat broad web research.
