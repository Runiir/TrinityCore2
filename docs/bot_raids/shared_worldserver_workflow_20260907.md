# Shared-worldserver workflow status

Updated 2026-09-10. This file contains one current status. Known failures and
rejected assumptions belong in the [error ledger](error_ledger.md). Historical
run narratives are retained in Git, including this file at commit 6882d0c204;
closed generated evidence is tracked by DVC under artifacts/cata_raid_program.
Do not treat a historical proposed repair as current launch instructions.

## Current run

Source `6882d0c20447283a9c97f006cdae2c7ea136a9db` built on its first attempt
and cleared Magmaw 10N in exactly 209.211 seconds. All ten bots survived the boss.
Three bots died on Drudges and recovered: Fire hook 30007, Affliction 30008 and
Paladin tank 30001. Native exit, build verification and cleanup passed.
This is a development clear, not throughput acceptance or training data.

The actual roster is 2 tanks, 3 healers and 5 DPS. All ten actors remain under
role review. Compare exact native pull-to-death damage and healing; exclude
friendly damage and mirrored 79010 events while retaining owned pet damage.
The route-event span includes approach time and is not the fight denominator.

The all-bot review reports 28,935,523 hostile damage, 138,307.847 exact DPS,
and 14,447.548 HPS. The five DPS actors contribute 104,040.571 exact DPS.
Throughput remains unresolved. Late targets remain valid, but optional parasite
support can be admitted without executable offense while repositioning is
forbidden. Fire hook deals only 244 damage over the last 57.689 seconds; Hunter
has 23 native Serpent Sting LOS failures. This is a shared target-admission
boundary, not proof of wrong class coefficients or a stale head-return target.

## Repair acceptance

The 6882 batch contains two independently reviewed runtime changes. Twenty
focused tests pass, including a repeated-hazard fixture that fails old source.

- Hazard movement no longer repeatedly cancels a native moving-permitted cast.
  A Hazard Scorch survives its full 1.246s duration with path progress; an
  uncovered Fireball still interrupts. The required Scorch finish/landing
  nevertheless fails, with no terminal native failure code. Preserve this
  repaired interruption boundary and route the missing outcome to OBS-008.
- The typed tank-swap repair is accepted: Paladin taunt at +90.601s transfers
  ownership by +91.919s while its movement continues. Reciprocal DK taunt at
  +185.136s is followed by body ownership at +186.133s. Exactly two swaps occur.

## Open work across the roster

- Optional support targets need actor-specific native LOS/range admission.
  Preserve mandatory personal-threat/bait obligations and hazard movement;
  select only observed legal alternatives. Existing pure facts lack LOS.
  ENC-003. This is the next shared DPS repair, ahead of coefficient tuning.

- Elemental Lightning Bolt has a proven artificial 12-yard cast rejection.
  The same field also controls positioning. Separate those semantics explicitly;
  do not hide a duplicate filler row from the positioning observer. DPS-037.
- Affliction Shadowflame and Blood Heart Strike remain blocked by shared area
  protection. No unreviewed blanket exception is permitted. DPS-029/DPS-026.
- Drudge escape destinations violate Rush-bait isolation. The source-safe
  fallback is not a proven full-roster-safe path. ENC-001.
- Healer review still lacks attributable Discipline absorption. OBS-006.

Preserve accepted MM haste/filler, Affliction boss-health potion, Elemental
moving Lava Burst, owner effective-stat observation and native Vengeance fixes.
No missing owner passive or damage-coefficient defect has been established by
the gear/stat review. Existing clear results do not accept all class throughput.

## Evidence and next action

The 41266 capture is DVC-published and verified via a fresh empty-cache remote
download; exact large local payloads were evicted after every reader finished.
Pointer: `artifacts/cata_raid_program/magmaw_development_41266a508c_20260908.tar.gz.dvc`.

The 6882 reviews are closed. Evidence is DVC-published, verified with a fresh
remote download, and exact large local payloads are evicted.
Pointer: `artifacts/cata_raid_program/magmaw_development_6882d0c204_20260908.tar.gz.dvc`. The current source is pushed to
`codex/dps-canary-20260908`. The
[active work unit](../../experiments/configs/cata_raid_active_work_unit_v1.json)
routes the next shared target-admission repair and retains the separate native
cast-failure observation gap. No unchanged encounter retry is justified.
