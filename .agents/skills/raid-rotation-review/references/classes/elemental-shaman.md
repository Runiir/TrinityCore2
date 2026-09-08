# Elemental Shaman review notes

Use these as class-specific checks after binding the current exact request, runtime profile, actor, target, and trace. They do not define encounter tactics.

## Exact setup and movement semantics

- For the current P4 exact reference, glyph items are prime `41531,41524,71155`, major `41537,41533,45778`, and minor `44923,43385,43386`.
- Pinned DBC maps item `71155` to glyph property `950`, aura `101052`; its effect is `SPELL_AURA_CAST_WHILE_WALKING` (330) with a Shaman spell-family mask.
- Movement compatibility is per spell. Check `HasAuraTypeWithAffectMask(SPELL_AURA_CAST_WHILE_WALKING, spellInfo)` at candidate admission and again before executor stop/yield. Glyph presence alone does not prove the bot caller honors it.
- Generated character glyph slots are grouped by DBC type: major properties occupy `glyph1,glyph4,glyph6`; minor `glyph2,glyph3,glyph5`; prime `glyph7,glyph8,glyph9`.
- Prefer the exact target catalog as the provisioning source. Preserve an explicitly configured role fallback when no promoted exact target exists.
- Spiritwalker's Grace `79206` needs both spellbook provisioning and a player-like policy trigger. A WCL cast proves availability/use, while a stationary WoWSims APL may omit it.

## Priority and cadence checks

- The current exact single-target APL orders Fire Elemental, Searing Totem, Lava Burst with Flame Shock remaining over 2s, Flame Shock refresh at 2s, Earth Shock at nine Lightning Shield stacks with Flame Shock remaining at least 3s, then Lightning Bolt.
- Chain Lightning is target-count policy, not the single-target filler. Keep its enemy-count gate distinct from Lightning Bolt eligibility.
- Lava Burst requires owned Flame Shock state. Trace missing aura, aura duration, target identity, candidate rejection, submission, and landing separately.
- Fulmination damage is a triggered outcome of Earth Shock/Lightning Shield state; do not count it as another manual cast.
- Lightning Bolt and Lava Burst overload/tag variants are proc outcomes. Do not add them to manual cast counts.
- Lava Surge `77762` rows are proc records, not Lava Burst casts.

## Measurement traps

- A raid clear, a 300-second dummy result, and a short WCL kill have different clocks and conditions. Compare action structure until setup and immutable scoring-start stats match.
- Require exact glyph, talent, gear, consume, race, distance, and effective-stat identity before damage-per-event or coefficient claims.
- `spell_cast` is submission instrumentation, not cast completion. Follow native result and landed damage/effect.
- A post-submission `already_casting` reason can accompany `result=ok`; it is not by itself a rejection.
- Runtime `moving_fraction` in combat aggregates is event-weighted, not wall-time movement fraction.
- Exclude mirrored vulnerability rows from originated damage; retain owner and pet attribution separately.
- Static same-bucket row order is unresolved without runtime score/tie-break evidence.
- If movement or range authority blocks every action before submission, route the shared cause to the runtime coordinator rather than weakening class ranges.
