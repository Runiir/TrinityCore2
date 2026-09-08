# Fire Mage Review Reference (Cataclysm)

- Resolve the promoted comparator with `pixi run python -m tools.raid_program.raid_workloop spec fire_mage`; retain revision, request/result identities, duration, encounter, buffs, stats, APL and action counts.
- Treat a stationary single-target WoWSims result as cadence structure unless live setup, effective stats, targets, buffs and duration match.
- Primary cast identities: Fireball `133`, Scorch `2948`, Living Bomb `44457`, Living Bomb explosion `44461`, Fire Blast `2136`, Pyroblast! `92315`, Combustion `11129`, Flame Orb `82731`/damage `82739`.
- Hot Streak `48108` and Impact `64343` can appear as WCL cast-table proc rows; exclude them from GCD-cast counts.
- Local profile semantics: Pyroblast! requires the owned Hot Streak aura; Combustion requires an owned target Ignite; Living Bomb maintenance rejects an existing owned aura.
- Keep proc absence, candidate rejection, native submission and landed damage separate. Sparse Fireballs reduce crit/proc opportunities and can explain downstream Pyroblast!/Combustion loss without proving a proc bug.
- `spell_cast` is native submission instrumentation, not completion or damage landing. A post-submit `already_casting` reason on an `ok` event is not rejection.
- Compare Fireball landed events to Fireball submissions and report both rates. Periodic ticks/explosions are outcomes, not applications.
- Report Living Bomb ticks and explosions separately; multi-target application counts are encounter-dependent.
- Exclude zero-origin transfer/mirror rows such as Point of Vulnerability from actor-originated damage.
- Damage per event is descriptive until scoring-start intellect, spell power, crit, haste, hit, mastery, buffs, consumes and target modifiers are available.
- Compare normalized glyph property IDs, not glyph item IDs. The promoted Fire prime set `42739/42743/42751` normalizes to `316/320/328` (Fireball/Pyroblast/Molten Armor); property `330` is Cone of Cold and is not exact reference parity.
- `moving_fraction` in combat aggregates is event-weighted, not movement wall time; never convert it to seconds.
- The current Scorch row has `max_mana_pct=0.4`. Its `moving_filler` tag is metadata: a 1,500 ms Scorch still meets the generic cast-time movement gate unless native Firestarter movement semantics are implemented.
- Propose widening Scorch only from a snapshot with a usable target, actual movement, mana above 40%, and no higher-priority usable instant; first rule out shared stale-motion or arbitration faults.
- A `Casting` action result can mean executor scheduling. Verify `HasUnitState`/generic/channel IDs, native motion type, spline state, displacement, vehicle state and a matching `spell_cast` before calling it active casting.
- Fire range findings must retain spell/profile range and target reach. Do not encode encounter formations as universal class behavior.
