# Owned pet targeting and health validation

Two scoped operations now pass on the retained level-1 Warlock: exact-name targeting of its owned Imp and reading its health while selected. Coverage moves from 424 to 426 of 916 operations, with 490 open. The pet tab, power, commands, combat and other class or level variants remain open.

One ordinary `/targetexact Volrot` selects native GUID `0xf14001a000000005`. The modern request and public target identify `Pet-0-1-0-0-416-0000000005`; the native request and player target field refer to the same owned Imp, entry416 and pet number1. Reviewed scenes show its purple selection circle and the stock target frame. Public and native health both read 254/254, and the visible health bar is full. Normal `/cleartarget` restores the empty selection and removes the target frame.

All nine trial restoration checks pass, preserving inventory, money, saved rows, observed position, closed panels and Harnesstwo's original full row and saved state. Normal class logout and reviewed original selection pass all five closing checks. Harnesslock and its native pet remain retained offline. Closing scenes show Harnesstwo selected and the primary seated with panels closed. Native worldserver, bridge and both existing client lifetimes remain unchanged on HDMI-1; no build, restart or additional client is needed.

The unchanged-runtime fixture guard checks the closed preparation, park and original-finish chain, exact current retained rows and original registration before resuming Harnesslock. All 66 focused tests pass. One initial assertion expects 140 from the pet creation, while the retained trace later updates health to 254; that failure is preserved and the expected latest value is corrected. All nine gameplay episodes close successfully. After archive review, all three qualification-metadata checks pass. The [native pet repair report](interactions_20261006_pet_repair.md) retains the earlier build, regression and fixture failures.

Installed trainer 154 teaches 80388 at level 10, and spell_learn_spell links it to Control Demon 93375. The current level-1 fixture lacks that control spell and has no pet tab. This read-only prerequisite result supplies the next normal training path; no spell, aura or level is granted.

Custom scripts remain blocked. The original `softTargetInteract=0` remains recorded as unrestored at stock-disabled `1`, following the user's instruction.

[DVC archive](../../artifacts/client_harness/442_interactions_20261006_112.tar.gz.dvc) contains 93,030,599 bytes, SHA-256 `9446a05694390a0b19ad5cb0042c26bbaf60299c24c1367b054efa51a5b3322d`, MD5 `c0491303bc272da9128375175bc28bf2`. Remote and archive review verify all 19 JSON receipts and 32 attributed images before local pruning.
