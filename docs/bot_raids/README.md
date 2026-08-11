# Cataclysm raid research index

This tree contains concise human strategy dossiers for the approved Cataclysm raid-progression program. Machine-readable encounter contracts and quantitative ledgers live under `experiments/configs/cata_raid_encounters/`; the shared index is `experiments/configs/cata_raid_strategy_catalog_v1.json`.

## Fidelity state

The target is Cataclysm Classic 4.4.2, Hour of Twilight. Blizzard's official patch notes date the release to 2025-02-18. A public client-build table identifies build 59185 as the live launch build on that date, but this is only a candidate identity: the program has not yet pinned a primary client-data extract and its content hashes or selected an exact Blizzard hotfix cutoff. Accordingly, the shared target remains `research_unresolved`.

No BWD dossier is currently `blizzlike_4_4_2_verified`. Each package records repository facts and current strategy evidence, but conflicting or unsupported values remain `fidelity_blocked` and may not become fixed bot timers, target counts, or implementation constants.

## Blackwing Descent

| Boss | Human dossier | Machine contract | Value/timer ledger | Current state |
|---|---|---|---|---|
| Magmaw | [Strategy](strategies/t11/blackwing_descent/magmaw.md) | `magmaw_v1.json` | `magmaw_ledger_v1.json` | Fidelity blocked |
| Omnotron Defense System | [Strategy](strategies/t11/blackwing_descent/omnotron_defense_system.md) | `omnotron_defense_system_v1.json` | `omnotron_defense_system_ledger_v1.json` | Fidelity blocked |
| Maloriak | [Strategy](strategies/t11/blackwing_descent/maloriak.md) | `maloriak_v1.json` | `maloriak_ledger_v1.json` | Fidelity blocked |
| Atramedes | [Strategy](strategies/t11/blackwing_descent/atramedes.md) | `atramedes_v1.json` | `atramedes_ledger_v1.json` | Fidelity blocked |
| Chimaeron | [Strategy](strategies/t11/blackwing_descent/chimaeron.md) | `chimaeron_v1.json` | `chimaeron_ledger_v1.json` | Fidelity blocked |
| Nefarian | [Strategy](strategies/t11/blackwing_descent/nefarian.md) | `nefarian_v1.json` | `nefarian_ledger_v1.json` | Fidelity blocked |

## Source rules

Quantitative evidence is ranked as: Blizzard notes/hotfixes and pinned client data; known-mode 4.4.2 logs or packet observations; pinned 4.4.2 BigWigs/DBM modules for ordering/timers; Wowhead 4.4.2 spell/NPC data; current reputable strategy guides; and original 4.3.4 sources only after unchanged behavior is established. Static spell values do not establish event schedules, addon timers do not establish damage, and guide prose does not override the server behavior actually present in this repository.

A behavior-changing claim requires two independent current strategy sources or one credible current strategy source plus repository confirmation. Historical guides are conflict/provenance evidence, not automatic 4.4.2 authority. Material uncertainty is always fail-closed.
