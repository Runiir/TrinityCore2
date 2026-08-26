# Magmaw Canary39 dynamic Drudge-spacing handoff

Canary39 ran exact clean source `40681de58fe8f2eedc3e05aa87eeddc8953402a7` under the uncapped completion watchdog. It cleared the entrance regroup and Chainwielder, then failed closed at the Drudge pair after 399.017 seconds on `death_loop_watchdog` at `3/3`. Magmaw was not reached. The worldserver exited normally, final forced diagnosis and trace passed, telemetry identity remained clean, forbidden assistance was absent, and cleanup removed every bot and lease.

## What Canary39 proved

The Canary38 escape repair worked. Holy Paladin `30004` completed the bounded native progressive escape, arrived at its selected endpoint, and later closed the reseparation observation. Both Drudges remained tank-owned and took sustained native damage. In the last complete sample before the first death, their health fractions were `0.734627` and `0.741980`. This result closes the prior `unsafe_drudge_member_escape_exhausts_native_candidates` edge.

## First actionable runtime edge

`unsafe_drudge_member_support_starves_dynamic_reposition`

The first death was Restoration Druid `30003` at timestamp `1787731062804`. At recovery tick `1787731059940`, while alive, the Druid was at `(-295.747, -66.948)` and only `14.8981` yards from a live Drudge. The encounter contract requires non-tanks to remain outside both 15-yard Thunderclap circles. The trace therefore correctly reported `group_position_safe=false` even though the prior movement endpoint had arrived and the cached anchor/path remained valid.

The Druid was not the active Rush target, held no hostile threat, and did not target either Drudge. Rush sequence 7 at `1787731056284` targeted Holy Paladin `30004`. Both Drudges remained owned by the tanks. This rules out a role-policy or threat-selection repair for the first edge.

At the unsafe tick, `FormationRequiredMutable=true`, `NativeChargePending=false`, and friendly support was available. `SelectMemberRecoveryAction` chose `PreferFriendlySupport`; the action code called `TryGroupHeal` and returned before the later formation-recovery branch could submit a new movement correction. The Druid then cast native Rejuvenation at `1787731060856` and died at `1787731062804`. Its corpse was sampled at `(-296.017, -66.3945)`, `7.72386` yards from the nearest Drudge. Earlier unsafe samples showed the same delayed correction pattern, including `11.0077` yards at `1787731039529`, with safety restored only at `1787731047669` at `16.1523` yards.

The failure is dynamic geometry. A previously reached endpoint can become unsafe as a live Drudge moves. Friendly support must not starve the independent set-and-forget movement submission needed to restore the 15-yard union-safe position.

## Bounded repair contract

- For an unsafe non-tank, attempt the existing formation-recovery movement submission before the friendly-support early return.
- Keep instant friendly support available in the same tick. Movement submission must not suppress healing and healing must not wait for arrival.
- Reuse the existing live-plus-native-home source union, deterministic candidate selection, strict complete native-path admission, endpoint safety, lane spacing, peer spacing, arrival, and movement-arbiter contracts.
- Preserve independent movement and action ownership. Encounter policy may request movement, but it must not call `MotionMaster` or block the ordinary class action queue.
- Preserve native Rush, tank ownership, health-sync, kill-sync, full-wipe-only recovery, and the verified progressive escape behavior.

Do not reduce the 15-yard safety distance, alter enemy damage or health, force threat or victims, grant pathing or line of sight, teleport, force resurrection, suppress healing until arrival, alter the Restoration Druid rotation, or manufacture a clear.

## Required implementation evidence

Add focused deterministic coverage proving that an unsafe support-capable member submits formation recovery before the support branch and can still perform instant support in the same tick. Retain the existing tests for safe members, pending Rushes, landed observations, strict movement admission, role actions, and full-wipe-only recovery. Every touched C or C++ source/header must remain below 1,000 lines.

After root review and focused tests, commit the bounded repair, build that exact commit only through the coordinator, verify the frozen 10N roster and runtime identity, then run Canary40 under the completion watchdog. There is no fixed raid success timer. If Canary40 clears the full route, run a fresh Canary41 for the required second consecutive clear before promotion.

## Immutable Canary39 evidence

- Source commit: `40681de58fe8f2eedc3e05aa87eeddc8953402a7`
- Source tree: `27a324ddb545a9dce54faf7643ffc45c7a8f138b`
- Binary SHA-256: `a2cbc6caa40a33a8654c2508e6d2959405d526a2047c06ad9d61ff067dd2cf26`
- Build receipt: `/tmp/trinity-magmaw-40681de58f-canary39-build.Athwjd/worldserver-build-receipt.json`
- Build receipt file SHA-256: `7723bb508e8309e2faeba480a98df1337a85f7ab83fd3e8ed5957f41b6fa8e1d`
- Build receipt canonical SHA-256: `3a002d318184e8ca23e141a2a836a34ab9cd96696f5a2c80fc0ea4d2d00fe8f5`
- Report: `/tmp/trinity-magmaw-40681de58f-canary39.DU6qS0/canary39-run/capture/report.json`
- Report canonical SHA-256: `b467a33d1c32ea76c23128e682d337e4061a811fc2236bcc7ab13345c697ab31`
- Report file SHA-256: `676f286e46377b0bab3798289ab84287865c6d6d29efb6ffffa91983978a817d`
- Raw trace SHA-256: `a5bc47977960eb63d872d73b89b9ae92bc17b03bd7a232edbd94c99b41cd11ad`
- Server log SHA-256: `850f30ef676b5e6cbb1e7887732fb6ade64fd7141288cc3d211aaa716266ea88`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`, difficulty `10N`, attempt `2`, route generation `3`
- Terminal result: `gameplay_failure`, `death_loop_watchdog` at `3/3`
- Route result: entrance clear, Chainwielder clear, Drudges incomplete, Magmaw not reached
- Death order: Restoration Druid `30003`, Protection Paladin `30001`, Fire Mage `30006`
- Final alive roster: `7/10`
- First live unsafe distance: `14.8981` yards before the first death
- First-death timestamp: `1787731062804`
- Evidence demultiplexing: `142/142` retained rows bound, zero rejected or unchecked
- Final forced diagnosis and trace: passed
- Forbidden-assistance gate: passed
- Cleanup: passed, worldserver exit code `0`, zero bots and leases

This failed canary is diagnostic evidence only. Do not promote it as an accepted clear.
