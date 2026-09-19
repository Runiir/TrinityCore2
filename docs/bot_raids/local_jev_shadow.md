# Local diagnostic shadow

Integration source: `68621071ccb3df1eb6927fbafa83a8c5dccdbb3a`.
Imported the offline analyzer, all-actor WCL timeline comparison, combat summary
consumer and their tests/references. Native runtime, class, boss, SQL and live
runner changes remain on the canary branch for separate causal review.

Local SimpleJev supplies diagnostic suggestions. Native evidence and independent
review determine correctness. Hosted Jev predictions are comparison data, not
ground truth. Neither backend may authorize actions or accept a repair.

## Start the local service

The persistent checkout is `$HOME/.local/share/trinity-simple-jev`. Its upstream
revision is `0dd5396ffce671ab7c4bfc031506d8e558cf8d23`. The integration includes
the deployment Pixi manifest/lock in `experiments/configs/local_jev/`. These files
are deployed to the upstream checkout root, where `hf-server` exists:

```sh
git clone https://github.com/featherless-ai/simple-jev.git "$HOME/.local/share/trinity-simple-jev"
git -C "$HOME/.local/share/trinity-simple-jev" checkout 0dd5396ffce671ab7c4bfc031506d8e558cf8d23
cp experiments/configs/local_jev/pixi.toml experiments/configs/local_jev/pixi.lock "$HOME/.local/share/trinity-simple-jev/"
pixi run --manifest-path "$HOME/.local/share/trinity-simple-jev/pixi.toml" --frozen serve --revision 2fc06364715b967f1860aea9cf38778875588b17
```

For an existing checkout, run only the last command. Do not start a second
service on an occupied port. Readiness: `curl http://127.0.0.1:8000/health`.
This pins Qwen3.5-0.8B, CUDA float16, an 8192-token window and serial requests.
The prior replay's model checkpoint was not recorded, so identical weights to
that replay are unproven. Full-group requests exceeded the 8 GiB GPU's capacity.

## Review one closed run

Use the existing completion-watchdog capture. Do not query a growing run.
The following commands use shell variables naming its closed directory and a
new output directory. No hosted key is needed.

```sh
pixi run python -m tools.bot_ml.compare_magmaw_timelines --bot-run "$closed_run" --wcl-manifest experiments/configs/cata_raid_encounters/blackwing_descent/magmaw_wcl_cast_timelines_v1.json --output "$review_dir/timeline.json"
pixi run python -m tools.bot_ml.analyze_magmaw_trace --input "$closed_run" --prepare-only --run-id "$run_id" --timeline-comparison "$review_dir/timeline.json" --output "$review_dir/review.json"
pixi run python -m tools.bot_ml.jev_shadow --review "$review_dir/review.json" --identity "$identity_json" --backend-receipt "$backend_json" --output "$review_dir/shadow"
```

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
Local confidence is not calibrated TypeSafe confidence. Evaluate it on held-out
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

Contracts: [TypeSafe API](https://docs.typesafe.ai/api) and
[pinned SimpleJev README](https://github.com/featherless-ai/simple-jev/blob/0dd5396ffce671ab7c4bfc031506d8e558cf8d23/README.md).
