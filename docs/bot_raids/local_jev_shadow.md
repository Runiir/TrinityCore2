> Status 2026-09-23: removed from the tuning workflow. The tooling below stays
> on disk for a later evaluation; no skill or graph step calls it.

# Local diagnostic shadow

Integration source: `68621071ccb3df1eb6927fbafa83a8c5dccdbb3a`.
Imported the offline analyzer, all-actor WCL timeline comparison, combat summary
consumer and their tests/references. Native runtime, class, boss, SQL and live
runner changes remain on the canary branch for separate causal review.

Local Laya now supplies diagnostic suggestions at `http://127.0.0.1:8000/v1/systemone`.
Native evidence and independent review determine correctness. Model predictions,
confidence and agreement with hosted Jev are not labels or action authority.

## Start the local service

Deployment: `$HOME/.local/share/trinity-laya`. The package is `laya==0.3.3`,
with `convaiinnovations/laya` subfolder `typed-decisions` pinned to revision
`c5d78730f3493e4fe16d61507ef4b78eef7318cf`. The request/response model identifier
is `convaiinnovations/laya-typed-decisions`. The adapter and Pixi manifest/lock
are tracked in `experiments/configs/local_laya/`.

```sh
mkdir -p "$HOME/.local/share/trinity-laya"
cp experiments/configs/local_laya/{server.py,pixi.toml,pixi.lock} "$HOME/.local/share/trinity-laya/"
pixi run --manifest-path "$HOME/.local/share/trinity-laya/pixi.toml" --frozen serve
```

For an existing deployment run only the last command, after checking that no
service already owns port 8000. Readiness: `curl http://127.0.0.1:8000/health`.
Health records the actual model, revision, device, dtype and context limits.
The current deployment uses CUDA/float16. The former local Qwen/SimpleJev
endpoint has been decommissioned. There is no automatic fallback to it.

The pinned checkpoint accepts 1,024 tokens per question and a 256-token question/options
head. The adapter rejects any truncated instructions, criteria or state with
HTTP 422 and a token-budget receipt. The client uses an explicit compact Laya
projection and preserves unavailable evidence and reference limitations. Never
truncate silently or sort option keys to improve agreement.

The previous thread's implementation is retained by commit `60ae9760b4` and
`artifacts/cata_raid_program/magmaw_jev_laya_cpu_replay_20260919.tar.gz.dvc`.
It was a temporary CPU adapter on port 8001. Its context-fit requests
still reached 1,024 tokens, and its long question headers were subject to Laya's
own truncation. Retain that replay as historical boundary evidence; it does not
validate the new untruncated projection or establish diagnostic accuracy.

The replacement was exercised on the closed lawful Magmaw run `2fcd4133aa`.
All six DPS actor requests returned typed responses, using 896–928 input tokens
with no truncated fields. Two suggestions failed deterministic evidence checks
and remain flagged for review. All six examples are quarantined and unlabeled.
This validates the local transport and packet limits, not model accuracy or raid
performance. Exact requests, responses and backend identity are retained in
`artifacts/cata_raid_program/magmaw_laya_migration_20260919.tar.gz.dvc`.
An earlier packet wording produced four flagged suggestions; both batches are
retained. The final batch is `shadow_verified/`, generated from commit `00784a1708`.

## Review one closed run

Use the existing completion-watchdog capture. Do not query a growing run.
Canonical development captures are read directly from `report.json` and its
hash-bound normalized raw batch. The review tools reassemble the existing combat
stream in memory; separate copied combat exports are unnecessary. Keep that raw
batch through review and verified DVC publication. A native death receipt remains
separate from capture completeness and qualification.
The following commands use shell variables naming its closed directory and a
new output directory. No hosted key is needed. The default local model is Laya.

```sh
pixi run python -m tools.bot_ml.compare_magmaw_timelines --bot-run "$closed_run" --wcl-manifest experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_wcl_cast_timelines_v1.json --output "$review_dir/timeline.json"
pixi run python -m tools.bot_ml.analyze_magmaw_trace --input "$closed_run" --prepare-only --run-id "$run_id" --timeline-comparison "$review_dir/timeline.json" --output "$review_dir/review.json"
pixi run python -m tools.bot_ml.jev_shadow --review "$review_dir/review.json" --identity "$identity_json" --backend-receipt "$backend_json" --native-report "$closed_run/report.json" --timeline-summary "$closed_run/report.timeline-summary.json" --output "$review_dir/shadow"
```

Every run now receives both local Laya and hosted Jev review for each admitted
bot, followed by the class or role reviewer. Run the second collection explicitly:

```sh
pixi run python -m tools.bot_ml.jev_shadow --review "$review_dir/review.json" --identity "$identity_json" --backend-receipt "$hosted_backend_json" --backend hosted --env-file "$jev_env_file" --native-report "$closed_run/report.json" --timeline-summary "$closed_run/report.timeline-summary.json" --output "$review_dir/hosted"
```

Supply `--native-report` and `--timeline-summary` together. The collector binds
both to the review, run identity and admitted actor GUIDs before either API call.
It projects exact pull-to-native-death DPS/HPS, owner and owned damage, and
survival from the existing timeline summary. Missing absorption, mana,
overhealing, threat and mitigation remain unknown; healer damage activity is
not healing activity. Omitted paired inputs remain explicitly unknown.
Use `--prepare-only` first and check those actual packets with the deployed
Laya tokenizer. A successful heuristic estimate does not prove they fit.

The hosted adapter reads `JEV` from the environment or the specified file and
uses the existing TypeSafe client. Credentials are never part of retained rows.
Retain exact ordered requests, resolved response model identity, failures and
latency separately for each provider. Neither provider is a fallback for the
other. Both retain quarantine and no action authority.

DPS packets preserve the existing causal screen. Tank/healer packets use their
own identity and actor-scoped native rows; unavailable healing, mitigation,
threat or damage observations remain unavailable. A sparse role packet cannot
replace the specialist's review of full native evidence. An insufficient-evidence
answer is an advisory result, not a contradictory repair recommendation.

If raw damage events are unavailable, omit the timeline command/argument.
The resulting review must preserve the missing observation; an old derived
timeline cannot be silently promoted to a newly corrected one. Review inputs
are versioned by the analysis Git source and SHA256 of the exact request.

`identity_json` needs the actual `run_id` and `closed: true`; only use this after
checking the native terminal receipt. Copy observed identity fields from the
closed evidence manifest, not desired configuration. Unknown fields stay absent.
The collector lists required identities in `REQUIRED_IDENTITY` and quarantines
incomplete identity. `backend_json` records upstream source, model checkpoint,
prompt revision, Pixi lock hash, device, dtype and context limit.
The CLI records current source-file hashes under `backend.execution_source`
before building packets. Supplied `client_files_sha256` remains a receipt claim;
it can be stale and must not override the observed execution-source hashes.
Run from a clean, frozen analysis checkout. These hashes bind source files at
startup, not historical predictions or remote hosted model weights.

All examples currently remain in quarantine, even when identities are complete.
They have no adjudicated labels. `examples.jsonl` stores the exact ordered HTTP
request, response, model receipt, latency, failure, run and actor identity.
`summary.json` and `dvclive/` record batch counts. A backend error retains its
example and continues to the next actor; the command then exits nonzero.
There is no hosted fallback. Existing batches cannot be overwritten.

## Later training

The current task is **post-run diagnosis**, not moment-to-moment bot control.
Post-run outcomes are valid context for this diagnostic task, but would leak
future information into an action policy. `action_policy_eligible` is always
false. Preserve failed/uncertain examples for later adjudication.

Before training, bind each label to reviewed native evidence and a resolved
issue/fix, complete run identity, script fidelity and capture quality. Predictions
and hosted agreement never become labels automatically. Keep all actors from a
run in the same partition; group related attempts/rosters before assigning a
holdout. The current `split_group` is a minimum grouping, not a finalized split.
Local confidence has not been calibrated on this raid diagnostic task. Evaluate it on held-out
adjudicated examples before choosing any threshold.

Publish only the compact review/shadow batch through `dvc add`, `dvc status` and
`dvc push`. Verify the exact remote objects before removing reconstructed inputs
or the published local payload. Retain the Git pointer and reconstruction recipe.

## Diagnostic corrections

- Pet hits no longer fill owner damage gaps. Unknown/proc effects remain marked
  as such; landed-effect cadence cannot prove completed-cast uptime.
- An aggregate first/last envelope that straddles a gap gives only possible
  overlap. Counts inside a gap are known only for fully contained envelopes.
  Even contained failure evidence does not establish the cause of the gap.
- Clipped native DPS is compared numerically only with timestamped WCL damage
  over that same horizon. WCL whole-fight DPS remains descriptive context.
  A common horizon still does not match phase coverage, gear or assignments.
- WCL completed casts and native landed effects retain separate counts. Their
  difference is not ranked as a cast deficit.

Contracts: [TypeSafe API](https://docs.typesafe.ai/api),
[Laya source](https://github.com/NandhaKishorM/laya), and
[model card](https://huggingface.co/convaiinnovations/laya).
