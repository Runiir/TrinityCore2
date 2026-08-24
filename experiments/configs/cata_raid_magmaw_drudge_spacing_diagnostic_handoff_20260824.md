# Magmaw Drudge spacing diagnostic handoff

The exact `ff5af70c7c56a0cb5ff4cdc3a20fadaa5b469d3d` canary failed closed under the completion watchdog after 285.589 seconds. It cleared the entrance and Chainwielder, reached the Drudge pair, and never reached Magmaw. Cleanup, identity, telemetry demultiplexing, trace continuity, and forbidden-assistance gates passed.

Eight native Rushes landed, four per source, with three valid 20-second intervals per source. No landed observation closed. `reseparated_roster_guids`, `profile_action_roster_guids`, and `health_sync_evaluated_roster_guids` remained empty. Bots 30003, 30004, 30007, and 30008 died.

The first explicit failed edge is bot 30003. The first Rush landed at `1787582535419`; bot 30003 recorded `drudge_anchor_spacing_unsafe` at `1787582537490`, never submitted a native recovery movement, and died at `1787582541627`. Both tanks reached their recovery anchors, but only emitted repeated combat-return submissions. Neither emitted an exact combat-anchor-arrival proof before the first death.

The retained trace cannot identify the rejected candidate or conflicting peer. Commit `d47cb0d209b0b7a87d98307dfa46c90197af32e6` added bounded, scoped diagnostics without changing gameplay selection or any acceptance gate, but its exact native build was rejected because the JSON serializer contained a malformed string literal. Commit `49e8f8bff809e8d685653d127dcaed1d0bf2724e` corrects that compile failure and adds a static regression guard. The next run must use the exact corrected tree and remains diagnostic verification, not a gameplay acceptance claim. It must expose the first failed reseparation predicate and the spacing candidate's member, coordinates, peer, peer-coordinate source, distance, and source/lane/spacing booleans.

Evidence remains local at `/tmp/trinity-magmaw-ff5af70c7c/canary1/capture`. Failed evidence must not be promoted to DVC acceptance data.
