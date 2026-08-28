# Magmaw Canary 95 parasite-kite handoff

## Immutable input

- Runtime commit: `5b67a352ec50112cddf0fe342d4b629253a44f36`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Report SHA-256: `8b64a08ea40adb303a5d8f1c0d90a491a72feb97d41f18e5151cb0e8f0d40a7b`
- Combat analysis SHA-256: `88f3dadd1f08f7968505a31498430bfb810f90f86a7777f1c6e7850c69d864c0`
- Combat log SHA-256: `fbc537d52861e6178cc9b25da680426b00f2293aa3e831aac735afcaf14d7243`

## Route result

Entrance regroup, Chainwielder, and Drudges cleared. Magmaw was reached but
not killed. The completion watchdog closed the run on a semantic progress
plateau after nine deaths. There was no future-encounter contamination and no
forbidden assistance.

## First broken edge

The bait hunter took Pillar of Flame at timestamp `1787940561513`. The fixed
bait mage was contacted and infected by a Lava Parasite at
`1787940572135`, followed by raid-wide Infectious Vomit beginning at
`1787940580139`. The previous parasite escape recomputed a pack-owned anchor as
parasite identities and positions changed, causing reactive movement churn and
re-entry toward the ranged and healer stack.

## Accepted bounded repair

Commit `7a57fa8df2` extracts parasite movement into a focused policy. The fixed
mage and hunter baiters own stable point-path identities for the route scope.
The destination remains outward from the support stack and extends only when
the moving pack makes the old point unsafe. Non-baiters receive only a local
contact escape. Pincer movement retains higher ownership.

Focused replay: `4 passed, 9 deselected`. The main strategy is 873 lines and
the parasite policy is 319 lines.

## One-run verification contract

Build the exact clean repair commit, freshly provision the same 10-player
Magmaw shard, and run one completion-watchdog canary. Verify that
`parasite_contact_evade` is stable and point-owned for the fixed baiters,
non-baiters do not join the kite lane without immediate contact, pincer
receipts still preempt parasite movement, and the route advances without
forbidden assistance. Return the first new trace-backed edge if it does not
clear. Do not tune class damage from this raid run.
