# Stock equipment and glyph tooltips

UI35 uses isolated ordinary pointer inputs on the HDMI-1 client windows. Both
clients share the same native worldserver and C++ protocol bridge; neither
process restarts. Observer v45 reads the public stock GameTooltip without
changing it. Its deployment through ordinary reload preserves both actors.

`equipment_tooltips_01` opens the character panel and hovers the equipped helmet,
cloak and two-handed sword. Their rendered tooltips and public names, item links
and owner frames match native inventory and the pinned native Item-sparse.db2:
78688 Colossal Dragonplate Helmet, 77097 Dreamcrusher Drape and 78478 Gurthalak,
Voice of the Deeps. The complete native inventory, money, archaeology state,
talents, glyphs and known spells remain unchanged.

This qualifies item identity on those three equipped slots. The observer records
at most 16 text lines; the helmet has 29. Its overlay partly obscures the helmet
heading, whose full name is independently checked through public tooltip text.
Native effective stats, every tooltip line and account appearance collection
remain open. The stock appearance ownership message is outside this check.

`glyph_tooltip_01` finds the already learned Battle glyph and displays its correct
stock tooltip. Final panel cleanup fails because the stock search edit box consumes
Escape to clear focus. The input guard refuses another Escape with an unchanged
panel signature. That failed episode remains unchanged in the evidence.
`glyph_tooltip_cleanup_01` binds to its exact source and unchanged native/runtime
state, then closes the observed stock window button normally.

The fresh `glyph_tooltip_02` passes the whole trial, restores the original search
and closes the panel through that button. Native GlyphProperties 483 binds aura
58095 and the already learned spell 58276. The rendered tooltip says Glyph of
Battle, Minor Glyph, and describes the Battle Shout duration and area bonus.
This qualifies the learned catalog tooltip only; socket replacement and actual
spell effects remain separate checks. No native state changes.

After deploying the current observer, use new owned evidence directories:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_observer_deploy --output <new-deployment-directory> --version 45
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_tooltips --family equipment --output <new-equipment-directory>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_tooltips --family glyph --output <new-glyph-directory>
```

The glyph trial requires the primary warrior to have already learned Battle
normally. Source-bound cleanup is available only for the exact owned failed
glyph-tooltip episode with unchanged actor, process lifetimes and native state:

```sh
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_tooltips --family glyph --recover-source <closed-failed-glyph-episode.json> --output <new-cleanup-directory>
```

Lua syntax checks pass. Original failures and reviewed frames are retained for
the DVC checkpoint; cleanup recovery does not relabel the failed trial.
