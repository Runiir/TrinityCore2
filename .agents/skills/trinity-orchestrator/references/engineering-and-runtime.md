# Engineering, runtime, build, and retry details

Read this reference only when the work touches native includes, telemetry, runtime
identity/admission, target selection, build ownership, or repeated failures.

## Native and telemetry boundaries

When splitting a translation unit to stay below the 1,000-line limit in AGENTS.md,
preserve prerequisite include order and inspect file-local names in the active
build receipt/cache if unity is enabled. A dormant CMake unity branch and an
extracted-body fixture do not prove the real include chain; in this core
`Pet.h` depends on `Common.h` being available first. Keep native compilation a
separate claim from behavioral fixtures.

For retained telemetry, find both full and delta serializers and send the same native
record through each. A field visible in a full snapshot can disappear after ring
eviction when the delta exporter omits it. Trace observation helpers through their
callees: `CalculateSpellDamage` reaches `ApplySpellMod` and can attach modifiers
to a prepared spell. Diagnostics read nonmutating inputs and label approximations
and omitted modifiers.

When changing decision or sampling frequency, verify the full-size export through
controller retention, parsing, and final acceptance recomputation. Incomplete
transport is an infrastructure failure, not a class-tuning signal; complete
transport does not prove native diagnostic arrays are complete. Check bounded
producers across the full scoring window at the active cadence and retain explicit
attempted/retained/dropped receipts for a repaired loss path. Keep diagnostic-loss
rejection separate from measured DPS/HPS. Run permanent-rejection regressions after
raw evidence eviction, use a small repository-owned fixture for final acceptance,
and keep optional hydrated-payload size checks separate with explicit skips.
Historical regression fixtures stay bound to their original reference and fixture
authority; a new catalog must not relabel old observations or break unrelated replay.

For mixed console JSON, identify the message type before interpreting shared fields.
A diagnostic `bots` array is not a status count. Preserve explicit zero values and
test newer inactive or malformed status after older readiness.

## Runtime identity and admission

Review the complete launch-to-consumer path and every identity used to select the
runtime actor and its inputs. For frozen-checkout admission, exercise the full
preparation caller with default checkout data absent, nested gear loaders included,
and both dry-run and apply paths. Offline reference validation uses frozen authority;
native preparation may use the actual configured, verified `DataDir`. Reproduce
the child process working directory and import roots, not only the outer driver
directory; a fixture-loader-only test does not prove the launch binds its data root.

Bind every check to its observation time. Prepull readiness uses the scoring-start
snapshot; an item consumed during combat does not invalidate that earlier readiness.
Return every known blocking finding together rather than stopping after one identity
field. Exact runtime identity comparison tests the complete emitted dictionary
against the real materialized expectation. Keep provisioning-only fields in their
own authority and distinguish required subsets from complete observed sets. A
fixture that trims expected fields cannot prove the production comparison. Correct
immutable contract identities through a new cohort; never fill missing observations
from expected values.

When adding shared target restrictions, exercise a protected first candidate and a
legal second candidate through each affected pet/totem selector. A final cast
rejection does not replace skipping an ineligible candidate during selection, and an
acquisition helper must not report success when target binding failed.

## Build ownership and resource policy

Serialize heavyweight builds through `queued_build`, shared worldserver ownership,
provisioning, and DVC publication. Check admission with:

```text
pixi run python -m tools.raid_program.queued_build status --compact
```

The compact status is sufficient for deciding whether a build is active; the full
status is historical context. Batch the current work-unit code and independent
review before one coordinator-owned build. Workers do not each launch builds.
New builds default to `cata_raid_build_resource_policy_host12_v1.json`: all 12
logical CPUs, one shared heavyweight lease, and one linker. Load average is only a
diagnostic; memory reserve, PSI, swap growth, and disk space can stop an unsafe
build. If 12 jobs are unsafe, retain that receipt and derive a bounded lower-memory
retry rather than silently restoring the old four-job policy.
If that retry also fails, stop and return the exact build phase and guard samples.

When verifying or reusing a binary, pass the exact policy in its receipt; never
relabel an old build as host12. A new policy requires its own configure lineage.
Do not guess CLI defaults or `-j` syntax. Policy-bound configuration comes from
`queued_build.expected_build_configuration(policy)`, with `-S . -B build` and
the policy's generator. Retain the successful argv and reuse it on resumes. Before
claiming a build, run `workflow_build preflight`; it repeats validation-reference
checks so stale catalogs fail before compilation. Generate receipt paths with
`workflow_build refs <paths...>` and owned-file hashes with
`workflow_build snapshot`, never by hand.

Commit graph/receipt progress before launch. Canonical dummy/shared runners retain
the original build commit and separately record the current coordinator commit when
only recognized coordination files changed. Do not rebuild or stash solely because a
progress commit advanced HEAD. Code, runtime input, tool, reference, and policy
changes require review and a matching build, with clean source. For a new build,
obtain configure lineage for the exact source, include the generator's `-G`, and
derive remaining arguments from the policy helper. Prefer
`pixi run python -m tools.raid_program.workflow_build run` after committing the
reviewed claim; it runs configure and build through the queue without intermediate
Git writes. Inspect argv with `workflow_build commands` without launching.
A failed step returns its receipt and stops; correct the cause before retrying.

Reuse exact verified assets, verify remote copies, and evict only exact duplicate
payloads.

## Retry and reviewer boundaries

Ordinary fixture, configuration, implementation, and review failures are repair
tasks; only a real tool/account/resource failure should require external input.
The graph's ten-failure rule forces a changed hypothesis; it does not stop the
program when a new bounded repair exists.

When replacing or resuming a worker, name the latest implementation review and its
unresolved findings. The worker reconciles those findings with the current diff;
a directory of old reports is not a handoff. Preserve completed repairs and
distinguish missing live acceptance from an implementation defect. For a critical
regression, run its explicit pytest node ID or verify the focused selector actually
collects it; a passing filtered suite that excludes the new test is not evidence.
Do not interrupt a quiet worker arbitrarily; send decisive context and use
`followup_task` to resume a completed worker.

The reviewer is a separate session that read the patch. Model agreement is not
review approval.
