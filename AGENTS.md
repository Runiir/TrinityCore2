Use pixi for python related stuff.
Use DVC/DVCLive for experiment tracking.
Commit experiment code/configs to git, and checkpoint generated data/artifacts with DVC.
After future experiments, run dvc status and dvc push to keep the remote in sync.

Bot diagnostics: Codex agents can run `make host-world` or `make host-world-botexp-small` to start an attached host `worldserver` with console stdin, then paste commands at the `TC>` prompt. For scripted smoke checks, pipe commands into the binary, e.g. `printf 'botauto diagnose all\nbotauto trace all 20\nserver exit\n' | timeout 90s build/src/server/worldserver/worldserver --config trinity-worldserver-test.conf`; this only proves command/diagnostic responsiveness, not boss completion. An exact 300-second scoring window is reserved for isolated training-dummy DPS calibration. Raid and dungeon validation must use the generated completion-watchdog run plan: poll at the configured heartbeat and terminate on normal clear, monotonic no-progress/semantic stall, repeated decisions, excessive death loops, infrastructure loss, or explicit interruption. A generous emergency wall-clock cap may protect infrastructure, but reaching it is not success and there is no 300-second raid/dungeon success timer. During live autonomy runs, use `.botauto diagnose [selector|all]` for machine-readable bot state and diagnosis, then `.botauto trace [selector] [limit]` to inspect recent repeated decisions/events. `.botauto debug [selector]` remains backward compatible and includes a compact `diagnosis` object.

Try to keep as little data as possible on the disk. offload to dvc as much as possible

Keep C and C++ source and header files below 1,000 lines. Split by concern so small changes invalidate as little of the build cache as practical.

For a broad request such as "implement Magmaw 10N bots", act as the coordinator
using `.agents/skills/trinity-orchestrator/SKILL.md` and
`.agents/skills/raid-performance-loop/SKILL.md`. A specialist's bounded patch
and handoff do not replace the requested encounter implementation and live validation.
Read these skills from the current checkout, even if a cached skill points elsewhere.
First inspect `git worktree list --porcelain`. Use the checkout holding `master`
and verify it matches the saved graph's `coordinator_worktree`; preserve unrelated
dirty work rather than building an old branch or copying its task state.

For boss-bot implementation requests naming an encounter and difficulty, run
`pixi run python -m tools.raid_program.raid_workloop start "<request>"`
on the current mainline coordinator checkout. Example: `start "implement magmaw 25hc bots"`.
This selects or initializes the requested scenario; it does not launch a server.
The plain request is sufficient on every new tab: a matching saved scenario is
continued, not restarted or narrowed to its current class/review. The primary
agent remains coordinator; `unit.owner_skill` assigns only the bounded subtask.
After assessment, publication or routing, execute the next returned step in the
same turn. Before a final reply, resume and check the parent objective. Open
requirements mean continue unless the user explicitly limited/stopped the task
or a demonstrated external blocker prevents all remaining authorized work.
Do not require the user to supply a special handoff or say "continue" again.
For continuation without a new encounter/difficulty, use `raid_workloop resume`.
Follow `docs/bot_raids/development_graph.md`. Preserve other scenarios and every
open actor requirement; missing research/scripts/runtime assets are implementation
work, not permission to borrow a different difficulty's acceptance.
Continue from the returned unit through evidence, repair, review, build preparation,
watchdog validation and publication. A dirty checkout or stale build configuration
requires source isolation/configuration repair, not a generic completion reply.
Report any earlier failing tests even if a narrower selection later passes; classify
their relevance without silently dropping them. Only stop for the user's requested
boundary, accepted objective, or a specific external blocker that cannot be resolved.
