# Compare first, query details second

Use `pixi run python -m tools.raid_program.evidence_view --help`. The commands
read retained inputs; they do not start servers, regenerate references, fetch
WCL or grant acceptance. Run them from the mainline checkout. Do not load the
Python implementation merely to use the CLI.

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
pixi run python -m tools.raid_program.evidence_view events report.timeline.json \
  --actor 30001 --spell 2912 --start-ms 40000 --end-ms 60000 --limit 20
pixi run python -m tools.raid_program.evidence_view select report.timeline.json \
  --path /events/123 --limit 10
```

All JSON inputs accept `archive.tar.gz::exact/member.json`; no extraction or
duplicate payload is needed. Hydrate only the named DVC object if absent.
`inspect` returns shape/actors or archive members. `events` supports actor, spell,
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

Stdout is limited to 16,000 characters. Oversized views fail with a narrowing
instruction instead of emitting truncated JSON. Use smaller pages or a deeper
path. Do not respond by dumping the entire report, graph history, tool catalog,
or generated dataset. Search source paths separately from generated artifacts.
Retain full evidence for verification; send the compact comparison and the few
decisive event pages to reviewers and advisory Jev/Laya packets.
