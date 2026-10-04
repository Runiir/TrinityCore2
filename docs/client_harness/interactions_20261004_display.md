# Stock display controls

Observer64 reads the installed FPS, screenshot and UI visibility bindings,
FramerateText and public FPS value. The display trial sends each normal binding
once and waits for the requested state without replaying input. UI hiding is
checked through the missing observation strip plus visual review of the world
and stock UI Hidden message. One inverse binding restores the HUD. The screenshot
trial retains the exact game-generated JPEG and removes its private duplicate.

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_display_controls --actor primary --output <new-owned-evidence-directory>
```

The primary and scout UI46 display01 trials both pass completely. FPS toggles on
and back to its original state, both generated screenshots are valid1280x720
JPEGs, and both HUDs hide and restore. Inventory, money and saved spells remain
unchanged. Each owned presenter is verified on HDMI-1. The low background FPS
is recorded; these trials qualify display behavior, not game performance.

The scout observer64 reload's28-second state wait fails and remains failed.
A separate60-second read-only verification succeeds with observer64, the same
session and unchanged money, equipment, group and raid profile. The reload input
is not repeated. No server restart or protocol change was needed.

DVC46 is synchronized. Review verifies7 selected receipts and38 attributed
images, including both game-generated JPEGs. Eight exact images are visually
reviewed. JPEG attribution/digest tests pass3/3. Three scoped operations are
added to the ledger; the checklist is281/916. Other display settings, latency,
camera, cinematics and movie dialogs remain open.
