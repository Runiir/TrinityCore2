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

Start with the emitted ledger's compact resume view:

```bash
pixi run python -m tools.raid_program.encounter_research_view <ledger-path>
```

Choose the next unresolved claim, then use `--key <claim-key>` for its values
and sources. Read the relevant dossier/contract sections, native functions and
DB rows. On the first audit, inventory the full boss/instance implementation
and read `experiments/configs/cata_raid_acceptance_policy_v1.json`. On a resume,
check source revisions before reusing retained observations. Do not reread all
evidence or rebuild a reference already bound to unchanged inputs.

Browse every referenced online page that supports a changed claim. Preserve
URL, title, publisher/author when available, publication/update date, retrieval
date, exact mode, and the bounded claim it supports. Do not cite a search result
or another dossier as the source.

For suspected timer, damage or phase bugs, follow
[the reproducible boss research procedure](references/reproduce-boss-research.md).
It covers longer WCL kill selection, browser extraction, addon event anchors,
client/native spell chains and the bounded implementation handoff.

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

Maintain `research_completion` in the existing ledger: one row per mechanic or
lifecycle obligation, with `key`, mode scope, status, known evidence, source
references and the exact next question. Full research is complete only when
the required coverage has supported values, a native comparison and acceptance
observations for the requested modes. A bounded repair can be ready earlier;
name its scope. Neither a populated packet nor a clear proves full fidelity.

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
