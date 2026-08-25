# Magmaw Canary30 positive self-range handoff

Canary30 ran the exact clean `53c1d427d27a4b58d9f0c0425f9cba210edac71f` tree with the coordinator-built binary. It cleared the entrance regroup and Chainwielder, then failed closed on the Drudge node after 419.796 seconds. The worldserver shut down cleanly with zero bots and leases. No teleport, forced threat, forced resurrection, native encounter mutation, or other forbidden assistance was observed.

## What the prior repair proved

The safe-member offense handoff worked. All seven required offensive roster slots recorded trained single-target actions. The retained trace contains 73 `drudge_lane_single_target_action` entries and 96 typed holds. Native Rush observations 1 through 6 recorded exact ten-player reseparation. Do not reopen the safe-member offense hypothesis.

## First broken edge

`positive_self_target_profile_actions_retain_a_hostile_range_envelope_after_resolution_so_combat_range_reconciliation_moves_a_safe_bot_toward_the_drudge_and_reopens_lane_recovery`

Rush observation 7 targeted holy paladin `30004` and became the first observation without an exact-roster reseparation receipt. At `1787698033296`, the paladin recorded `drudge_group_lane_position_already_safe`. The next profile resolution selected positive self spell `31842` (Divine Favor), retained a hostile maximum range, and repeatedly emitted `profile_combat_range_movement`, `native_self_centered_range`, and `native_self_centered_path_rejected` against Drudge target `59`. This moved or tried to move the healer toward the hostile even though the action target was the healer and the Drudge route owned movement.

The first death was holy paladin `30004` at `1787698079794`. Affliction warlock `30008` died at `1787698135248`, and elemental shaman `30010` died at `1787698140487`. The final forced diagnosis retained seven survivors. The controller stopped the run on its third death-loop observation. The Drudges remained alive, and Magmaw was not reached.

## Source diagnosis

`ResolveProfileCombatAction()` correctly distinguishes a positive self action from a hostile self-centered action while selecting a candidate. That distinction is lost when the selected action is materialized: every self-target action copies `Profile.MaxRange` into `ResolvedCombatAction::MaxRange`. `ExecuteProfileCombatAction()` and the shared `world.profile_combat_range` candidate then infer hostile positioning from `TargetGuid == bot` plus a positive `MaxRange`. This makes a positive self buff such as Divine Favor look like Shadowflame or Holy Wrath.

## Bounded repair contract

Implement one shared runtime hypothesis:

- Preserve a hostile range envelope only for a self-targeted spell that is natively hostile and explicitly configured as a self-centered hostile action.
- A positive self-targeted action must resolve with no hostile positioning envelope, so neither the executor nor `world.profile_combat_range` submits movement toward the hostile for it.
- Preserve the existing movement behavior for real point-blank hostile actions such as Shadowflame and Holy Wrath.
- Add deterministic coverage for one positive self action and one hostile self-centered action, plus a source-level assertion that both execution paths consume the same resolved contract.
- Keep every C and C++ source/header below 1,000 lines. Split by concern if the repair cannot fit without crossing the limit.

Do not special-case Divine Favor or Magmaw, weaken Drudge spacing, disable ordinary player movement, force a cast, teleport, resurrect, manufacture damage, or alter native encounter state.

## Immutable Canary30 evidence

- Source commit: `53c1d427d27a4b58d9f0c0425f9cba210edac71f`
- Source tree: `0b1e4ff2af431c532544f7b8d5a31fa54c5d5eae`
- Binary SHA-256: `0c30957fe8900ef48f45484ffa31a776d8ca80eca5aa03d22e32b6a757e130fc`
- Build receipt: `/tmp/trinity-magmaw-53c1d427d2.C3oUL2/worldserver-build-receipt-v2.json`
- Build receipt canonical SHA-256: `52550cc6c9b9b1a1cde9a7c4ebb0ff29f75e39b412e307bbb919d4d07fc55a3e`
- Build receipt file SHA-256: `0d6f0962cae8cd0025dcd47b00033fabbdb6517f47cfe3f918678ac8dc2298bc`
- Config SHA-256: `19b4a6493f9145b5381bb8f5fc8535e60ce5cbbee1652a86267522fb59771e3d`
- Report: `/tmp/trinity-magmaw-53c1d427d2-canary30.jOcmLS/canary30-run/capture/report.json`
- Report canonical SHA-256: `7b5c72d6a178955e7e5f0cf38aa15303f43ca63d40e7dd5dd0bfb589656268a3`
- Report file SHA-256: `283ed6a9d609cbe4cd7d692589620abac26d313363b1ed2a7988f9d9830d009f`
- Raw trace SHA-256: `5b17b301c9e1bef7e9225deaf133a0b16c66c584e55bdb45a31f8ed85c8255fb`
- Server log SHA-256: `1328f7213326bc95df69e733b142acdf6f903685bb293d15104839f4337b782b`
- Server epoch: `5482958734247152`
- Attempt: `2`
- Route scope: generation `3`, node `bwd.magmaw.drudges`
- Terminal: `gameplay_failure`, `death_loop_watchdog`, three deaths, seven survivors
- Evidence demultiplexing: passed, 150 retained and bound rows, zero rejected rows
- Cleanup: passed, worldserver exit code 0

The next owner is `raid-bot-runtime-implementation`. It may implement this one resolved-action range edge and run focused tests only. A separate coordinator must review the patch, obtain an exact queued build receipt, provision a fresh roster, and run Canary31 under the completion watchdog.
