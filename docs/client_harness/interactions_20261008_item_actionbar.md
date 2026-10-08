# Ordinary Hearthstone actionbar drag, UI171

UI171 qualifies only `actionbars.drag_item` for the original level 1 Warrior Harnesstwo (GUID 2), existing Hearthstone 6948/SQL GUID 41 and an empty cell on effective actionbar page 7. Coverage is now 453 of 916 operation contracts. The occupied-slot bag swap is the next open unit.

The scout runs alone on verified HDMI-1 with private display `:2`. The primary remains stopped. One normal login and one normal logout complete the roundtrip. All six actors finish offline with the original saved state, inventory, resources, pose, target and layout preserved. The two retained Hunter pets, 4 and 16, belong to the protected actor. No item use or cast occurs.

| Witness | Observed value |
| --- | --- |
| Source item | Backpack 0, slot 1; item 6948, SQL GUID 41, count 1 |
| Destination | Main-bar button 3, public slot 75/native slot 74; effective page 7, active spec 0 |
| Sole assignment | Modern `241b00804a`; native `4a241b0080` |
| Added saved action | `[0,74,6948,128]` |
| Sole clear | Modern `000000004a`; native `4a00000000` |
| Cursor cleanup | One stock Shift pickup, then one reviewed cancellation at an empty world point |
| Final restoration | Original action rows and complete inventory, HP/power/XP, pose, target and layout |
| Exact native rest | Float32 `3ff2c641` before login; `b2e45242` after, 52.72333526611328 |
| Resource shutdown | All eight checks pass; original game PID 3534954 and its launcher are absent |

The drag's reviewed destination starts empty and becomes a rendered Hearthstone icon. The complete journals contain exactly one assignment and one clear in their bound ordinary input windows. Native inventory GUIDs and saved item rows stay unchanged throughout. The logout request is modern body `00`, translated to the empty native request; the native completion and delivered modern completion agree.

The initial `item_recon01` cannot observe the actionbar while the backpack is open. Later passive-observer scheduling fixes that visibility. Two unattributed stand/AFK changes require separately recorded, excluded restorations. The first observer reload attempt fails before input; a source-bound renewal restores the original pose and AFK state, then one ordinary `/reload` loads the corrected passive observer. These predecessors remain immutable.

The first clear attempt fails before input because the reviewed world pixels changed. A fresh reviewed point permits the sole actual clear. The first close attempt fails before stopping the client because the reader rejects the real empty-cursor shape `{}`. It remains a failed receipt. No successful gameplay input is replayed.

Completed gameplay is committed at C `235c10e2f5ca299452f44d11552fae2017cb8791`. The subsequent six-file repair at D `a60300d44460debad572c04b13722f917ebac276` handles exact JSON empty cursor shapes, complete ordered journal budgets and the source-backed logout body. Its fresh parked-selection capture is read-only. The original C park, fresh D capture and immediate closing PNG each bind their actual source directory and bytes. Capture and stop require the original game PID, private display and window. The saved transition carries the exact C/D source bytes and proves the other runtime sources unchanged.

The final D capture and `item_close_pause02` succeed, with no gameplay input or saved-state mutation. All eight shutdown checks pass. An ignored `Input.__del__` Xlib connection-closed warning occurs after SIGTERM and the successful result, when the owned private display has already closed. The recorded closure itself has no failure, and the command exits 0.

Validation passes 240 focused tests, with independent portable and runtime reviews passing 123 and 117 respectively. The codec-enabled world/auth suite passes 6,556 tests. Its one environment-specific DVCLive archive test passes separately in the root Pixi environment. Earlier diagnostic ordering, logout-body, fixture-call and CLI import failures remain retained with the corrected results.

The [DVC pointer](../../artifacts/client_harness/442_interactions_20261008_171.tar.gz.dvc) identifies 236,655,195 compressed bytes, SHA256 `a73daaafc3524eb99361889ee1af6163c22920ab65ffe720699fd37267b20501`. An actual remote stream verifies the compressed identity, all 126 JSON and 123 PNG members, and both complete journals. Semantic replay consumes 23,932 selected packet rows and 117,765 event rows in original order. The external remote review SHA256 is `ddee63708620a0877b08790e19d23ead0bff74f052573c829598a6b2cd7c2f60`. It creates no local archive download.

After that verification, all 123 local PNGs (194,851,764 bytes), the exact workspace archive and its exact DVC cache object are removed. JSON receipts and external proofs remain local. Scoped DVC status reports the expected absent local archive/cache; push reports up to date. No global cache collection occurs.

Scripts remain blocked. The original `softTargetInteract=0` stays explicitly unrestored at stock `1`. New trials use a code controller with model/revision null. Other items, pages, occupied action cells, casts and the rest of the interaction family remain open.
