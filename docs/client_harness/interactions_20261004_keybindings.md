# Stock keybindings with native restoration

UI62 qualifies five operations: menu options, menu keybindings, keybindings open, assign key and close. The checklist moves from 332 to 337 of 916 scoped operations.

The owned primary client assigns the unused Ctrl+Shift+F12 chord to the second Toggle Framerate Display slot beside Ctrl+R. Close saves it; the chord survives reload and toggles the visibly rendered FPS counter on and off. Stock removal, Close and reload restore the exact original binding. Original settings category, search, CVars, values and unapplied state match. All ten native/public restoration checks pass, including native position, resources, stats, spells, actions, pose, AFK and group. Eight acceptance frames were visually reviewed.

The first whole run failed only pose restoration: the originally seated player was standing after the interface roundtrip. Its binding and settings checks passed. The exact cause is not established by packet timing. A separate bounded recovery restored the original seated pose and passed ten checks; it qualifies no operation. The fresh full retry includes ordinary sit/stand restoration after reload and passes completely.

DVC62 verifies 18 JSON receipts and 196 attributed images. The archive is 362439588 bytes, SHA256 dc5636a613c6f9a332c0a388800ee4cf39e8398b2d51d430014dbb20c9d83e4d. Two clients remain on HDMI-1; no client, bridge or native worldserver restart or build occurred. The closure resource check recorded about 16.0 GiB available RAM and no recent memory pressure.

This covers the primary idle level85 client, account binding set1 and one harmless unused chord. Conflicts, explicit clear-binding cases, per-character profiles, defaults and combat variants remain open.
