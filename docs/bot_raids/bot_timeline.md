# Bot timeline

The canonical capture controller writes `report.timeline.html`,
`report.timeline.json`, and `report.timeline-summary.json` beside its report.
Open the HTML for the actor overview and filter by actor, phase, target or
spell. Inspect the full event details before choosing a repair. The JSON
retains the same causal records for command-line analysis.

Incoming damage is included as `damage_taken`, including callbacks with zero
health damage and nonzero native `raw_amount`. Filter by event kind and the
receiving actor. The incoming overview groups the selected route through death
by actor, source GUID/entry and spell, including damage before the first outgoing
hit. Time/phase/spell filters apply to the event list, not this summary table.
The earliest callback is an observation bound, not a claimed pull-start event.
Incoming shared damage remains health pressure even when excluded from DPS. `summary.incoming_damage` exposes the same groups for workers.
This does not change the DPS/HPS numerator. Use the native raw field's stated
calculation stage before comparing it with an external unmitigated field.
Legacy damage callbacks hardcode absorption to zero, so this view labels it
unavailable. Zero health damage alone does not distinguish avoidance from
absorption. These callbacks are not a complete count of swing attempts.

Instrumented ordinary swings appear as `melee_resolution`. The native melee
table follows the current filters and displays up to 500 matching swings; narrow
the time range to inspect later rows. Its event details retain the weapon roll,
each bonus/armor/outcome stage and loaded attacker inputs. These are resolution
observations, not extra damage. `resolved_damage_amount` precedes `DealDamage`.
Only a damage callback with the explicit `related_event_sequence` and matching
actor/source/target supplies `health_damage`. Missing or conflicting callbacks
stay unknown. `summary.melee_resolutions` reports observation and correlation
counts. Older captures cannot recover these fields from final damage alone.

The HTML embeds the complete model as deterministic gzip/base64 and expands it
inside the browser without a network dependency. Event details are rendered on
expansion. Use a browser with `DecompressionStream` support; loading failures
remain visible. Time inputs apply when committed by moving focus away.
Actor totals describe the full scoring window; the event list and activity
marks follow the selected interval. A phase labelled `unknown` remains unknown,
even when individual targetability observations identify the live body.

To reconstruct the view from retained evidence:

```sh
pixi run python -m tools.raid_program.bot_timeline \
  --raw RUN/raw.jsonl --report RUN/report.json \
  --output RUN/timeline.json --summary RUN/timeline-summary.json \
  --html RUN/timeline.html
```

Report-only reconstruction explicitly lacks the event stream. Legacy trace
policy fields were serialized from export-time state; they cannot establish
historical eligibility or targeting. New entries freeze event, bound and native
selected targets separately, with their own observation times. Cached policy,
binding and movement observations retain their timestamps and freshness flags.
An accepted submission, native finish and landed effect are separate events;
missing cast-instance correlation is never inferred as an exact match.

For an archived normalized capture, avoid writing another large raw/model copy:

```sh
pixi run python -m tools.raid_program.bot_timeline \
  --raw-archive VERIFIED_ARCHIVE.tar.gz --raw-member live-prepared/raw.jsonl \
  --report RUN/report.json --summary RUN/replay-summary.json --html RUN/replay.html
```

This reads the exact regular-file member without unpacking it, hashes its bytes
for the same raw identity, and writes only the requested outputs. HTML still
contains the full model. Keep the original archive/report DVC binding.

The existing trace queue retains up to 4,096 pending entries plus 128 exported
entries per actor. Delta capture drains pending pages, including at termination.
A longer consumer outage can still overflow this bounded queue; that loss is
reported and blocks complete-evidence acceptance. Full interactive trace
commands still show a bounded recent tail. Use the retained delta stream for
failure investigation.

Use five-second full diagnosis with two-second trace capture for the next
development canary. Status/trace transitions request additional bounded
diagnoses. Preserve native combat aggregates, identity/readback receipts and raw
evidence; the timeline does not replace them. Compare actual capture log bytes
per second, trace parser time and server resource receipts with
`tools.raid_program.compare_capture_cost`. Its CPU comparison is observational,
not an isolated measurement of logging cost.

Optimization review uses `tools.raid_program.bot_optimization_acceptance` with
`--baseline`, `--candidate`, `--matched-setup` and `--repair-assertions` JSON
inputs. Setup and repair assertions must be reviewed against their evidence
pointers and bound to the identified summaries. The comparator does not verify
the contents of arbitrary evidence-pointer strings. It independently reports
encounter clear, requested repair and performance. The default five-percent
decline threshold routes diagnosis; it is not a statistical significance test.
Missing evidence produces an inconclusive result. Reduced add damage alone is
not a regression. Keep faster but unmatched historical runs as benchmarks.
Known material declines still require diagnosis when other missing evidence
makes the overall verdict inconclusive. Healing activity and HPS flags require
demand, survival and absorption review before attributing a regression.

Automatic timelines bind the native raw hash and a stable report-source
projection. The final report inventories their file hashes. A full report hash
cannot be embedded before that report exists without creating a hash cycle.
Post-close reconstruction may additionally bind the full report-file hash.
Preserve an already-inventoried HTML when improving its renderer after closure.
Write a separate compact artifact and receipt with renderer revision, original
hash, exact decompressed-model hash, size and generation time. The native run
keeps its original source identity.
