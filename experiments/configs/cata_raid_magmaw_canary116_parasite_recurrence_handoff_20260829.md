# Magmaw Canary116 parasite recurrence handoff

## Identity

- Source commit: `ae9761adb32a04dc3563dd05b1372a5c9aa33cb5`
- Run: `trinity-magmaw-ae9761adb3-canary116.n0L5tX`
- Classification: `gameplay_failure`
- Terminal gate: `death_loop_watchdog` after 511.374 seconds
- Report SHA-256: `9c76a6a0af6a6e9069baf868a34b249b1e897ebd7aa326f546984751cbd08521`
- Raw JSONL SHA-256: `1991c42652ef53a5c60dd2db86d4e8eb87547cfcadfeed2db508f239f9713dc9`
- Worldserver log SHA-256: `deb32f06ebf9311591b6092cc5bcfbaf7d57d835d50f075e4e0c3130dcdf34d8`

## What held

The entrance, Chainwielder, and both Drudges cleared. Magmaw formation no
longer stalled on the Canary115 endpoint-Z mismatch: the roster staged,
pulled, and accumulated 194 active combat seconds on Magmaw. The previous
formation, current-route authority, and future-pack contamination signatures
are absent in this run. This run does not invalidate those repairs.

## First causal failure

Parasite control recurred during Magmaw. Seven of ten players took Infectious
Vomit. The controller ended the run on its third death-loop transition with
complete forced terminal evidence and clean shutdown. This is a new occurrence
of `magmaw_parasite_control_allows_player_infection`, not a continuation of the
closed prepull-formation failure.

Magmaw active-combat throughput was 74,996.907 party DPS and 18,012.046 party
HPS. Individual damage uptime collapsed for the Elemental shaman (0.124),
Unholy death knight (0.186), and several support actors after infection and
deaths. The run therefore cannot qualify class throughput independently of the
encounter failure.

## Workflow consequence

Canary116 is diagnostic evidence only. Independent review found that the new
hidden-candidate watchdog can reuse a diagnosis sampled up to 30 seconds ago
on later status polls, and the deterministic formation fixture stops before
native admission and pre-pot readiness. Fix diagnosis freshness and extend the
compiled replay across route destination, strict native admission, formation,
and pre-pot readiness before admitting another live canary.
