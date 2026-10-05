# Local voice self-mute, 2026-10-05

UI84 closes at381/916 reviewed operations. The owned scout's installed `TOGGLE_VOICE_SELF_MUTE` binding works while voice login is offline. This qualifies local self-mute only.

Whole-pass `voice_mute01` starts with both slots unbound and CTRL-SHIFT-F12 unused. Ordinary stock Keybindings search, listener and assignment bind that chord. The reviewed row and tooltip render "Voice Chat: Toggle Mute Self" and CTRL-SHIFT-F12. Ordinary key input changes public `IsMuted` false to true, then back to false. All other voice fields stay unchanged. The stock right-click removes the temporary binding; both slots visibly return to Not Bound and the chord is clear. Original voice and Settings state, plus all10 native checks, restore.

The earlier `voice_bindings01` search is a whole failure. Escape leaves Settings open and cleanup refuses replay. The first source-bound recovery refuses its category click because the code compares64 characters against the observer's60-character caption. The corrected recovery restores12 checks against the saved baseline before the whole trial starts. Future search inspection uses the observed Close button. These failures and recovery alone are excluded from qualification.

Validation retains4 initial negative-test failures caused by a mock lacking the case ID. Correcting that mock gives13 focused passes; the production negative outcomes already reject wrong binding/state. Full1149 tests pass. The native worldserver and both owned game lifetimes remain unchanged on HDMI-1. Memory pressure stays zero with around16GiB available. No additional game client or model service is launched.

Connected voice audio, channel activation, microphone transmission, online services, peer mute/deafen and online microphone indicators remain open. Chat tab/root menus have no Copy entry; player-link menus still need inspection for copying and report cancellation.

Evidence: [UI84 DVC pointer](../../artifacts/client_harness/442_interactions_20261005_84.tar.gz.dvc), archive490080576 bytes, SHA-256 `8a9ac9abed68619c6232b26d5d6e52a3f9e988d75d23d6f16e03a8af300f10fe`. Remote review verifies19 JSON receipts and287 attributed images. Key members under `evidence/client_interactions_20261005_ui84/` are `voice_mute01/episode.json`, `voice_whole_review.json`, `voice_search_failure_review.json` and `voice_search_recovery02/episode.json`.
