Use pixi for python related stuff.
Use DVC/DVCLive for experiment tracking.
Commit experiment code/configs to git, and checkpoint generated data/artifacts with DVC.
After future experiments, run dvc status and dvc push to keep the remote in sync.

Bot diagnostics: Codex agents can run `make host-world` or `make host-world-botexp-small` to start an attached host `worldserver` with console stdin, then paste commands at the `TC>` prompt. For scripted smoke checks, pipe commands into the binary, e.g. `printf 'botauto diagnose all\nbotauto trace all 20\nserver exit\n' | timeout 90s build/src/server/worldserver/worldserver --config trinity-worldserver-test.conf`; this only proves command/diagnostic responsiveness, not boss completion. An exact 300-second scoring window is reserved for isolated training-dummy DPS calibration. Raid and dungeon validation must use the generated completion-watchdog run plan: poll at the configured heartbeat and terminate on normal clear, monotonic no-progress/semantic stall, repeated decisions, excessive death loops, infrastructure loss, or explicit interruption. A generous emergency wall-clock cap may protect infrastructure, but reaching it is not success and there is no 300-second raid/dungeon success timer. During live autonomy runs, use `.botauto diagnose [selector|all]` for machine-readable bot state and diagnosis, then `.botauto trace [selector] [limit]` to inspect recent repeated decisions/events. `.botauto debug [selector]` remains backward compatible and includes a compact `diagnosis` object.

Try to keep as little data as possible on the disk. offload to dvc as much as possible

Keep C and C++ source and header files below 1,000 lines. Split by concern so small changes invalidate as little of the build cache as practical.
The pre-commit hook checks staged C/C++ sources/headers and rejects 1,000 or more
lines. Enable it with `git config core.hooksPath .githooks`; direct check:
`pixi run python -m tools.raid_program.module_size`. Unchanged oversized legacy
files are not checked by this incremental guard; changing one requires splitting it.

Current user model preference: use `gpt-5.6-luna` with `reasoning_effort: max`
for all delegated roles, including implementation, causal diagnosis, architecture,
coordination and independent review. Keep implementer and reviewer in separate
sessions. Do not silently escalate to Sol/Astra; narrow the task or improve its
evidence when stuck. Jev and Laya are removed from the workflow (2026-09-23): no step calls them; their code stays on disk. Historical receipts retain their
actual model identities; old Sol requirements do not override this preference.
This controls model selection for new agents, not the model of an existing session.

For a broad request such as "implement Magmaw 10N bots", act as the coordinator:
follow `.agents/skills/raid-tuning-playbook/SKILL.md` for the tuning loop and
`.agents/skills/trinity-orchestrator/SKILL.md` for startup, the saved graph and
review. A specialist's bounded patch and handoff do not replace the requested
encounter implementation and live validation. Read these skills from the current
checkout, even if a cached skill points elsewhere.

For boss-bot implementation requests naming an encounter and difficulty, run
`pixi run python -m tools.raid_program.raid_workloop start "<request>"`
on the current mainline coordinator checkout. Example: `start "implement magmaw 25hc bots"`.
This selects or initializes the requested scenario; it does not launch a server.
For continuation without a new encounter/difficulty, use `raid_workloop resume`.
First inspect `git worktree list --porcelain`. Use the checkout holding `master`
and verify it matches the saved graph's `coordinator_worktree`; preserve unrelated
dirty work rather than building an old branch or copying its task state.
The plain request is sufficient on every new tab. The primary agent remains
coordinator; `unit.owner_skill` assigns only the bounded subtask. Execute each
returned step in the same turn; do not require the user to say "continue" again.
Before a final reply, resume and check the parent objective: open requirements
mean continue. Preserve other scenarios and every open actor requirement; missing
research/scripts/runtime assets are implementation work, not permission to borrow
a different difficulty's acceptance. A dirty checkout or stale build configuration
requires source isolation/configuration repair, not a generic completion reply.
Report any earlier failing tests even if a narrower selection later passes; classify
their relevance without silently dropping them. Only stop for the user's requested
boundary, accepted objective, or a specific external blocker that cannot be resolved.
