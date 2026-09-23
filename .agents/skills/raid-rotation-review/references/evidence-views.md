# Compare first, query details second

Use `pixi run python -m tools.raid_program.evidence_view --help`. The commands
read retained inputs; they do not start servers, regenerate references, fetch
WCL or grant acceptance. Run them from the mainline checkout. Do not load the
Python implementation merely to use the CLI.

For a saved task, start with `pixi run python -m tools.raid_program.evidence_view task --max-chars 6000`.
It returns the validated active objective, unit, claim/blocker, evidence references,
open requirement IDs and exact next inspection command. It does not change the stage.
Use `task --section unit` for the complete constraints, `--section receipts` for
bound operation inputs, and `--section requirements` for actor requirements.
For a retained DPS comparison, explicitly request `task --section references`.
That resolves the latest assessed run/baseline by hash and supplies commands using
the promoted request/result/ComputeStats. Check the retained unit against the
current unit. Missing hydration or identity returns a specific error, never a
replacement file. Execute the admission command before interpreting raw stat deltas.
The joined existing gates distinguish favorable self-provided baseline stats from
controlled parity. Passing setup admission does not prove spell tuning or cadence.

## Comparisons

```sh
pixi run python -m tools.raid_program.evidence_view compare \
  --current report.json --baseline earlier-report.json --actor 30540
pixi run python -m tools.raid_program.evidence_view compare \
  --current report.json --wowsims exact-result-or-review.json --actor 30540
pixi run python -m tools.raid_program.evidence_view compare \
  --current report.timeline.json --wcl reviewed-component-references.json
```

Native inputs are completed calibration reports or existing `bot_timeline` JSON.
Use the existing timeline producer for raw raid captures. Compare complete windows;
do not substitute active time for elapsed time. Different actor GUIDs require
`--baseline-actor`; multi-actor overviews match only exact GUIDs and list unmatched
actors. Select `--actor` for spell/setup detail. Overview pages default to ten
actors, with `next_offset`; use `--offset` to continue.
Known native spec, role or mode mismatches are marked `incompatible_context`.
Missing identity checks stay explicit; equal GUIDs do not establish matching setup.
Different epochs/cohorts are recorded as run differences, as expected for separate runs.

WoWSims inputs accept the exact aggregate result, normalized result, or existing
rotation review. Select `--player-index` for a raw multi-player simulator result.
Use the promoted request/result binding, not the newest file by timestamp. Existing
review gates stay visible; a raw aggregate lacks setup admission. A summary does
not replace the full request/ComputeStats/native join required for tuning.

WCL accepts existing reviewed actor/component references used by
`rank_raid_damage_gaps`, the retained WCL DPS catalog (select `--reference-id`),
or a retained cast manifest. Select `--reference-actor` when same-spec mapping is
ambiguous. For example, use the tracked catalogs under
`experiments/configs/cata_raid_encounters/<raid>/`. A total-only reference leaves
the whole gap unattributed. Casts alone never establish per-spell damage.
Component/duty references require the existing full native timeline; its producer
owns hostile damage and mirrored-callback accounting.

The signed gap is reference minus current. Positive losses, native gains and
the numeric residual reconcile to the total. Missing buckets are unknown, not
zero. DTR-tagged simulator copies, other tags and pet casts stay separate from
ordinary action counts. Literal spell IDs are only a first alignment; aliases,
per-target casts and periodic/direct splits still require producer evidence.
Apparent DPS differences are not estimates of recoverable DPS or causal proof.

Default output includes eight ranked components. Use `--top` to change that,
or `--output /tmp/comparison.json` to retain the full comparison while keeping
stdout compact. Omitted component counts and signed sums remain explicit.

## Focused evidence

```sh
pixi run python -m tools.raid_program.evidence_view inspect capture.tar.gz
pixi run python -m tools.raid_program.evidence_view inspect 'capture.tar.gz::run/spec/report.json'
pixi run python -m tools.raid_program.evidence_view inspect report.json \
  --path /combat_calibration/bots/0 --limit 100
pixi run python -m tools.raid_program.evidence_view events report.timeline.json \
  --actor 30001 --spell 2912 --start-ms 40000 --end-ms 60000 --limit 20
pixi run python -m tools.raid_program.evidence_view select report.timeline.json \
  --path /events/123 --limit 10
```

All JSON inputs accept `archive.tar.gz::exact/member.json`; no extraction or
duplicate payload is needed. Hydrate only the named DVC object if absent.
`inspect` returns shape/actors or archive members.
Use `inspect --path` to discover a nested object's field names, types, sizes and
locators. Do not enumerate its keys by running `select` once per offset, or read
all nested payloads just to find which observation fields exist.
`events` supports actor, spell,
target, kind, phase and time filters on existing timeline/decision records.
The default clock is relative to the native scoring/pull edge, or simulator
iteration time; use `--clock absolute` explicitly when needed.

Pages preserve source order and include original JSON Pointer locators, correlation
IDs, source hash, missing observations and `next_offset`. Target filters match any
explicit selected/bound/offensive/effect target while retaining those distinctions.
Missing phase/time observations are counted when excluded by filters, not invented.
Use `select --path <locator>` for omitted candidate/state details, then a deeper
pointer when necessary. Arrays and objects paginate. Read the interval before a
failure as well as after it. Absence in a filtered or incomplete capture is not
proof that an action never occurred.

Stdout defaults to 12,000 characters (`--max-chars`, 2,000..16,000). Large results
automatically shrink their page and return a `next_command`. A single oversized
item becomes an explicit structural view with detail pointers. Comparisons support
`--view-path /pairs/0/components` (or other full-result pointers) for omitted fields.
Every command accepts `--output`: compare/admission export the full computed review;
select/events export the requested page, not an unbounded raw report. Follow the
returned command or pointer; do not respond by dumping the entire report, graph history, tool catalog,
or generated dataset. Search source paths separately from generated artifacts.
Retain full evidence for verification; send the compact comparison and the few
decisive event pages to reviewers and optional Jev/Laya packets.

## Tool-call examples

Choose the question before the command. These are alternatives, not a checklist
to execute on every run. Replace example paths/IDs with the saved task's exact
inputs. For routine inspection use `--max-chars 6000` and approximately 2,000 tool
output tokens. Save full results with `--output` when needed. A truncated response
is an incomplete observation: follow a detail pointer or narrow fields/time/actor,
not a larger dump. Do not concatenate pages to evade the output budget.

### Did a role repair work, and why did acceptance fail?

For a completed healer/tank report, use the result command. It reports native
outcome, failed role checks, scalar metrics and reference eligibility separately.
`REPORT` must name the exact bound report; archive-member inputs also work.

```sh
REPORT=/absolute/path/to/report.json
pixi run python -m tools.raid_program.evidence_view result "$REPORT" --max-chars 6000
```

This is not an actor assessment or automatic repair acceptance. Missing fields
stay null, not zero or success. The output binds the source hash and gives a
`reference_detail_command` for exact reference failures. To inspect that question:

```sh
pixi run python -m tools.raid_program.evidence_view result \
  'capture.tar.gz::run/report.json' \
  --section reference --max-chars 6000
```

If checks are omitted, follow the returned pointer. For example, inspect a failed
dispel metric directly instead of recursively searching all native snapshots:

```sh
pixi run python -m tools.raid_program.evidence_view select "$REPORT" \
  --path /role_calibration_record/metrics/dispel_success_ratio --max-chars 6000
```

If the schema is unknown, use `inspect --path /role_calibration_record/metrics`
once, then select the relevant field. Do not page every field just to be thorough.
A passing repair metric plus `reference_conditions_not_comparable` means the
observed repair and reference eligibility need separate conclusions. Inspect the
named reference failure; do not rerun unchanged gameplay hoping it clears. A ratio
alone does not prove opportunities, sufficient coverage, attribution or acceptance.

An over-budget result exits nonzero with `query_exceeds_output_budget` and the
required selectors. A task never reports success by replacing required fields with
their names. Fix the query or malformed input; do not bypass the failure with a
raw dump. Existing event/selection pages identify every omitted item's locator.

### Keep live output out of the prompt

Preserve the exact generated launch command and append stdout/stderr redirection
to an attempt-specific launcher log outside any run directory required to be new
or empty. Do not pipe the controller through `head`, hide its exit code, or change
the watchdog. Poll the existing process at the configured heartbeat with a small
output budget. Inspect the final report using the projection above; a controller's
large final JSON is an artifact, not a progress message. Keep launcher logs with
the existing run publication, then evict them through the normal lifecycle.

### Find one source condition or one log error

```sh
rg -n -C 3 'DispelCleanse|min_injured_players' \
  src/server/game/Bots/BotClassSpecActionProfileCandidates.cpp
rg -n -m 10 --max-columns 240 --max-columns-preview \
  'ERROR|Traceback|runtime_asset_closure_incomplete' /absolute/attempt.launcher.log
```

The source predicate is illustrative; use the assigned edge's file and symbol.
Log excerpts locate an error, not complete causal evidence. Follow its exact file
or JSON pointer when more context is needed. Search source under `src/`, `tools/`
or `tests/`; search generated evidence only in the exact run/artifact. Avoid
`rg ... artifacts/ | head`, `sed -n '1,80p' *.jsonl`, `jq '.'`, printing
`raw_runtime_status`, and recursive JSON walkers that print every match. One JSONL
line or nested object can contain an entire run. Batch independent small checks,
but keep dependent diagnosis queries sequential so the first answer narrows the next.
