# Parallel Bot Autonomy Runbook

This workflow keeps validation lanes running independently until every deliverable from `.codex/plans/auto_bots/18.md` has accepted evidence. A failed lane creates a follow-up lane; it does not stop other lanes.

## Checklist

Create or refresh the master checklist:

```bash
pixi run bot-autonomy-checklist --output .codex/plans/auto_bots/master_checklist.json
```

Each row moves through `pending`, `running`, `review`, `accepted`, or `needs_followup`. A deliverable is terminal only at `accepted` with an evidence artifact path.

## Lane Isolation

Generate one config root per live lane:

```bash
pixi run bot-lane-configs --lane 0 --lane-name stonecore_full_clear_r1 --db-isolation per-lane-clone
```

The manifest records unique world, instance, RA, and SOAP ports, isolated log and pid paths, a bot pool tag, and per-lane auth, characters, world, and hotfix schema names. The generated `db_clone_plan.json` records clone, reset, and cleanup commands. Final Stonecore and Blackwing Descent clears must use fresh per-lane DB clones and uninterrupted whole-scenario runs.

## Watchdog Validation

Generated run plans default to completion-watchdog validation:

```bash
pixi run bot-validation-run-plan --validation-scenario-dir dataset/validation_scenarios --output-dir dataset/validation_run_plan
```

The resulting commands use `pixi run bot-live-validate --duration-policy completion-watchdog`. Reports include `completion_reason`, `watchdog_state`, `progress_counters`, `acceptable_final_evidence`, and `final_evidence_rejections`. Emergency wall-clock timeouts, segment-only reports, stale/no-progress reports, and teacher-assisted-only reports are not final clear evidence.

## Promotion

Lane-local reports stay under `artifacts/live_validation_instances/<lane>/...` until review. Promote only accepted evidence into canonical DVC paths:

```bash
pixi run bot-live-artifact-promote \
  --source-report artifacts/live_validation_instances/stonecore_full_clear_r1/report.json \
  --canonical-report artifacts/live_validation_scenario_reports/stonecore_5n.json \
  --manifest artifacts/live_validation_promotion/stonecore_full_clear_r1.json
```

After promotion, checkpoint the canonical artifacts with DVC and sync:

```bash
pixi run dvc status
pixi run dvc push
```
