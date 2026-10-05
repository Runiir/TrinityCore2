# Pending display selections and stock discard

The owned primary passes one pending selection each for Resolution, Display Mode and Monitor. Resolution changes from 1280×720 to 1152×720, Display Mode from Windowed to Windowed (Fullscreen), and the private nested Monitor selector from Primary to Generic Non-PnP Monitor. Every selection remains pending until the stock Close and Exit choices discard it. No Apply action is submitted.

All observed active CVars remain byte-identical. The public `C_VideoOptions.GetCurrentGameWindowSize` getter uses the actual `gxMonitor=0` and `gxMaximize=0`, and keeps reporting 1280×720. Logical screen dimensions remain unchanged at about 1365.33×768; UI scaling makes these different from the pixel window size. All other observed proxies preserve the baseline. Each selection passes seven checks and each reopened discard restoration passes six. Final display, settings-layout and native restoration pass four, five and ten checks respectively.

Six reviewed images show the three pending selectors, the exact exit confirmation, the reopened Controls category and the final seated primary with Settings closed. The reopened category does not visibly show display selectors; its encoded public probe proves their original values. The private selector's Primary label refers to the nested display. Independently verified owned physical window geometry stays on HDMI-1 throughout.

This qualifies `settings.resolution`, `settings.window_mode` and `settings.monitor_selection` for these pending selections and stock discard only. Applying changes, other options, physical monitor switching, allocation/performance and persistence remain open. Read-only observer 119 adds actual-window getters without invoking or wrapping setters. Installed build 60895 CASC source pins define the pending proxies and stock Exit behavior. All 174 focused and 1,484 full protocol checks pass. Observer deployment preserves the native session, pose and AFK state; the scout stays at character selection.

Coverage is 403 of 916 scoped operations, with 513 open. No extra client, server, model job or native build starts in this batch. Scripts stay blocked. Historical original `softTargetInteract=0` remains unrestored at stock-disabled `1`, as accepted by the user.

The [UI96 DVC pointer](../../artifacts/client_harness/442_interactions_20261005_96.tar.gz.dvc) identifies the remotely verified 258,959,771-byte archive, SHA-256 `1aeb77c2f231267126a2a48dacac46a2bc10abc60224ad3488f3730e30d866b0`. Archive review verifies 13 JSON receipts and 161 attributed image hashes.
