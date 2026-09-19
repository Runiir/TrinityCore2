# Concurrent class calibration

Use the current promoted WoWSims `self_provided_baseline` requests before
changing class damage or priorities. These are exact 300-second, level-88,
11977-armor, passive targets with the pinned execute-health schedule. A city
dummy that remains at full health is a different experiment. Name filtering
separates attribution but cannot prevent shared debuffs or splash damage.

The runner reuses the existing native calibration and cohort lifecycles. It
starts at most two private-phase fixtures on one owned worldserver. Each bot
retains the same target coordinates, range, native LOS/path checks, gear,
consumes, and class actions as the serial fixture. Only `single_target_300`
uses private phases. Tank and healer modes retain their existing setup.

From a clean committed checkout with a verified build receipt:

```bash
pixi run python -m tools.raid_program.wowsims_reference_workspace hydrate
pixi run python -m tools.raid_program.run_dummy_calibrations \
  --build-receipt /absolute/path/to/worldserver-build-receipt.json \
  --output /tmp/dummy-current-source-seed1 \
  --concurrency 2
```

The default batch covers Survival, Fire, Affliction, Elemental, and Balance.
Use repeated `--spec` arguments for a bounded subset, or `--concurrency 1` for
a serial control. Every selected spec must have a verified promoted request.
Do not regenerate a reference merely because its payload was evicted.

Provisioning and pool reset happen once before server launch. Never start two
copies of this runner or reset the pool while another cohort is active.
The runner owns the worldserver and refuses to replace an existing one.
The asset receipt identifies missing offline map files. When creating a new
worktree, materialize the exact selected-map members from the verified native
data into independent files under `data/mmaps`, with the contracted `0444`
mode. Do not chmod hardlinks to the live DataDir or bypass an inventory mismatch.

Each spec directory contains the request, addressed command responses,
compact native progress, complete final calibration report, and cleanup.
`batch.json` binds source, build, executable, configuration, server epoch,
requested specs, results, and server exit. Preparation receipts bind actual
database inputs; `dvclive/` records measured DPS/HPS and capture acceptance.

Progress polling omits heavy per-action arrays. One full status is captured
before each addressed stop. Full diagnostics remain authoritative for casts,
outcomes, pet damage, and reference compatibility. A failed capture retains
its measured damage but cannot pass the batch. A successful concurrent batch
requires a peer to keep advancing its native scoring clock and damage after
another cohort stops. Phase observations prove each actor and target share
their assigned phase; peer invisibility is not directly sampled and is marked
unobserved rather than manufactured from expected values.

`measurement_completed` means an exact, isolated window with complete transport.
`reference_comparable` separately reports whether the setup matches the pinned
reference; `comparison_rejections` names each mismatch. `diagnostics_complete`
is independent of both. A completed run can retain valid DPS/HPS while an extra
potion or omitted simulator racial blocks comparison. Do not remove legitimate
live actions merely to satisfy an incomplete reference. Preserve that reference
and generate a separately attributable corrected control.

`batch_accepted` remains the strict capture/reference gate, including verified
cleanup. `performance_accepted` and `training_eligible` remain false.
Review effective stats, native consumable use, spell cadence, damage per
event, pet contribution, and downtime against the promoted request before
claiming class parity. Legacy role thresholds are not full WoWSims parity.

Publish the closed batch and its review through DVC, run targeted `dvc status`
and `dvc push`, verify an empty-cache remote reconstruction, then evict exact
duplicate payloads. Keep the compact comparison and DVC reconstruction path.
