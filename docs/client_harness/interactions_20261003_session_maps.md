# Session persistence and stock maps

UI34 uses one shared native worldserver and the C++ protocol bridge. Their
lifetimes stay unchanged. Both owned clients keep private input displays and
HDMI-1 windows. These are code-controlled ordinary-input tests under the current
AGENTS.md; they do not run a decision model.

The primary actor starts with three legitimately completed Draenei projects,
13 fragments and four Draenei Tomes. `session_logout_01` binds its native baseline
to the successful UI33 earned-state receipt. Stock archaeology history and the
active quest log match before logout. Normal menu logout starts the native
countdown; Escape cancels it with a native acknowledgement. A second logout
completes and the server enumerates the character.

The immediate selection screenshot precedes asynchronous model loading. A later
owned screenshot shows Harnessone at level 85 with full visible gear. After a
separate visual review, `session_reenter_01` presses Enter. Native login, actor
identity, public gear/money/group/profile/quests and the complete native baseline
match. All three crafted artifacts, project histories, fragment balance and
keystone stack survive. Quest 28825, A Personal Summons, remains visible with its
details, while quest 52 remains rewarded. Both history and quest panels pass
again after login. This tests one actor's normal full-session persistence; server
restart, other quests/races and character creation remain separate requirements.

Run the phases separately so the owned lobby can be inspected before reentry:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_session_persist logout --output <new-logout-directory> --source <closed-earned-keystone-episode.json>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_session_persist reenter --output <new-reentry-directory> --source <closed-logout-episode.json> --reviewed-character-selection
```

The source must be a successful owned episode on the same client/server
lifetimes. The review option records a completed visual inspection; it does not
request permission from the user. The runner submits no gameplay API mutations,
resource grants or model calls.

Map observer v43 adds bounded public `C_Map`, `C_ResearchInfo` and stock-frame
reads. V44 adds the existing minimap button rectangles. Both deployments use
ordinary `/reload` on each client and preserve their public baselines. Public
Interface sources are pinned from the installed 60895 CASC, including the Cata
world map, canvas scroll handler and digsite data provider.

`map_navigation_01` opens Badlands and passes its planar coordinate oracle, then
stops because the compact map hides the Zoom Out button. Native state and the
original digsite display setting remain unchanged. The failure stays in evidence.
`map_navigation_02` passes ordinary right-click navigation to Eastern Kingdoms,
show/hide of all four owned digsite icons and bound close/reopen to Badlands.
`map_navigation_03` also checks all rendered icon names, physically left-clicks
Hammertoe's Digsite to navigate into Badlands, and clicks the minimap zoom buttons
from level zero to one and back to zero. All nine actions pass. Native resources,
projects, completion history and inventory stay unchanged; display settings are
restored.

Public map ID 1418, player world XY and its normalized position agree with the
native Badlands rectangle from `WorldMapArea.dbc`. Public `UnitPosition` reports
Z zero while the native character is at 241.668; the coordinate qualification
covers planar XY and does not establish public height. Other continents, dungeon
floors, quest/taxi overlays, fragment caps and additional navigation variants
remain open. Twenty-three actor/menu/travel observation guards pass; both changed
Lua files pass `luac -p`.

Use a fresh owned output directory after deploying the current observer:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_observer_deploy --output <new-deployment-directory> --version 44
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_map_navigation --output <new-map-directory>
```

The runner requires an outdoor player zone with one owned visible digsite for
the zone-selection fixture. It uses the observed binding and public map/button
coordinates. It preserves original failures, closes panels and restores the
digsite/minimap settings.
