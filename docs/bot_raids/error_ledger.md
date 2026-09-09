# Raid program error ledger

Updated 2026-09-09. This is the canonical index of known blockers and rejected
assumptions. The current workflow summary chooses work; this ledger explains
what has already failed. Do not create a new handoff document merely to copy it.

## Current queue

| ID | Status | Proven failure / limit | Next action |
| --- | --- | --- | --- |
| DPS-006 | Build passed; live pending | Orb's forward destination and execution both use ground pathfinding; it leaves damage range before the first tick. | Run the already reviewed `979f5c832f` Fire canary. Require native 82736 and owner-attributed 82739 damage, not just movement. |
| DPS-007 | Diagnosis open; implementation paused | Hunter compares an 11-row catalog with a 14-row loaded pet spellbook. Normal saving also persists those 14 rows. | Establish the canonical native spell/actionbar fixed point before changing the producer or consumer. Do not build the rejected 11-row launch requirement. |
| DPS-008 | Setup failure confirmed | Affliction actor 1306 has enchant 4115 and a catalog Tailoring requirement, but a fresh `character_skills` readback has no skill 197 row. | Reconcile actual selected-actor profession setup from the canonical requirements, verify readback, then validate native applicability. Do not tune Affliction coefficients. |
| OBS-001 | Observation gap; no repair admitted | Current complete calibration exports have no aggregate `native_spell_finish` series, although full/delta serialization was repaired. | Inspect producer/capture mode if a future diagnosis needs cast-finish joins. Do not rebuild only to repeat the serializer change. |

## Closed blockers

| ID | Accepted repair | Live evidence | Wrong assumption to avoid |
| --- | --- | --- | --- |
| DPS-001 | Native and Python self-provided aura admission follow caster ownership for player and target effects. | `2b661e8b67` Fire passed owned-aura checks. | An aura ID alone does not prove an external buff. Fix every actual consumer, including Python final acceptance. |
| DPS-002 | The real calibration launch reconciles the selected actor's learned spells and reads them back. | `a3d0719729` and `ec02d7196a`: Wizardry 89744 present; native intellect multiplier 1.05. | Generated SQL or a catalog entry does not prove an existing actor learned the passive. |
| DPS-003 | Promoted spec reaction settings feed the native combat scheduler with a 100 ms floor. | `ec02d7196a` Fire: 2,998 decisions, about 100 ms apart; old Fire used about 500 ms. | WoWSims is event-driven; its 10 ms setting is not a polling frequency. Faster decisions also enlarge exports. |
| CAP-001 | Latest heartbeat responses share the bounded capture budget; malformed/truncated exports remain infrastructure failures through final acceptance. | `ec02d7196a`: all 1,399 Fire, 1,738 Hunter and 2,239 Affliction chunks retained. | Equal per-command partitions discarded a complete native export while other capacity was unused. Partial scalars are not a complete accepted run. |
| DPS-005 | Orb suppresses inherited idle owner-follow. | `ec02d7196a`: all five Orbs retain idle motion 0 and do not return to the owner. | Removing follow does not prove damage. The separate destination/execution defect is DPS-006. |
| BUILD-001 | Preserve real native prerequisite includes when splitting translation units. | `9423ec8a17` repaired the earlier missing Common.h/Pet.h build failure. | Extracted-body fixtures do not compile the real include chain. The actual build uses non-unity mode. |

## Active error details

### DPS-006: Orb destination and execution

- Observed on complete `ec02d7196a` Fire evidence: five casts, zero Orb damage.
  The forward path ends 13.476 horizontal yards from the target. Aura 82690
  appears around 400 ms; the first nominal tick is around 1.4 s, after the Orb
  has left the 10-yard selector cylinder. Target validity, LOS and attackability
  remain true. Exact tick timestamps are inferred from native scheduling.
- Earliest code mismatch: `summoner->MovePositionToFirstCollision` derives a
  ground-navmesh endpoint; default `MovePoint` pathfinds again. Changing only
  one call would leave the other rewrite intact.
- Repair `979f5c832f`: one shared collision implementation with unchanged
  default behavior; only Orb requests straight collision calculation and
  straight native movement at both submissions. `Object.h` remains unchanged
  to avoid broad recompilation. Five focused tests and independent Sol review
  pass; native build passes. Live damage is not yet accepted.
- Reject: victim requirements, radius/tick/coefficient changes, dummy-position
  changes, bot Z steering, collision bypass, or treating no-follow as DPS repair.
- Evidence: [Fire ec02 archive](../../artifacts/cata_raid_program/calibration_fire_mage_ec02d7196a_20260909.tar.gz.dvc),
  member `calibration-fire_mage-ec02d7196a/dps-review/flame-orb-live-review.md`.

### DPS-007: Hunter persisted and loaded identity

- `ec02d7196a` Hunter: 23,106.767 DPS, pet 737,564 damage, alive throughout.
  All 3,002 pet setup observations nevertheless fail identity; ready ticks are
  zero. This is not evidence of an idle/dead pet.
- Generated authority expects 11 rows, hash `be83c8a872bfb2b7fca6d9fb26d6aa1a0ebb1e9b00eb93d36d1f2ffa36254b74`.
  Loaded state has 14, hash `bc3322f102216e3308dc94e4fa30e2960641678949109ccbda1a90063e684ce8`.
  Extra spells are 1742, 24604 and 65220; 2649/17253 autocast states also differ.
- A fresh parent SELECT after normal native saving found that same 14-row
  state in `pet_spell`. The report's first proposed requirement to see 11 rows
  before every launch is therefore paused. A new loader-receipt subsystem has
  **not** been implemented. Prove the native derivation and stable canonical
  setup first; do not merely bless an observed spellbook or delete valid spells.
- Affected callers are duplicated in CalibrationReset.cpp, CalibrationBot.cpp
  and CalibrationCompletion.cpp. Rows already uses the shared
  BotWorldPopulationMgrCalibrationIdentity helper. A Completion-only patch
  would be incomplete.
- Actual Hunter throughput remains unresolved even after identity is fixed.
  936 Auto Shot maintenance decisions are not 936 shots; 117 damage events
  landed. The retained WCL raid has Survival, not Marksmanship.
- Closed evidence is currently under
  `/home/runiir/Games/trinity-shared-instance-validation-03cb01db0b/calibration-marksmanship_hunter-ec02d7196a/dps-review/`.
  Publication remains pending. The design addendum must supersede the original
  repair packet explicitly before dispatch.

### DPS-008: Affliction profession setup

- `ec02d7196a` Affliction: complete 300 seconds, 29,240.243 DPS (93.3806% of
  reference), 388.6 self-healing HPS, no deaths or movement loss. Throughput
  thresholds pass; this does not establish every setup input.
- The review explicitly lacked independent profession readback. Parent then
  queried actor 1306, skill 197, and received no row. Catalog requirements are
  `provisioning_bot.profession_setup.requirements`, not `bot.skills`.
- Reject the earlier statement that the corrected profession setup was
  accepted. Equipped enchant identity is not native enchant applicability.
  The launch currently reconciles learned spells, not profession requirements.
- Evidence: local `calibration-affliction_warlock-ec02d7196a/report.json`,
  `dps-review/affliction-calibration-review.md`, and
  `profession_postrun_readback.json` under the same validation root.
  Publication remains pending; no claim of an observed Lightweave proc.

## Run index and acceptance boundaries

| Source / spec | DPS | HPS | Interpretation |
| --- | ---: | ---: | --- |
| `798a115d45` Elemental | 32,911.683 | 0 | 88.9522% of reference, optimization accepted. Preserve this result. |
| `2b661e8b67` Fire | 23,839.460 | 0 | Missing actual Wizardry; owned-aura repair passed. |
| `a3d0719729` Fire | 28,821.683 | 0 | Partial native prefix only; final capture truncated. Not accepted full-window evidence. |
| `ec02d7196a` Fire | 29,021.037 | 0 | Complete; setup/cadence pass; below 85%; Orb still zero. |
| `ec02d7196a` Hunter | 23,106.767 | 0 | Complete; pet identity incompatibility and hard-floor failure. |
| `ec02d7196a` Affliction | 29,240.243 | 388.6 | Complete; throughput passes; actual profession setup incomplete. |
| `090f24f4b8` Magmaw 10N | 128,636.918 | 19,225.751 | Native clear; 233 damage-bearing seconds, zero boss deaths. Roster DPS objective remains open. |

Magmaw's encounter-start-to-death duration was 271.011 seconds. Do not mix that
denominator with 233 damage-bearing seconds. Retained WCL uses 1 tank / 1 healer /
8 DPS versus our 2 / 3 / 5; its 378,849 aggregate DPS is not a matched roster floor.
All current development calibrations remain training-ineligible because the
qualification identity and non-certifying fixture boundaries are unresolved.

## Updating and using the ledger

1. Before dispatch or retry, select an existing ID or add one evidenced failure.
   Include that ID, current evidence, rejected approaches, owned callers and the
   acceptance condition in the worker packet. Do not send the entire history.
2. Update the same entry after diagnosis, implementation, review, build and live
   result. These are separate states. A repair with no live outcome stays pending.
3. Record every subsequent attempt as source/run ID plus what changed and its
   outcome. No new run solely because a worker finished or metadata is stale.
4. Count only attempts that reach the same causal edge. Historic counts before
   this ledger are not reconstructed or invented. At ten occurrences, stop
   unchanged retries and write the causal summary against this ID.
5. Keep large traces in DVC. Link the archive and member when published; remove
   obsolete local payload references after verified eviction. A ledger edit
   needs no extra approval, build or live experiment.

## Process failures already observed

- Broad reviews and handoffs omitted actual launch consumers or duplicate native
  callers. Parent caught these late. Map the finite launch-to-outcome path before
  assigning an implementation; return all known blockers together.
- Fixtures proved isolated behavior while setup, native include closure or final
  report assembly remained wrong. Use the actual failing caller and negative
  counterexample; do not equate a passing stub with live success.
- Report and catalog assumptions survived as stale current status. This ledger
  records their replacement explicitly; old reports remain historical evidence.
- Agent usage limits interrupted Hunter diagnosis and implementation preparation.
  No Hunter gameplay edits were made. This is an infrastructure limit, not another
  failed canary or evidence that a different model repaired DPS.
