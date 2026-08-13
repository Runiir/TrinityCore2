# Blackwing Descent diagnostic node architecture

The validation scenario generator keeps one canonical BWD 10N parent route and
six explicitly named diagnostic routes. The parent scenario is
`blackwing_descent_10n`; its generated route remains the native ordered
eleven-node route used by a full-instance qualification run. The diagnostic
scenario IDs are:

- `blackwing_descent_10n_magmaw_diagnostic`
- `blackwing_descent_10n_omnotron_diagnostic`
- `blackwing_descent_10n_maloriak_diagnostic`
- `blackwing_descent_10n_atramedes_diagnostic`
- `blackwing_descent_10n_chimaeron_diagnostic`
- `blackwing_descent_10n_nefarian_diagnostic`

All seven BWD scenarios are emitted into the same
`dataset/validation_scenarios/validation_routes.jsonl` aggregate. Runtime
profiles select one `scenario_id`, so a diagnostic cohort cannot consume the
parent's later nodes or another boss shard's nodes. Each diagnostic profile
also has its own pool tag; the eventual fixture must provide disjoint account,
character, group, instance/save, attempt, and evidence identities for those
tags.

The Magmaw shard is deliberately only entrance regroup, Chainwielder trash,
the two-Drudge lane, and Magmaw. Omnotron, Maloriak, Atramedes and Chimaeron
start at their native local approach and include only their corresponding
regroup/trash/boss nodes. The Nefarian shard records all five predecessor boss
entries as a pre-seeded diagnostic prerequisite, but starts on the upper ledge,
requires preparation there, and includes a native descent node before the
Nefarian encounter node.

`diagnostic_only` and `prerequisite_contract.certifies_predecessors=false` are
preserved in the scenario and route rows. A pre-completed predecessor enables
isolated script/strategy diagnosis; it never supplies a predecessor kill,
unlock, boss, or full-clear acceptance fact. Only the canonical parent route
and later sequential full-instance runs can feed authoritative progression
gates.
