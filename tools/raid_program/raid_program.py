"""Raid-level workloop: ``implement <raid> <mode> bots`` as a data-driven program.

Entry points (all through ``tools.raid_program.raid_workloop``):

    start "implement bwd 10n bots" [--preview]    select or create the raid program
    resume [--program|--boss]                     exact next coordinator action
    program status [--boss KEY]                   compact per-boss table
    program plan|packet|handoff|decide|reopen|fix|refresh-data|review-diff|review|build
    program run-plan|run-batches|run|ingest|assess|e2e

A program holds one unit per boss shard (its seeded-lockout plan, cohort and
owner skill) and one end-to-end unit (the full-raid cohort on the composed
route). It references boss-level scenarios by key and never writes the
boss-level graph. ``raid_workloop`` imports this module only for raid-level
commands. Nothing here launches agents; ``program build`` is the only compiling
step, ``program run-batches`` the only step that starts shard_coordinator (and so a
worldserver), ``program refresh-data`` the only DVC repro/push step, and
``program ingest`` (also run by run-batches) the only evidence-archiving step.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.raid_program import raid_program_batches as batches
from tools.raid_program import raid_program_build as builds
from tools.raid_program import raid_program_data as datas
from tools.raid_program import raid_program_ingest as ingests
from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_review as reviews
from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_runs as runs
from tools.raid_program import raid_program_sanity as sanity
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError
from tools.raid_program.raid_program_next import (  # noqa: F401 - re-exported for callers of this module
    COORDINATOR, NEW_RUN_DIR, WORKLOOP, current as _current, evidence_retry as _evidence_retry, next_step,
    policy as _policy, round_label)
from tools.raid_program.raid_program_request import raid_aliases, resolve_raid_request

RESUME_SCHEMA = 'raid_program_resume_v1'
FINISH_LINE = {
    'boss_unit': ('accepted in a round when its latest shard run is a native clear, its scoreboard verdict passes '
                  '(every non-healer actor at the raid target\'s WCL ratio, native clears, no boss-window deaths) on '
                  'that round\'s binary with archived evidence, and no input is missing; accepted units must pass again '
                  'every round or they reopen'),
    'e2e': ('accepted when one fresh-instance run of the full-raid cohort on the composed route (trash, interactions, '
            'transports) kills every boss node natively on the round binary, with no raid-level input open; seeded '
            'lockouts are diagnostic assistance and never count'),
    'program': 'complete only when resume reports parent_objective_complete (every boss unit and the e2e unit accepted)',
}
RULES = [
    'Only the coordinator commits, builds, provisions, runs servers, archives evidence and records program steps.',
    'A raid-level request authorizes one implementation agent per round packet (user decision 2026-09-25); '
    'no model override; implementer and reviewer are separate sessions.',
    'No edits while a build runs: every agent has handed off before program build.',
    'One build per round through queued_build with the default policy; the job count comes from the policy.',
    'Seeded lockouts are diagnostic assistance and never certify a predecessor kill.',
    'Raid runs use the completion watchdog; there is no raid success timer. Recovered trash deaths are context; '
    'boss-window deaths fail a kill.',
]


def start_request(root: Path, request: str, mode: str | None = None, preview: bool = False,
                  expected_sha256: str | None = None) -> dict | None:
    """Program view for a raid-level request; None when the request is boss-level."""
    target = resolve_raid_request(root, request, mode)
    if target is None:
        return None
    from tools.raid_program.raid_program_inputs import discover_program
    discovery = discover_program(root, target['raid'], target['mode'])
    if preview:
        return {'schema': RESUME_SCHEMA, 'read_only': True, 'requested_program': discovery['program_id'],
                'aliases': raid_aliases(root, target['raid']), 'program': _compact(discovery),
                'next_action': f'{WORKLOOP} start "{request}" selects this program (no server, build or agent).'}
    rounds.select(root, discovery, expected_sha256)
    return resume(root)


def program_focused(root: Path) -> bool:
    """Plain ``resume`` continues the program only after a raid-level start; any doubt keeps the boss graph."""
    try:
        state, _ = store.load(root)
    except (OSError, ValueError):
        return False
    return bool(state) and state.get('focus') == 'program'


def _compact(discovery: dict) -> dict:
    return {'raid': discovery['raid'], 'mode': discovery['mode'], 'name': discovery['name'],
            'raid_inputs': discovery['raid_inputs'], 'excluded_bosses': discovery['excluded_bosses'],
            'units': [{'boss': unit['boss_key'], 'unit_id': unit['unit_id'], 'boss_scenario': unit['boss_scenario'],
                       'cohort_id': unit['cohort_id'], 'lockout': unit['lockout']['seed_boss_argument'],
                       'seedable': unit['lockout']['seedable'], 'ready_to_run': unit['ready_to_run'],
                       'missing_inputs': [item['input'] for item in unit['missing_inputs']]}
                      for unit in discovery['units']],
            'e2e': {key: discovery['e2e'][key] for key in ('scenario_id', 'cohort_id', 'ready_to_run', 'missing_inputs')}}


def _loaded(root: Path) -> tuple[dict, dict, str]:
    state, program, data = rounds.load_active(root)
    return state, program, store.state_sha256(data)


def resume(root: Path) -> dict:
    state, program, sha = _loaded(root)
    discovery = rounds.discover(root, program)
    action, commands = next_step(root, program, discovery, sha)
    changed = [path for path, digest in program['bootstrap_sources'].items() if discovery['sources'].get(path) != digest]
    return {
        'schema': RESUME_SCHEMA, 'state_sha256': sha, 'state_path': store.STATE_PATH.as_posix(),
        'program_id': program['program_id'], 'objective': program['objective'], 'stage': program['stage'],
        'round': program['round'], 'revision': program['revision'],
        'coordinator_skill': 'trinity-orchestrator', 'loop_skill': 'raid-tuning-playbook',
        'shard_skill': 'raid-shard-architecture',
        'next_action': action, 'commands': commands,
        'packets': {key: {'owner_skill': row['owner_skill'], 'handoff': _handoff_state(row['handoff'])}
                    for key, row in (_current(program).get('packets') or {}).items()},
        'status_table': rounds.status_rows(program, discovery),
        'e2e': {'status': program['e2e']['status'], 'ready_to_run': discovery['e2e']['ready_to_run'],
                'scenario_id': discovery['e2e']['scenario_id'],
                'missing_inputs': [item['input'] for item in discovery['e2e']['missing_inputs']],
                'last': (program['e2e']['results'] or [None])[-1]},
        'raid_inputs': [{'input': item['input'], 'owner_skill': item['owner_skill'], 'blocks': item['blocks']}
                        for item in discovery['raid_inputs']],
        'pending_e2e_evidence': [{'round': row['round'], 'outcome': row['outcome'], 'root': row['evidence'].get('root'),
                                  'error': row['evidence'].get('error'), 'retry': _evidence_retry(program, row, root)}
                                 for row in runs._pending(program)],
        'changed_inputs_since_creation': changed,
        'open_user_decisions': [{key: row.get(key) for key in ('id', 'question', 'options', 'recommendation', 'context',
                                                               'packet_id')} for row in reviews.open_decisions(program)],
        'review': _review_state(program),
        'last_sanity': _last_sanity(program),
        'build_policy': _policy(root),
        'finish_line': FINISH_LINE, 'rules': RULES,
        'parent_objective_complete': program['stage'] == 'complete',
        'parked_programs': sorted(key for key in state['programs'] if key != program['program_id']),
        'boss_level_resume': f'{WORKLOOP} resume --boss',
        'execution': ('Parent objective accepted; report its evidence.' if program['stage'] == 'complete' else
                      'Remain the coordinator: execute next_action, then resume and execute the next one. A round, '
                      'a packet handoff or an assessment does not finish the raid; it is finished only when resume '
                      'reports parent_objective_complete. Stop only for an explicit user limit or a demonstrated '
                      'external blocker. This command is read-only.'),
    }


def _review_state(program: dict) -> dict | None:
    holder = _current(program)
    if program['stage'] not in ('review', 'build') and not holder.get('reviews'):
        return None
    latest = reviews.latest_review(holder) if holder else None
    return {'reviews': len(holder.get('reviews') or []),
            'latest': {key: latest.get(key) for key in ('verdict', 'reviewer', 'diff_sha256', 'recorded_utc')}
            if latest else None}


def _last_sanity(program: dict) -> dict | None:
    assessed = next((row for row in reversed(program['rounds']) if row.get('assessment')), None)
    if not assessed:
        return None
    blocked, warned = sanity.assessment_lines(assessed['assessment'])
    return {'round': assessed['round'], 'investigate_before_tuning': blocked, 'warnings': warned}


def _handoff_state(handoff: dict | None) -> str:
    if not handoff:
        return 'pending'
    return 'abandoned' if handoff.get('abandoned') else 'external' if handoff.get('external') else 'recorded'


def status(root: Path, boss: str | None = None) -> dict:
    _, program, sha = _loaded(root)
    discovery = rounds.discover(root, program)
    if boss:
        unit = next((unit for unit in discovery['units'] if unit['boss_key'] == boss), None)
        if unit is None:
            raise GraphError('no boss unit ' + boss + ' in ' + program['program_id'])
        return {'schema': 'raid_program_unit_v1', 'state_sha256': sha, 'unit': unit, 'record': program['units'].get(boss)}
    rows = rounds.status_rows(program, discovery)
    header = 'boss | status | ready | lockout | last | verdict | owner | missing'
    table = [header] + [' | '.join(str(value) for value in (
        row['boss'], row['status'], 'yes' if row['ready_to_run'] else 'no', row['lockout'], row['last'] or '-',
        row['verdict'] or '-', row['owner_skill'] or '-', ','.join(row['missing']) or '-')) for row in rows]
    return {'schema': 'raid_program_status_v1', 'state_sha256': sha, 'program_id': program['program_id'],
            'stage': program['stage'], 'round': program['round'], 'table': table,
            'e2e': {'status': program['e2e']['status'],
                    'missing_inputs': [item['input'] for item in discovery['e2e']['missing_inputs']]},
            'raid_inputs': [item['input'] for item in discovery['raid_inputs']]}


def boss_pointer(root: Path) -> dict | None:
    """One-line pointer for the boss-level resume output when a raid program exists."""
    try:
        state, _ = store.load(root)
        if not state:
            return None
        program = state['programs'][state['active_program']]
        return {'program_id': program['program_id'], 'stage': program['stage'], 'round': program['round'],
                'resume': f'{WORKLOOP} resume --program'}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def packet(root: Path, packet_id: str) -> dict:
    _, program, _ = _loaded(root)
    return packets.worker_packet(root, program, rounds.discover(root, program), packet_id)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog='raid_workloop program', description='Raid-program rounds')
    verbs = result.add_subparsers(dest='verb', required=True)
    status_parser = verbs.add_parser('status', help='Compact per-boss table (read-only)')
    status_parser.add_argument('--boss', help='Full detail of one boss unit')
    packet_parser = verbs.add_parser('packet', help='Worker packet of one round packet (read-only)')
    packet_parser.add_argument('--id', required=True, help='boss:<key>, shards or research')
    packet_parser.add_argument('--output', type=Path)
    plan = verbs.add_parser('plan', help='Freeze this round\'s work packets')
    plan.add_argument('--boss', action='append', help='Limit boss packets to these open bosses (repeatable)')
    handoff = verbs.add_parser('handoff', help='Record one packet handoff')
    handoff.add_argument('--id', required=True)
    handoff.add_argument('--file', type=Path)
    handoff.add_argument('--abandon', metavar='REASON', help='The packet produced nothing this round')
    handoff.add_argument('--external', metavar='REASON', help='The work landed outside the program (name the commits)')
    decide = verbs.add_parser('decide', help='Record the user\'s answer to a needs_user_decision item, verbatim')
    decide.add_argument('--decision-id', required=True)
    decide.add_argument('--answer', required=True, help='The user\'s exact words')
    reopen = verbs.add_parser('reopen', help='Send one packet back to implementation (implement, review or build stage)')
    reopen.add_argument('--id', required=True)
    reopen.add_argument('--reason', required=True)
    fix = verbs.add_parser('fix', help='Record a coordinator fix in the current round (implement, review or build stage)')
    fix.add_argument('--reason', required=True)
    refresh = verbs.add_parser('refresh-data', help='dvc status/repro of the raid stages, chmod 0644, closure rebind, '
                               'dvc push; lists the files to commit')
    review_diff = verbs.add_parser('review-diff', help='Write the round diff (plan commit to working tree, bookkeeping '
                                   'excluded) and print its sha256 (read-only)')
    review_diff.add_argument('--output', type=Path, required=True, help='A file outside the source tree')
    review = verbs.add_parser('review', help='Record one review of the round diff (accept -> build, reject -> review)')
    review.add_argument('--verdict', choices=reviews.VERDICTS)
    review.add_argument('--diff-sha256', help='The sha256 printed by review-diff')
    review.add_argument('--reviewer', help='Who reviewed (a separate session)')
    review.add_argument('--report', type=Path, help='The reviewer\'s report file')
    review.add_argument('--empty-diff', action='store_true', help='Accept a round with no source change (verified)')
    build = verbs.add_parser('build', help='One configure + worldserver build of the committed round')
    build.add_argument('--dry-run', action='store_true')
    build.add_argument('--finish', action='store_true', help='Adopt a completed worldserver ticket; never compiles')
    build.add_argument('--queue-receipt', type=Path, help='With --finish: the exact worldserver_build ticket')
    run_plan = verbs.add_parser('run-plan', help='Write the round\'s shard run plans (or the e2e plan)')
    run_plan.add_argument('--replan', action='store_true', help='Replace plans that have no recorded run')
    run = verbs.add_parser('run', help='Record one shard_run.json, or a batch that produced none')
    run.add_argument('--shard-run', type=Path)
    run.add_argument('--failed-batch', type=int)
    run.add_argument('--reason')
    run_batches = verbs.add_parser('run-batches', help='Run, record and ingest batches until the target bosses have '
                                   'their counted kills (never commits)')
    run_batches.add_argument('--label', required=True)
    run_batches.add_argument('--max-batches', type=int, default=batches.MAX_BATCHES)
    run_batches.add_argument('--wait-seconds', type=int, default=batches.WAIT_SECONDS,
                             help='How long stray pytest fake worldservers are waited out')
    run_batches.add_argument('--batch-timeout-seconds', type=int, default=batches.BATCH_TIMEOUT_SECONDS,
                             help='Emergency cap of one shard_coordinator run (the shard watchdogs end it first)')
    ingest = verbs.add_parser('ingest', help='Archive and record the round\'s kills of bosses with a raid target')
    ingest.add_argument('--label', required=True)
    assess = verbs.add_parser('assess', help='Judge every boss and open the next round or the e2e unit')
    assess.add_argument('--label', help='The round\'s scoreboard label (required when a boss with a target ran)')
    e2e = verbs.add_parser('e2e', help='Record the end-to-end run, or leave the e2e stage with --failed')
    e2e.add_argument('--shard-run', type=Path)
    e2e.add_argument('--failed', metavar='REASON')
    e2e.add_argument('--archive-pending', action='store_true', help='Retry archiving recorded e2e evidence')
    e2e.add_argument('--evidence-lost', metavar='REASON',
                     help='Close e2e evidence whose /tmp root is gone; a lost clear reopens the e2e unit')
    for writer in (plan, handoff, decide, reopen, fix, refresh, review, build, run_plan, run, run_batches, ingest,
                   assess, e2e):
        writer.add_argument('--expect', help='state_sha256 from resume; rejects a stale writer')
    return result


def _assessment_summary(state: dict) -> dict:
    program = rounds.active(state)
    assessed = next(row for row in reversed(program['rounds']) if row.get('assessment'))
    blocked, warned = sanity.assessment_lines(assessed['assessment'])
    return {'round': assessed['round'], 'investigate_before_tuning': blocked, 'sanity_warnings': warned,
            'units': {key: {'status': row['status'], 'not_accepted_because': row['not_accepted_because']}
                      for key, row in assessed['assessment']['units'].items()}}


def command(root: Path, argv: list[str]) -> dict:
    """Dispatch ``raid_workloop program <verb> ...``."""
    args = parser().parse_args(argv)
    expect = getattr(args, 'expect', None)
    verb = args.verb
    if verb == 'status':
        return status(root, args.boss)
    if verb == 'packet':
        result = packet(root, args.id)
        if args.output:
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return result
    if verb == 'review-diff':
        return reviews.review_diff(root, args.output)
    extra: dict = {}
    if verb == 'plan':
        rounds.plan(root, args.boss or None, expect)
    elif verb == 'handoff':
        rounds.record_handoff(root, args.id, args.file, args.abandon, expect, args.external)
    elif verb == 'decide':
        reviews.decide(root, args.decision_id, args.answer, expect)
        extra['decision'] = args.decision_id
    elif verb == 'refresh-data':
        extra['refresh_data'] = datas.refresh_data(root, expect)
    elif verb == 'review':
        reviews.record_review(root, args.verdict, args.diff_sha256, args.reviewer, args.report, expect, args.empty_diff)
        extra['review'] = reviews.latest_review(rounds.current_round(rounds.active(store.load(root)[0])))
    elif verb == 'reopen':
        rounds.reopen_packet(root, args.id, args.reason, expect)
    elif verb == 'fix':
        rounds.record_fix(root, args.reason, expect)
    elif verb == 'build':
        if args.dry_run:
            return builds.build(root, dry_run=True)
        extra['build'] = (builds.finish(root, args.queue_receipt, expect) if args.finish
                          else builds.build(root, expect))
    elif verb == 'run-plan':
        extra = runs.run_plans(root, expect, args.replan)
    elif verb == 'run':
        runs.record_run(root, args.shard_run, expect, args.failed_batch, args.reason)
    elif verb == 'run-batches':
        extra['run_batches'] = batches.run_batches(root, args.label, expect, args.max_batches,
                                                   wait_seconds=args.wait_seconds,
                                                   batch_timeout=args.batch_timeout_seconds)
        extra['exit_status'] = extra['run_batches']['exit_status']
    elif verb == 'ingest':
        extra['ingest'] = ingests.ingest(root, args.label, expect)
        if extra['ingest']['errors']:
            extra['exit_status'] = 1  # raid_workloop exits non-zero; the errors carry their retry commands
    elif verb == 'assess':
        rounds.assess(root, args.label, expect)
        extra['assessment'] = _assessment_summary(store.load(root)[0])
    elif args.archive_pending:
        runs.archive_pending_e2e(root)
    elif args.evidence_lost:
        runs.evidence_lost(root, args.evidence_lost, expect)
    else:
        runs.record_e2e(root, args.shard_run, expect, args.failed)
    if verb == 'e2e' and runs._pending(rounds.active(store.load(root)[0])):
        # The step itself was recorded, but some e2e evidence (this run's or an older one) is still open.
        extra |= {'exit_status': 1, 'exit_reason': 'open_e2e_evidence (see resume.pending_e2e_evidence)'}
    return extra | {'resume': resume(root)} if extra else resume(root)
