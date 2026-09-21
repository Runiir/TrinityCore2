# Compact diagnosis workflow validation

Source changes: `eca979a75a`, `3f1416d98a`, `dcfa000410`.
Scope: retained evidence retrieval and agent instructions. No native behavior,
build, live capture, task-state transition, or raid acceptance changed.

## Use

From the coordinator checkout, run:

```sh
pixi run python -m tools.raid_program.evidence_view task
```

Follow its exact admission and comparison commands. The task resolves assessed
run receipts and archive members by hash, chooses the actual calibration actor,
and identifies the promoted simulator request/result/ComputeStats and catalog root.
It preserves the active stage, claim, and all open requirements. Missing inputs
stay explicit; it does not hydrate data or launch work.

Comparisons automatically reduce large pages and return continuation commands.
`--view-path` drills into a computed comparison; `events` filters existing records;
`select` reads an exact pointer. `inspect --path` lists nested fields without their
values. Every command accepts `--output`. Continuations remove both spellings of
that option so they cannot overwrite the original export.

Read detailed skill references only for a question left unanswered by the compact
results. Do not concatenate many pages or enumerate every field with separate calls.

## Evidence and limits

The three startup skill bodies shrank from 56,884 to 18,916 bytes. Detailed rules
remain in conditional references. Two fresh Luna max diagnosis sessions exercised
retained Balance unit-04/unit-05 evidence against the promoted v4 simulator bundle.
The first exposed reference preloading and an isolated-checkout root mistake.
The second reached the correct setup admission, signed damage ranking, baseline
confounder, and missing native attribution without proposing a speculative repair.

| Measurement | Earlier session to first compaction | Second bounded diagnosis |
| --- | ---: | ---: |
| Rendered tool-output characters | 752,269 | 154,169 |
| Tool responses | 42 | 18 |
| Compactions | 1 | 0 |

This measures tool text, not total model tokens or wall-clock speed; the intervals
are not identical workloads. It does not guarantee that future agents never drift.
The second test still enumerated fields in many calls. The resulting nested
inventory fix was verified afterward: all 65 real bot fields fit in one 8,758-character
response. A third complete fresh-agent test was not performed.

Independent Luna max review approved the tool changes, including the discovered
equals-form export-overwrite fix and the nested inventory addition. Final mainline
validation: 191 passed, 1 failed. The failing
`test_script_readiness_uses_source_tree_identity` also failed before these changes:
recorded hash `0855911a...` differs from native source `df4c8ee5...`. Its receipt
was not relabeled by this workflow patch. Five earlier sparse-worktree failures
were classified; mainline resolved four and retained this pre-existing failure.

Run the focused suites with Pixi:

```sh
pixi run python -m pytest -q tests/test_evidence_view.py tests/test_evidence_paging.py tests/test_evidence_task.py tests/test_evidence_admission.py tests/test_rank_raid_damage_gaps.py tests/test_magmaw_timeline_comparator.py tests/test_development_graph.py tests/test_raid_agent_skill_runtime_bounds.py tests/test_raid_workloop.py
```

Validation outputs, input hashes, review verdicts, transcript-derived measurements,
and exact replay commands are retained through
`artifacts/cata_raid_program/evidence_context_workflow_20260921.tar.gz.dvc`.
Raw native reports and agent transcripts were not duplicated. These are workflow
validation artifacts, not newly accepted raid or policy-training evidence.

Publication: the 13,721-byte archive has DVC MD5
`d1d6b642ca97ceb31604728d95083c73`. `dvc status` and targeted `dvc push` completed;
the remote object was read back and its bytes/hash verified. The exact local
archive and cache object were then evicted.
