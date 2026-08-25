# Magmaw Canary29 safe-member offense handoff

Canary29 ran the exact clean `c7c6bb9f7f0c51265f1ae20ab96ef01a59af467a` tree with the coordinator-built binary. It cleared the entrance regroup and Chainwielder, then failed closed on the Drudge node after 439.833 seconds with three healer deaths. The worldserver shut down cleanly with zero bots and leases. No teleport, forced threat, forced resurrection, native encounter mutation, or other forbidden assistance was observed.

## What the prior repair proved

The displaced-origin recovery repair worked. Native Rush observations 1 through 14 recorded exact-roster reseparation. The full ten-player roster survived at least eleven landed Rushes. No `no_candidate_committed` result occurred before the first death. Do not reopen the displaced-origin hypothesis.

## First broken edge

`landed_drudge_recovery_keeps_safe_members_in_route_handled_offense_hold_until_the_next_20s_rush_reopens_the_queue_so_no_trained_single_target_action_executes_and_healers_attrition_die`

The two Drudges remained near full health throughout the recovered Rush sequence. Their health moved only from 96.4997/97.7267 percent at observation 1 to 89.0004/94.0211 percent at observation 14. Direct trace reconstruction found 4,890 Drudge-route entries and zero `drudge_lane_single_target_action` or `drudge_lane_single_target_hold` decisions for every roster member. `drudge_native_charge_lane_reseparate` repeated 1,323 times for GUID 30008 and 127 to 139 times for most surviving peers.

The route closed early observations in roughly 12 to 18 seconds. By observation 11, closure took about 38.5 seconds and bulk-closed observations 11 through 14 after additional native Rushes had already landed. Observations 15 and 16 landed about 1.5 seconds after that closure, leaving no useful offense window. Healers 30003, 30004, and 30005 then died about one native 20-second Rush cycle apart.

## Source diagnosis

`DrudgeLaneContext::RunFormationActions()` treats every landed native Rush as `recoveryNeeded`, calls `HoldOffense()`, and returns `PhaseResult::Handled` even for a member that is already safe. That prevents `RunThreatAndEvidenceActions()` from reaching the existing guarded `drudge_lane_single_target_action` path. The movement arbiter already permits movement and combat resources concurrently, so the defect is the route decision consuming the combat opportunity, not movement execution itself.

`ProfileActionAccepted` is an evidence receipt. It must not be a circular prerequisite that prevents the first guarded profile action from running.

## Bounded repair contract

Implement one trace-backed runtime hypothesis:

- Unsafe members must continue mechanic recovery and offense hold.
- A member that is already safe for its assigned lane, source union, spacing, and tank constraints must allow the existing guarded threat/evidence phase to evaluate a normal trained single-target action while the set-and-forget movement path remains active.
- Preserve lane ownership, exact roster, native Rush readiness, tank-anchor, kill-sync, and prospective seed-distance safety gates.
- Add focused deterministic policy coverage for safe and unsafe members, pair-too-close state, tank constraints, and active recovery scope.
- Keep every C and C++ source/header below 1,000 lines. Split by concern if the repair cannot fit without crossing the limit.

Do not reduce separation or timing thresholds, force threat or taunts, alter Drudge AI, teleport, resurrect, manufacture outcomes, or grant a broad generic-combat bypass.

## Immutable Canary29 evidence

- Source commit: `c7c6bb9f7f0c51265f1ae20ab96ef01a59af467a`
- Source tree: `5e716728bd2abb1e8133ce3176a1eea97ff24d1b`
- Binary SHA-256: `5208fd31a5179bec965f3ff64393bb17beade82cd0dc50b6a99ca7904475f990`
- Build receipt: `/tmp/trinity-magmaw-c7c6bb9f7f.1PPPpS/worldserver-build-receipt.json`
- Build receipt canonical SHA-256: `1eda164bf53c01b9da3678c3d92ba60fa792a68cd8a7bb17c9a7ea070a50dbaa`
- Config SHA-256: `9dcfda57f27d94729a661e17d5618cd1bc5d8a538c5a6318a1bffb11111f5f83`
- Report: `/tmp/trinity-magmaw-c7c6bb9f7f-canary29.xecJ8Q/canary29-run/capture/report.json`
- Report canonical SHA-256: `180d60ed29a7cd87a7e199aafd0b9d45fbf45e4c667d8a790ecd0f19e2648a7c`
- Report file SHA-256: `90a5837ba49be4f6a9032ac48acdc7d8772c93ab231320102653fb9d35f16b41`
- Raw trace SHA-256: `bfa91214f9dd171adfe1fbfed2abe9436cc3c1506a1b9bde302bf1b9f7384f93`
- Server log SHA-256: `6d3cbf35f09a57bfae3b82f1fdd73b835c21b043162984536f420fbc60495fb6`
- Server epoch: `5289128477902581`
- Attempt: `2`
- Route scope: generation `3`, node `bwd.magmaw.drudges`
- Terminal: `gameplay_failure`, `death_loop_watchdog`, three deaths, seven alive
- Evidence demultiplexing: passed, 158 retained and bound rows, zero rejected rows
- Cleanup: passed, worldserver exit code 0

The next owner is `raid-bot-runtime-implementation`. It may implement and run focused tests only. A separate coordinator must review the patch, obtain an exact queued build receipt, provision a fresh roster, and run Canary30 under the completion watchdog.
