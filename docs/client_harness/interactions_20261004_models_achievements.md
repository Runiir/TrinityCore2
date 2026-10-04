# Stock dressing room and achievement tracking

UI47 qualifies four dressing-room operations on the primary warrior and four
achievement operations on the scout. The checklist is now 289/916 scoped fixture
variants. Both clients remain on HDMI-1, with their original native sessions and
the same worldserver process. No native rebuild or server restart was needed.

The dressing-room trial uses ordinary Ctrl-click on equipped Gurthalak (78478)
and backpack Worn Greatsword (49778). Dedicated read-only observation pages avoid
the normal state page's payload limit. Preview and Reset wait for model geometry
readiness, then visual review verifies the rendered sword. Stock rotation arrows
change and restore facing. Close removes the window. Native equipment, inventory,
money, currencies, archaeology, talents, glyphs and saved spells stay unchanged.
Only primary_dressup_04 qualifies these operations.

The achievement trial selects General (92). Six visible names, point values and
earned flags match the native Achievement DBC and character tables. Selecting
unearned Level 10 (6) exposes Track. Checking and unchecking it changes the public
tracked list, rendered checkbox and Objectives row. The trial collapses selection
before restoring Summary, then closes the panel. Native earned/progress tables,
inventory, money and spells stay unchanged. Only scout_achievements_02 qualifies
these operations. Summary earned-row contents and persistence are outside scope.

Both trials send ordinary inputs once and wait for results. Observer deployments
record baseline/session identity separately from gameplay. A reload can exceed
60 seconds at the observed low background FPS; the read wait is now bounded at
180 seconds. No timeout is treated as successful deployment and reload input is
never repeated merely because observation is late.

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_dressup --output <new-owned-evidence-directory>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_achievements --actor scout --output <new-owned-evidence-directory>
```

The archive preserves every earlier failure:

- Observer65 primary deployment failed while loading. Separate read-only
  verification confirmed the installed version and unchanged session/baseline.
- Dressup01 overflowed the normal observation page. An exact-source cleanup-only
  episode closed the visually reviewed model; observer66 added a dedicated page.
- Dressup02 checked geometry too early and failed. Dressup03 completed machine
  checks, but visual review rejected its blank Reset model. Its qualification
  remains false. Dressup04 requires geometry readiness after Reset and passes
  visual review.
- Scout achievements01 failed to restore hidden selection under Summary.
  Exact-source cleanup restored the layout; achievements02 collapses the selected
  row before returning to Summary.
- A setup test initially failed (1 failed, 15 passed) because its mock did not
  accept the observation timeout argument. Deployment had already begun before
  the change was committed. The archived setup correction identifies those exact
  execution sources; no gameplay qualification comes from that deployment.
  The corrected targeted selection passed 17 tests. The final 180-second reload
  regression selection passes 11 tests.

DVC47 is synchronized. A single archive review verifies 25 selected JSON receipts
and 298 attributed images, including failures and cleanup. Eleven exact successful
frames receive visual review. The earlier rejected frames are retained separately.
After remote and digest verification, raw PNGs and this archive's exact local
cache object can be evicted. Local missing-cache status for previously evicted
archives is expected; cloud status remains the synchronization check.

Other item types, model windows, achievement categories, tooltips, comparison,
criteria progress, notifications and reconnect persistence remain open. These
passes do not claim full feature-family coverage.
