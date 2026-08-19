# Encounter claim ledger

Use this evidence order:

1. Frozen 4.4.2 client data and official Blizzard patch/hotfix sources.
2. Cutoff-compatible combat logs with exact report, date, size, and difficulty.
3. Pinned addon release/commit and file hash for corroborating timers/spells.
4. Contemporaneous guides/databases, with independent corroboration for
   material quantitative claims.
5. Repository code/DB only as an inventory of current behavior and gaps.

Each material claim needs:

```text
claim_id
mode                         10N | 10H | 25N | 25H | shared
phase
observation_or_value
unit_and_range_semantics
source_id_and_exact_location
authority_rank
status                       resolved | conflict | unresolved
repository_observation
implementation_consequence
acceptance_observation
```

Required mechanic coverage:

- legitimate engage, prerequisite, reset, wipe, death, credit, save/load;
- ordered phase transitions and native timers;
- health/damage/count/radius/duration/speed/target-selection values per mode;
- adds, hazards, vehicles, interactions, platforms, doors, and transports;
- tank, healer, DPS, movement, utility, and recovery obligations;
- observable success/failure event for every obligation.

Never interpolate normal-to-heroic or 10-to-25 scaling. Never convert a guide's
rough tactic into an exact server constant.
