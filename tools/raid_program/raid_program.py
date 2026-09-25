"""Raid-level workloop: ``implement <raid> <mode> bots`` as a data-driven program.

Entry points (all through ``tools.raid_program.raid_workloop``):

    start "implement bwd 10n bots" [--preview]    select or create the raid program
    resume [--program|--boss]                     exact next coordinator action
    program status [--boss KEY]                   compact per-boss table
    program plan|packet|handoff|reopen|fix|build|run-plan|run|ingest|assess|e2e

A program holds one unit per boss shard (its seeded-lockout plan, cohort and
owner skill) and one end-to-end unit (the full-raid cohort on the composed
route). It references boss-level scenarios by key and never writes the
boss-level graph. ``raid_workloop`` imports this module only for raid-level
commands. Nothing here launches agents or servers; ``program build`` is the only
compiling step and ``program ingest`` the only DVC-archiving step.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.raid_program import raid_program_build as builds
from tools.raid_program import raid_program_ingest as ingests
from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_runs as runs
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError
from tools.raid_program.raid_program_request import raid_aliases, resolve_raid_request

WORKLOOP = 'pixi run python -m tools.raid_program.raid_workloop'
COORDINATOR = 'pixi run python -m tools.raid_program.shard_coordinator'
RESUME_SCHEMA = 'raid_program_resume_v1'
NEW_RUN_DIR = '<new directory outside the repository>'
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


def _current(program: dict) -> dict:
    return program['rounds'][-1] if program['rounds'] and program['rounds'][-1]['round'] == program['round'] else {}


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
        'changed_inputs_since_creation': changed,
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


def _handoff_state(handoff: dict | None) -> str:
    if not handoff:
        return 'pending'
    return 'abandoned' if handoff.get('abandoned') else 'external' if handoff.get('external') else 'recorded'


def _policy(root: Path) -> dict:
    try:
        path, policy, _ = builds.build_policy(root)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        return {'error': str(error)[:200]}
    return {'path': path.as_posix(), 'policy_id': policy.get('policy_id'),
            'maximum_compiler_jobs': policy['parallelism']['maximum_compiler_jobs']}


def round_label(program: dict) -> str:
    current = _current(program)
    if current.get('label'):
        return current['label']
    commit = ((current.get('build') or {}).get('source_commit') or 'build')[:10]
    return f"{program['program_id'].replace(':', '_').lower()}-r{program['round']:02d}-{commit}"


def next_step(root: Path, program: dict, discovery: dict, sha: str) -> tuple[str, list[str]]:
    stage, number, expect = program['stage'], program['round'], f'--expect {sha}'
    current = _current(program)
    if stage == 'plan':
        open_units = [k for k, u in program['units'].items() if u['status'] != 'accepted']
        raid = [f"{item['input']} ({item['owner_skill']})" for item in discovery['raid_inputs']]
        return (f'Round {number} plan: freeze one work packet per open boss unit ({", ".join(open_units) or "none"}), '
                'the shards packet when shard or e2e inputs are missing, and the research packet for raid-level '
                'research inputs (the script-readiness audit waits until every boss unit is accepted)'
                + (f"; raid-level inputs open: {', '.join(raid)}" if raid else '')
                + '. Then spawn one implementation agent per packet (no model override), each given its packet JSON; '
                  'agents edit only owned files and return the handoff JSON.',
                [f'{WORKLOOP} program plan {expect}',
                 f'{WORKLOOP} program packet --id <packet_id> --output /tmp/<packet_id>.json'])
    if stage == 'implement':
        pending = [key for key, row in current['packets'].items() if not row['handoff']]
        return (f'Round {number} implement: {len(pending)} packets await handoffs ({", ".join(pending)}). Give each '
                'agent its packet; save each final handoff JSON at the packet\'s handoff.save_as path and record it '
                '(or --abandon REASON, or --external REASON naming the commits of work done outside the program). '
                'Route patch requests: shard files to the shards packet, research files to the research packet (or '
                'apply them yourself when there is none), coordinator files yourself. Review class_native and '
                'shared_runtime changes in a separate session per the playbook risk tier.',
                [f'{WORKLOOP} program packet --id {key} --output /tmp/{packets.packet_file(key)}.json' for key in pending]
                + [f'{WORKLOOP} program handoff --id <packet_id> --file <handoff.json> {expect}'])
    if stage == 'build':
        policy = _policy(root)
        return (f'Round {number} build: confirm every agent has stopped (an edit during the build aborts it). Apply '
                'the remaining patch requests; if compositions, scenario rows, profiles or prerequisites changed, '
                'reproduce their DVC stages and rebind the runtime asset closure (raid-shard-architecture); run the '
                'packets\' focused tests and report earlier failures; commit everything including the program state. '
                'The dry run shows the ownership check of every file changed since the plan commit. Then build that '
                f"commit once through queued_build with {policy.get('path')} ({policy.get('maximum_compiler_jobs')} "
                'compiler jobs from the policy). Never build while a worldserver runs. Commit the recorded build. '
                'An interrupted build is adopted with --finish; a packet that must change again is reopened; a '
                'coordinator repair is recorded with program fix.',
                [f'{WORKLOOP} program build --dry-run', f'{WORKLOOP} program build {expect}',
                 f'{WORKLOOP} program build --finish [--queue-receipt <ticket.json>] {expect}',
                 f'{WORKLOOP} program reopen --id <packet_id> --reason <text> {expect}',
                 f'{WORKLOOP} program fix --reason <text> {expect}'])
    if stage == 'run':
        return _run_step(program, discovery, current, expect)
    if stage == 'e2e':
        return _e2e_step(program, discovery, expect)
    return ('Parent objective accepted (parent_objective_complete): every boss unit and the end-to-end unit passed. '
            'Report the evidence.', [])


def _run_step(program: dict, discovery: dict, current: dict, expect: str) -> tuple[str, list[str]]:
    label = round_label(program)
    if not current.get('plans_written'):
        ready = [unit['boss_key'] for unit in discovery['units'] if unit['ready_to_run']]
        return (f"Round {program['round']} run: write the shard run plans for every ready shard ({', '.join(ready) or 'none'}); "
                'all ready shards share one worldserver in batches of the coordinator\'s shard capacity.',
                [f'{WORKLOOP} program run-plan {expect}'])
    plans = current.get('run_plans') or []
    if not plans:
        return (f"Round {program['round']} run: no shard is ready to run (see status_table missing inputs). "
                'Close the round so the next one plans that work.', [f'{WORKLOOP} program assess {expect}'])
    recorded = {run['batch'] for run in current.get('runs') or []}
    commands = []
    for plan in plans:
        output = f"{NEW_RUN_DIR[:-1]} for batch {plan['batch']}>"
        commands += [f"{COORDINATOR} --plan {plan['path']} --output-dir {output} --dry-run",
                     f"{COORDINATOR} --plan {plan['path']} --output-dir {output}",
                     f'{WORKLOOP} program run --shard-run <output-dir>/shard_run.json {expect}',
                     f"{WORKLOOP} program run --failed-batch {plan['batch']} --reason <why no shard_run.json> {expect}"]
    targets = [unit['boss_key'] for unit in discovery['units'] if unit['raid_target']['present'] and unit['ready_to_run']]
    commands += [f'{WORKLOOP} program ingest --label {label} {expect}',
                 f'{WORKLOOP} program assess --label {label} {expect}']
    missing = [plan['batch'] for plan in plans if plan['batch'] not in recorded]
    return (f"Round {program['round']} run: run every batch through shard_coordinator (one worldserver, seeded "
            'lockouts, completion watchdog) into a new output directory and record each shard_run.json, or record a '
            'batch that produced none with --failed-batch'
            + (f" (batches without a run: {missing})" if missing else '')
            + f". Then archive and record the kills of the bosses with a raid target ({', '.join(targets) or 'none'}) "
              f'with program ingest under label {label}; repeat a batch (same plan, new output directory) and ingest '
              'again until those bosses reach their target\'s kills_per_measurement; then assess every boss '
              '(verdict where a target exists, typed stall otherwise), run dvc status and dvc push, and commit.',
            commands)


def _e2e_step(program: dict, discovery: dict, expect: str) -> tuple[str, list[str]]:
    e2e = discovery['e2e']
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
                     f"{COORDINATOR} --plan {plans[-1]['path']} --output-dir {NEW_RUN_DIR}",
                     f'{WORKLOOP} program e2e --shard-run <output-dir>/shard_run.json {expect}']
    commands.append(f'{WORKLOOP} program e2e --failed <why the plan cannot run or produced no shard_run.json> {expect}')
    return (f"End-to-end: every boss unit is accepted. Check the composed route, write the e2e run plan (the full-raid "
            f"cohort {e2e['cohort_id']} on a fresh instance, no seeded lockout), run it with shard_coordinator under "
            'the completion watchdog and record it. A failed or unrunnable e2e opens another round.', commands)


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
    writers = []
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
    reopen = verbs.add_parser('reopen', help='Send one packet back to implementation (implement or build stage)')
    reopen.add_argument('--id', required=True)
    reopen.add_argument('--reason', required=True)
    fix = verbs.add_parser('fix', help='Record a coordinator fix in the current round (implement or build stage)')
    fix.add_argument('--reason', required=True)
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
    ingest = verbs.add_parser('ingest', help='Archive and record the round\'s kills of bosses with a raid target')
    ingest.add_argument('--label', required=True)
    assess = verbs.add_parser('assess', help='Judge every boss and open the next round or the e2e unit')
    assess.add_argument('--label', help='The round\'s scoreboard label (required when a boss with a target ran)')
    e2e = verbs.add_parser('e2e', help='Record the end-to-end run, or leave the e2e stage with --failed')
    e2e.add_argument('--shard-run', type=Path)
    e2e.add_argument('--failed', metavar='REASON')
    for writer in (plan, handoff, reopen, fix, build, run_plan, run, ingest, assess, e2e):
        writer.add_argument('--expect', help='state_sha256 from resume; rejects a stale writer')
    return result


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
    extra: dict = {}
    if verb == 'plan':
        rounds.plan(root, args.boss or None, expect)
    elif verb == 'handoff':
        rounds.record_handoff(root, args.id, args.file, args.abandon, expect, args.external)
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
    elif verb == 'ingest':
        extra['ingest'] = ingests.ingest(root, args.label, expect)
    elif verb == 'assess':
        rounds.assess(root, args.label, expect)
    else:
        runs.record_e2e(root, args.shard_run, expect, args.failed)
    return extra | {'resume': resume(root)} if extra else resume(root)
