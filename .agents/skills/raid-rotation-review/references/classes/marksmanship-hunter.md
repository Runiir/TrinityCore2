# Marksmanship hunter review notes

Use these notes only after confirming the live actor is Marksmanship and recording the loaded profile identity and hash.

## Verified live priority semantics

- Rapid Fire is the major haste cooldown candidate.
- Aimed Shot is selected during Careful Aim or when the fast-cast state is active.
- Steady Shot is the focus builder and maintains Steady Focus through its paired-shot state.
- Chimera Shot and Readiness have explicit readiness and sequence gates.
- Serpent Sting and normal Chimera use are outside the Careful Aim gate in the reviewed profile.
- Kill Shot is the execute action.
- Arcane Shot is the focus dump when focus is at least 66 or Chimera remains at least four seconds away.
- Steady Shot is the filler when higher candidates fail their gates.
- The accepted live range is 40 yd for the profile and 45 yd for Kill Shot. Do not reopen it without new spell-range evidence.

## Measurement traps

- Native Improved Steady Shot applies haste aura `53220`; the talent aura
  `53221` and the simulator's tagged aura are different identities. Observe
  the triggered aura for maintenance and preserve an unconditional final
  Steady Shot when maintenance is not due.
- Compare the exact eligible APL branch before calling a priority inversion.
  Conditional Aimed Shot can precede Steady maintenance; an Aimed win with a
  missing haste buff alone does not prove a defect. A low paired-shot count
  also needs the intervening movement and native casts, not just total procs.
- Record selection, movement permission, native submission, completion, and landed damage as separate edges.
- `cast_combat_spell` for spell 75 can mean keeping ranged auto enabled. It is not proof that an Auto Shot fired.
- Diagnose Auto Shot cadence from native swing fire and suppress reasons, with target, movement, and death windows joined.
- Focus-gate rejections need a timestamped focus timeline before they support starvation, capping, or threshold changes.
- `movement_requires_instant_action` attributes a rejected cast to movement arbitration. It does not establish a class-priority fault.
- Compare cast mix on attributable alive and active time. Do not stretch a partial encounter window into a 300-second DPS result.
- Keep owner and pet events separate. Match owner stats, pet stats, pet type, pet uptime, and inheritance before tuning pet output.
- Use originated or deduplicated damage. Mirrored owner/pet effects can inflate raw event damage.
- Match race, talents, glyphs, gear, reforges, enchants, gems, consumes, effective stats, buffs, debuffs, target count, duration, and movement before using a DPS ratio.
- Compare glyph item, spell-item-enchantment property, and applied aura identities. Route a stale canonical glyph projection to setup ownership rather than compensating in class policy.
- A same-class log from another hunter spec is not a same-spec external comparator.
- Cooldown submissions do not prove aura application, charge use, cooldown start, or later readiness. Join receipts to native outcomes.
- Target changes can be encounter-owned. Require the encounter target contract before changing Marksmanship target policy.
