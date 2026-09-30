"""The exact next coordinator action of a raid program, per stage (``resume.next_action`` and ``commands``).

Every step names a tracker command, so a coordinator never needs a /tmp
script: ``refresh-data`` for raid DVC data, ``review-diff``/``review`` for the
round review, ``decide`` for user decisions, ``run-batches`` for the run loop,
and ``assess`` (with its run-sanity findings). Open user decisions come first:
``next_action`` then starts with ASK THE USER.
"""
from __future__ import annotations

from pathlib import Path

from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_review as review
from tools.raid_program import raid_program_runs as runs
from tools.raid_program import raid_program_sanity as sanity

WORKLOOP = 'pixi run python -m tools.raid_program.raid_workloop'
COORDINATOR = 'pixi run python -m tools.raid_program.shard_coordinator'
# experiments.archive_run_evidence archives (and deletes) only /tmp paths, so shard runs are written there.
NEW_RUN_DIR = '/tmp/<new run directory>'


def current(program: dict) -> dict:
    return program['rounds'][-1] if program['rounds'] and program['rounds'][-1]['round'] == program['round'] else {}


def slug(program: dict) -> str:
    return program['program_id'].replace(':', '_').lower()


def round_label(program: dict) -> str:
    holder = current(program)
    if holder.get('label'):
        return holder['label']
    commit = ((holder.get('build') or {}).get('source_commit') or 'build')[:10]
    return f"{slug(program)}-r{program['round']:02d}-{commit}"


def policy(root: Path) -> dict:
    from tools.raid_program import raid_program_build as builds
    try:
        path, rules, _ = builds.build_policy(root)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        return {'error': str(error)[:200]}
    return {'path': path.as_posix(), 'policy_id': rules.get('policy_id'),
            'maximum_compiler_jobs': rules['parallelism']['maximum_compiler_jobs']}


def evidence_retry(program: dict, row: dict, root: Path) -> str:
    """--archive-pending while the evidence is archivable (root holds the run, or a completed archive), else --evidence-lost."""
    if runs.evidence_gone(root, program['program_id'], row):
        return f'{WORKLOOP} program e2e --evidence-lost <reason>'
    return f'{WORKLOOP} program e2e --archive-pending'


def next_step(root: Path, program: dict, discovery: dict, sha: str) -> tuple[str, list[str]]:
    action, commands = _stage_step(root, program, discovery, sha)
    asks = review.open_decisions(program)
    if not asks:
        return action, commands
    decide = [f'{WORKLOOP} program decide --decision-id {row["id"]} --answer "<the user\'s exact words>" --expect {sha}'
              for row in asks]
    return ('ASK THE USER: packet agents need decisions only the user can make. Ask each question below as written '
            '(with its options and recommendation), wait for the answer, and record the user\'s exact words with '
            'program decide. Do not answer them yourself. The build is blocked until every decision is answered. '
            + review.decision_prompt(asks) + ' Meanwhile: ' + action, decide + commands)


def _stage_step(root: Path, program: dict, discovery: dict, sha: str) -> tuple[str, list[str]]:
    stage, number, expect = program['stage'], program['round'], f'--expect {sha}'
    holder = current(program)
    if stage == 'plan':
        return _plan_step(program, discovery, expect)
    if stage == 'implement':
        pending = [key for key, row in holder['packets'].items() if not row['handoff']]
        return (f'Round {number} implement: {len(pending)} packets await handoffs ({", ".join(pending)}). Give each '
                'agent its packet; save each final handoff JSON at the packet\'s handoff.save_as path and record it '
                '(or --abandon REASON, or --external REASON naming the commits of work done outside the program). A '
                'handoff may carry needs_user_decision items: resume then says ASK THE USER. Route patch requests: '
                'shard files to the shards packet, research files to the research packet (or apply them yourself when '
                'there is none), coordinator files yourself. When every packet has handed off, the round moves to '
                'review.',
                [f'{WORKLOOP} program packet --id {key} --output /tmp/{packets.packet_file(key)}.json' for key in pending]
                + [f'{WORKLOOP} program handoff --id <packet_id> --file <handoff.json> {expect}'])
    if stage == 'review':
        return _review_step(program, holder, expect)
    if stage == 'build':
        rules = policy(root)
        latest = review.latest_review(holder) or {}
        return (f'Round {number} build: the accepted review ({latest.get("reviewer")}) covers round diff '
                f'{str(latest.get("diff_sha256"))[:12]}. Confirm every agent has stopped (an edit during the build '
                'aborts it). program build --dry-run shows the argv, the ownership check of every file changed since '
                'the plan commit, and the gates (user decisions answered, an accepted review of exactly the committed '
                'round diff, current raid DVC data); a failing gate names its fix (a source commit after the review '
                'needs review-diff and review again; stale data needs refresh-data). Then build that commit once '
                f"through queued_build with {rules.get('path')} ({rules.get('maximum_compiler_jobs')} compiler jobs "
                'from the policy). Never build while a worldserver runs. Commit the recorded build. An interrupted '
                'build is adopted with --finish (the same gates, current raid data included, must pass for the ticket\'s '
                'commit; refreshed data needs a new build); a packet that must change again is reopened; a coordinator repair is '
                'recorded with program fix.',
                [f'{WORKLOOP} program build --dry-run', f'{WORKLOOP} program build {expect}',
                 f'{WORKLOOP} program build --finish [--queue-receipt <ticket.json>] {expect}',
                 f'{WORKLOOP} program refresh-data {expect}',
                 f'{WORKLOOP} program reopen --id <packet_id> --reason <text> {expect}',
                 f'{WORKLOOP} program fix --reason <text> {expect}'])
    if stage == 'run':
        return _run_step(root, program, discovery, holder, expect)
    if stage == 'e2e':
        return _e2e_step(root, program, discovery, expect)
    older = runs._pending(program)
    if older:
        return ('Parent objective accepted (parent_objective_complete): every boss unit and the end-to-end unit passed. '
                f'{len(older)} older e2e evidence archive(s) are still open (see pending_e2e_evidence); archive or close '
                'them, then report the evidence.',
                sorted({evidence_retry(program, row, root) for row in older}))
    return ('Parent objective accepted (parent_objective_complete): every boss unit and the end-to-end unit passed. '
            'Report the evidence.', [])


def _plan_step(program: dict, discovery: dict, expect: str) -> tuple[str, list[str]]:
    number = program['round']
    open_units = [k for k, u in program['units'].items() if u['status'] != 'accepted']
    raid = [f"{item['input']} ({item['owner_skill']})" for item in discovery['raid_inputs']]
    previous = program['rounds'][-1] if program['rounds'] else {}
    blocked, warned = sanity.assessment_lines(previous.get('assessment'))
    findings = ''
    if blocked:
        findings += (f" Investigate before tuning: the round {previous['round']} run-sanity checks flagged "
                     'measurements that cannot be trusted; the boss packets carry them, and no DPS tuning happens '
                     'until each is explained or fixed: ' + '; '.join(blocked) + '.')
    if warned:
        findings += ' Sanity warnings (read, not blocking): ' + '; '.join(warned) + '.'
    return (f'Round {number} plan: freeze one work packet per open boss unit ({", ".join(open_units) or "none"}), '
            'the shards packet when shard or e2e inputs are missing, and the research packet for raid-level '
            'research inputs (the script-readiness audit waits until every boss unit is accepted)'
            + (f"; raid-level inputs open: {', '.join(raid)}" if raid else '') + '.' + findings
            + ' Then spawn one implementation agent per packet (no model override), each given its packet JSON; '
              'agents edit only owned files and return the handoff JSON.',
            [f'{WORKLOOP} program plan {expect}',
             f'{WORKLOOP} program packet --id <packet_id> --output /tmp/<packet_id>.json'])


def _review_step(program: dict, holder: dict, expect: str) -> tuple[str, list[str]]:
    number = program['round']
    reviews = holder.get('reviews') or []
    report = f"{packets.handoff_directory(program)}/review_{len(reviews) + 1}.md"
    diff = f"~/.cache/{slug(program)}-r{number:02d}-review{len(reviews) + 1}.diff"
    record = [f'{WORKLOOP} program review-diff --output {diff}',
              f'{WORKLOOP} program review --verdict accept|reject --diff-sha256 <sha256 from review-diff> '
              f'--reviewer <reviewer> --report {report} {expect}']
    route = [f'{WORKLOOP} program reopen --id <packet_id> --reason "<review finding>" {expect}',
             f'{WORKLOOP} program fix --reason "<coordinator repair>" {expect}']
    latest = reviews[-1] if reviews else None
    if latest and latest['verdict'] == 'reject':
        return (f"Round {number} review: the last review ({latest['reviewer']}, {latest['recorded_utc']}, report "
                f"{(latest.get('report') or {}).get('path')}) rejected the round. Route each finding to its owner: a "
                'file a packet owns goes back to that packet with program reopen (its agent fixes it and hands off '
                'again; the round returns here); a coordinator file you fix yourself and record with program fix. '
                'Commit, then write a new review diff and have it re-reviewed in a separate session; check the fixes '
                'for new regressions, not only the findings.', route + record)
    return (f'Round {number} review: every packet has handed off. 1) Apply the remaining patch requests yourself '
            '(shard, research and coordinator files). 2) If shard data changed (compositions, scenario rows, profiles, '
            'prerequisites, dvc.yaml), run program refresh-data: it reproduces the stale raid DVC stages, sets file '
            'modes, rebinds the runtime asset closure, pushes, and lists the files to commit. 3) Run every packet\'s '
            'focused tests and report every failure, earlier ones included (compare with the known-failure baseline: '
            'pixi run python -m tools.raid_program.test_baseline check <tests>). 4) Commit everything including the '
            'program state (the review sha256 is the same before and after the commit). 5) program review-diff '
            'writes the round diff (plan commit to working tree, untracked files included, program bookkeeping '
            'excluded) and prints its sha256. 6) A reviewer in a separate session reviews that file per the playbook '
            f'risk tier; save the report at {report}. 7) Record the verdict with program review: accept moves to '
            'build, reject stays here with routing guidance. A round with no source change is closed with program '
            'review --empty-diff.',
            [f'{WORKLOOP} program refresh-data {expect}'] + record
            + [f'{WORKLOOP} program review --empty-diff {expect}', f'{WORKLOOP} program build --dry-run'] + route)


def _run_step(root: Path, program: dict, discovery: dict, holder: dict, expect: str) -> tuple[str, list[str]]:
    label = round_label(program)
    if not holder.get('plans_written'):
        ready = [unit['boss_key'] for unit in discovery['units'] if unit['ready_to_run']]
        return (f"Round {program['round']} run: write the shard run plans for every ready shard ({', '.join(ready) or 'none'}); "
                'all ready shards share one worldserver in batches of the coordinator\'s shard capacity.',
                [f'{WORKLOOP} program run-plan {expect}'])
    plans = holder.get('run_plans') or []
    if not plans:
        return (f"Round {program['round']} run: no shard is ready to run (see status_table missing inputs). "
                'Close the round so the next one plans that work.', [f'{WORKLOOP} program assess {expect}'])
    recorded = {run['batch'] for run in holder.get('runs') or []}
    missing = [plan['batch'] for plan in plans if plan['batch'] not in recorded]
    targets = [unit['boss_key'] for unit in discovery['units'] if unit['raid_target']['present'] and unit['ready_to_run']]
    commands = [f'{WORKLOOP} program run-batches --label {label} {expect}',
                f'{WORKLOOP} program assess --label {label} --expect <state_sha256 after committing run-batches>']
    for plan in plans:  # manual fallback for one batch, the steps run-batches automates
        output = f"/tmp/{label}-b{plan['batch']}-<utc stamp>"
        commands += [f"{COORDINATOR} --plan {plan['path']} --output-dir {output} --dry-run",
                     f"{COORDINATOR} --plan {plan['path']} --output-dir {output} --gdb-backtrace",
                     f'{WORKLOOP} program run --shard-run {output}/shard_run.json {expect}',
                     f"{WORKLOOP} program run --failed-batch {plan['batch']} --reason <why no shard_run.json> {expect}"]
    commands.append(f'{WORKLOOP} program ingest --label {label} {expect}')
    try:
        from tools.raid_program.raid_program_batches import kill_summary
        counted = kill_summary(root, program)
    except (ValueError, KeyError, OSError, TypeError):  # informational only; run-batches counts again itself
        counted = None
    return (f"Round {program['round']} run: program run-batches --label {label} runs the whole round loop: it waits "
            'out stray pytest fake worldservers (a real worldserver refuses the run), checks /tmp headroom, runs each '
            'planned batch through shard_coordinator --gdb-backtrace (one worldserver, seeded lockouts, completion '
            'watchdog) into /tmp, records its shard_run.json (or the failed batch), ingests the kills (archived to DVC), '
            f"and repeats until every boss with a raid target ({', '.join(targets) or 'none'}) has its target's "
            'kills_per_measurement counted kills; it stops early after --max-batches (default 5) or when a batch adds '
            'no counted kill, and its stopped/next_action fields say what to do. When the target bosses already '
            'have their kills it runs nothing and reports targets_met. Ctrl-C or SIGTERM stops the running batch: its '
            'shard_coordinator group and its worldserver/gdb are stopped and verified gone before it exits.'
            + (f' Batches without a run: {missing}.' if missing else '')
            + (f' Counted kills under {label} so far: {counted}.' if counted else '')
            + ' It does not commit: commit the files it lists. Then program assess --label '
            f'{label} judges every boss (verdict where a target exists, typed stall otherwise; its run-sanity '
            'checks keep a boss open on any blocking finding); run dvc status and commit. The remaining commands are '
            'the manual fallback for a single batch.', commands)


def _e2e_step(root: Path, program: dict, discovery: dict, expect: str) -> tuple[str, list[str]]:
    e2e = discovery['e2e']
    awaiting = runs.awaiting_evidence(program)
    if awaiting:
        error = (awaiting.get('evidence') or {}).get('error')
        if evidence_retry(program, awaiting, root).endswith('--archive-pending'):
            failing = (awaiting.get('evidence') or {}).get('state') == 'failed'
            return ('End-to-end: the clear is recorded but its evidence is not archived yet'
                    + (f' (last error: {error})' if error else '') + '. The unit is accepted, and the program '
                    'completes, only once the pointer is stored; retry the archive from the kept /tmp run root.'
                    + (' If the archive keeps failing (for example DVC is unreachable), abandon this attempt with '
                       'program e2e --failed REASON; the next round re-runs the full route and the kept evidence '
                       'can still be archived later.' if failing else ''),
                    [f'{WORKLOOP} program e2e --archive-pending']
                    + ([f'{WORKLOOP} program e2e --failed <reason> {expect}'] if failing else []))
        return ('End-to-end: the clear\'s /tmp run root is gone and no completed archive exists, so its evidence is '
                'lost. Record that; the unit reopens and the next round re-runs the full route.',
                [f'{WORKLOOP} program e2e --evidence-lost <reason> {expect}'])
    if not e2e['ready_to_run'] or discovery['raid_inputs']:
        blockers = [item['input'] for item in e2e['missing_inputs'] + discovery['raid_inputs']]
        return ('End-to-end: the unit cannot run (' + ', '.join(blockers) + '). Leave the e2e stage so the next round '
                'plans that work.', [f'{WORKLOOP} program e2e --failed "missing inputs: {", ".join(blockers)}" {expect}'])
    plans = (runs.e2e_round(program) if program['rounds'] else {}).get('run_plans') or []
    commands = [f"pixi run python -m tools.raid_program.raid_route_composer --composition {e2e['route_composition']} --check"]
    if not plans:
        commands.append(f'{WORKLOOP} program run-plan {expect}')
    else:
        commands += [f"{COORDINATOR} --plan {plans[-1]['path']} --output-dir {NEW_RUN_DIR} --dry-run",
                     f"{COORDINATOR} --plan {plans[-1]['path']} --output-dir {NEW_RUN_DIR} --gdb-backtrace",
                     f'{WORKLOOP} program e2e --shard-run <output-dir>/shard_run.json {expect}']
    commands.append(f'{WORKLOOP} program e2e --failed <why the plan cannot run or produced no shard_run.json> {expect}')
    return (f"End-to-end: every boss unit is accepted. Check the composed route, write the e2e run plan (the full-raid "
            f"cohort {e2e['cohort_id']} on a fresh instance, no seeded lockout), run it with shard_coordinator under "
            'the completion watchdog into a new /tmp directory and record it. A failed or unrunnable e2e opens another '
            'round.', commands)
