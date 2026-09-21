# Optional per-bot improvement advice

Jev/Laya suggest where to investigate. They never gate a commit, build, experiment,
graph transition, or acceptance. Keep the 95% WoWSims requirement, exact dummy
window, encounter completion, independent review and deterministic checks intact.
Broad "implement this boss" approvals are not DPS diagnostics.

Start with the existing comparison, not another raw-log packet:

```sh
pixi run python -m tools.raid_program.evidence_view compare --current RUN --wowsims RESULT --actor GUID --output comparison.json
pixi run python -m tools.raid_program.bot_improvement_advice --comparison comparison.json --actor GUID --top 2 --output advice --backend both
```

`--baseline RUN` and `--wcl REFERENCE` comparisons work too. Use the full
`--output` artifact, not a paginated stdout overview. No extra live run or
simulator regeneration is required. `--prepare-only` writes inspectable packets
without network calls. Source hashes and full input are retained outside model
state. Paths can point to existing archive members through `evidence_view`.

Each request contains one actor and one component, with reference/context checks,
activity, duty, unknowns and the residual. The model chooses a next investigation
from explicit options. The tool translates that choice into a concrete inspection
step and retains the original probabilities, response and request separately.
No score proves a defect or recoverable DPS. All roles may receive damage advice;
this does not replace healer/tank role and safety evidence.

The reviewer checks the suggestion against the comparison and, when needed, an
actor/spell/time-filtered `evidence_view events` slice. Missing candidate eligibility
cannot prove wrong priority. Different target counts or tank damage intake cannot
establish single-target parity. Duty overlap does not make every idle second
necessary. DoTs, pets and triggered copies are not ordinary player casts.

Use one pass on the largest gaps. Do not wait for agreement, invent an approval
receipt, or repeat an unchanged request. Provider failure/disagreement leaves the
coordinator free to continue from deterministic evidence. A byte-budget preflight
avoids oversized packets; it is not a tokenizer guarantee. It preserves and skips
oversized requests instead of truncating evidence. A local 422 means not reviewed.
Both providers receive the same state; no model call automatically starts a run.

Pre-commit now runs deterministic checks only. Legacy scope/claim advice remains
available explicitly through `worker_precommit --model-advice` or
`worker_checkpoint`, but is not a required plan/result stage.

Evaluate usefulness on separately labeled cases. Keep expected labels outside
model state. Report errors, abstentions and false alarms per provider, including
cases the provider could not review. Synthetic smoke cases test the interface;
they are not real-run validation or training data. Only independently adjudicated,
attributable real cases can establish diagnostic value. Remove advice from paths
where it does not improve decisions or reviewer time.
