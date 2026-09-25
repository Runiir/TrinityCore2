"""Raid-level workloop: ``implement <raid> <mode> bots`` as a data-driven program.

Entry points (all through ``tools.raid_program.raid_workloop``):

    start "implement bwd 10n bots" [--preview]    select or create the raid program
    resume [--program|--boss]                     exact next coordinator action
    program status [--boss KEY]                   compact per-boss table
    program plan|packet|handoff|build|run-plan|run|assess|e2e   round transitions

A program holds one unit per boss shard (its seeded-lockout plan, cohort and
owner skill) and one end-to-end unit (the composed full route). It references
boss-level scenarios by key and never writes the boss-level graph, so
``start "implement magmaw 10n bots"`` and plain ``resume`` stay unchanged until
a raid-level ``start`` selects a program. Nothing here launches agents or
servers; ``program build`` is the only compiling step.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError
from tools.raid_program.raid_program_inputs import discover_program
from tools.raid_program.raid_program_request import raid_aliases, resolve_raid_request

WORKLOOP = 'pixi run python -m tools.raid_program.raid_workloop'
RESUME_SCHEMA = 'raid_program_resume_v1'
FINISH_LINE = {
    'boss_unit': ('accepted when its latest shard run in the round is a native clear, its scoreboard verdict passes '
                  '(every non-healer actor at the raid target\'s WCL ratio, native clears, no boss-window deaths) on '
                  'that round\'s build, and no input is missing (research, damage fidelity, native script, target)'),
    'e2e': ('accepted when one fresh-instance run of the composed full route (trash, interactions, transports) kills '
            'every boss node natively; seeded lockouts are diagnostic assistance and never count'),
    'program': 'complete when every boss unit and the e2e unit are accepted',
}
RULES = [
    'Only the coordinator commits, builds, provisions, runs servers and records program steps.',
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
            'e2e': {'scenario_id': discovery['e2e']['scenario_id'], 'ready_to_run': discovery['e2e']['ready_to_run'],
                    'missing_inputs': discovery['e2e']['missing_inputs']}}


def _loaded(root: Path) -> tuple[dict, dict, str]:
    state, data = store.load(root)
    if state is None:
        raise GraphError('no raid program selected; run raid_workloop start "implement <raid> <mode> bots"')
    store.check(root, state)
    return state, rounds.active(state), store.state_sha256(data)


def resume(root: Path) -> dict:
    state, program, sha = _loaded(root)
    discovery = discover_program(root, program['raid'], program['mode'])
    action, commands = next_step(root, program, discovery, sha)
    current = program['rounds'][-1] if program['rounds'] and program['rounds'][-1]['round'] == program['round'] else {}
    changed = [path for path, digest in program['bootstrap_sources'].items()
               if discovery['sources'].get(path) != digest]
    return {
        'schema': RESUME_SCHEMA, 'state_sha256': sha, 'state_path': store.STATE_PATH.as_posix(),
        'program_id': program['program_id'], 'objective': program['objective'], 'stage': program['stage'],
        'round': program['round'], 'revision': program['revision'],
        'coordinator_skill': 'trinity-orchestrator', 'loop_skill': 'raid-tuning-playbook',
        'shard_skill': 'raid-shard-architecture',
        'next_action': action, 'commands': commands,
        'packets': {key: {'owner_skill': row['owner_skill'],
                          'handoff': 'abandoned' if (row['handoff'] or {}).get('abandoned')
                          else 'external' if (row['handoff'] or {}).get('external')
                          else 'recorded' if row['handoff'] else 'pending'}
                    for key, row in (current.get('packets') or {}).items()},
        'status_table': rounds.status_rows(program, discovery),
        'e2e': {'status': program['e2e']['status'], 'ready_to_run': discovery['e2e']['ready_to_run'],
                'missing_inputs': [item['input'] for item in discovery['e2e']['missing_inputs']],
                'last': (program['e2e']['results'] or [None])[-1]},
        'raid_inputs': [item['input'] for item in discovery['raid_inputs']],
        'changed_inputs_since_creation': changed,
        'build_policy': _policy(root),
        'finish_line': FINISH_LINE, 'rules': RULES,
        'parent_objective_complete': program['stage'] == 'complete',
        'parked_programs': sorted(key for key in state['programs'] if key != program['program_id']),
        'boss_level_resume': f'{WORKLOOP} resume --boss',
        'execution': ('Parent objective accepted; report its evidence.' if program['stage'] == 'complete' else
                      'Remain the coordinator: execute next_action, then resume and execute the next one. A round, '
                      'a packet handoff or an assessment does not finish the raid; stop only for an explicit user '
                      'limit or a demonstrated external blocker. This command is read-only.'),
    }


def _policy(root: Path) -> dict:
    try:
        path, policy, _ = rounds.build_policy(root)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        return {'error': str(error)[:200]}
    return {'path': path.as_posix(), 'policy_id': policy.get('policy_id'),
            'maximum_compiler_jobs': policy['parallelism']['maximum_compiler_jobs']}


def next_step(root: Path, program: dict, discovery: dict, sha: str) -> tuple[str, list[str]]:
    stage, number = program['stage'], program['round']
    expect = f'--expect {sha}'
    current = program['rounds'][-1] if program['rounds'] else {}
    if stage == 'plan':
        open_units = [k for k, u in program['units'].items() if u['status'] != 'accepted']
        return (f'Round {number} plan: freeze one work packet per open boss unit ({", ".join(open_units) or "none"}) '
                'plus the shards packet when shard inputs are missing. Then spawn one implementation agent per packet '
                '(no model override), each given its packet JSON; agents edit only owned files and return the handoff '
                'JSON.', [f'{WORKLOOP} program plan {expect}', f'{WORKLOOP} program packet --id <packet_id> '
                          '--output /tmp/<packet_id>.json'])
    if stage == 'implement':
        pending = [key for key, row in current['packets'].items() if not row['handoff']]
        return (f'Round {number} implement: {len(pending)} packets await handoffs ({", ".join(pending)}). Give each '
                'agent its packet; save each final handoff JSON at the packet\'s handoff.save_as path and record it '
                '(or --abandon REASON, or --external REASON naming the commits of work done outside the program). Route patch requests: shard files to the shards packet (or apply them '
                'yourself when there is none), coordinator files yourself. Review class_native and shared_runtime '
                'changes in a separate session per the playbook risk tier.',
                [f'{WORKLOOP} program packet --id {key} --output /tmp/{packets.packet_file(key)}.json' for key in pending]
                + [f'{WORKLOOP} program handoff --id <packet_id> --file <handoff.json> {expect}'])
    if stage == 'build':
        policy = _policy(root)
        return (f'Round {number} build: confirm every agent has stopped (an edit during the build aborts it). Apply '
                'the remaining patch requests; if compositions, scenario rows, profiles or prerequisites changed, '
                'reproduce their DVC stages and rebind the runtime asset closure (raid-shard-architecture); run the '
                'packets\' focused tests and report earlier failures; commit everything including the program state. '
                f"Then build that commit once through queued_build with {policy.get('path')} "
                f"({policy.get('maximum_compiler_jobs')} compiler jobs from the policy). Never build while a "
                'worldserver runs. Commit the recorded build.',
                [f'{WORKLOOP} program build --dry-run', f'{WORKLOOP} program build {expect}'])
    if stage == 'run':
        return _run_step(program, discovery, current, expect)
    if stage == 'e2e':
        e2e = discovery['e2e']
        plans = (current.get('e2e') or {}).get('run_plans') or []
        commands = [f"pixi run python -m tools.raid_program.raid_route_composer --composition {e2e['route_composition']} --check"]
        if not plans:
            commands.append(f'{WORKLOOP} program run-plan {expect}')
        else:
            commands += [f"pixi run python -m tools.raid_program.shard_coordinator --plan {plans[-1]['path']} --dry-run",
                         f"pixi run python -m tools.raid_program.shard_coordinator --plan {plans[-1]['path']} "
                         '--output-dir <new directory outside the repository>',
                         f'{WORKLOOP} program e2e --shard-run <output-dir>/shard_run.json {expect}']
        return ('End-to-end: every boss unit is accepted. Check the composed route, write the e2e run plan (one '
                'fresh-instance shard on the full route, no seeded lockout), run it with shard_coordinator under the '
                'completion watchdog and record it. A failed e2e opens another round.', commands)
    return 'Parent objective accepted: every boss unit and the end-to-end unit passed. Report the evidence.', []


def _run_step(program: dict, discovery: dict, current: dict, expect: str) -> tuple[str, list[str]]:
    slug = program['program_id'].replace(':', '_').lower()
    commit = ((current.get('build') or {}).get('source_commit') or 'build')[:10]
    label = f"{slug}-r{program['round']:02d}-{commit}"
    plans = current.get('run_plans') or []
    if not plans and _plans_written(program):
        return (f"Round {program['round']} run: no shard is ready to run (see status_table missing inputs). "
                'Close the round so the next one plans that work.', [f'{WORKLOOP} program assess {expect}'])
    if not plans:
        ready = [unit['boss_key'] for unit in discovery['units'] if unit['ready_to_run']]
        return (f"Round {program['round']} run: write the shard run plans for every ready shard ({', '.join(ready) or 'none'}); "
                'all ready shards share one worldserver in batches of the coordinator\'s shard capacity.',
                [f'{WORKLOOP} program run-plan {expect}'])
    recorded = {run['batch'] for run in current.get('runs') or []}
    targets = [(unit['boss_key'], unit['raid_target']['scenario'], unit['cohort_id']) for unit in discovery['units']
               if unit['raid_target']['present'] and unit['ready_to_run']]
    commands = []
    for plan in plans:
        commands += [f"pixi run python -m tools.raid_program.shard_coordinator --plan {plan['path']} --dry-run",
                     f"pixi run python -m tools.raid_program.shard_coordinator --plan {plan['path']} --output-dir "
                     f"<new directory outside the repository for batch {plan['batch']}>",
                     f'{WORKLOOP} program run --shard-run <output-dir>/shard_run.json {expect}']
    commands += [f'pixi run python -m tools.raid_program.scoreboard ingest --scenario {scenario} --label {label} '
                 f'--run-dir <output-dir>/shards/{cohort}' for _, scenario, cohort in targets]
    commands.append(f'{WORKLOOP} program assess --label {label} {expect}')
    missing = [plan['batch'] for plan in plans if plan['batch'] not in recorded]
    return (f"Round {program['round']} run: run every batch through shard_coordinator (one worldserver, seeded "
            'lockouts, completion watchdog) and record each shard_run.json'
            + (f" (batches without a run: {missing})" if missing else '')
            + '. Ingest each shard run of a boss with a raid target under one label and repeat the batch until those '
              'bosses reach the target\'s kills_per_measurement counted kills; then assess every boss (verdict where '
              'a target exists, typed stall otherwise).', commands)


def _plans_written(program: dict) -> bool:
    return any(entry['action'] == 'run_plans' and entry.get('round') == program['round']
               for entry in program.get('history') or [])


def status(root: Path, boss: str | None = None) -> dict:
    _, program, sha = _loaded(root)
    discovery = discover_program(root, program['raid'], program['mode'])
    if boss:
        unit = next((unit for unit in discovery['units'] if unit['boss_key'] == boss), None)
        if unit is None:
            raise GraphError('no boss unit ' + boss + ' in ' + program['program_id'])
        return {'schema': 'raid_program_unit_v1', 'state_sha256': sha, 'unit': unit,
                'record': program['units'].get(boss)}
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


def packet(root: Path, packet_id: str) -> dict:
    _, program, _ = _loaded(root)
    return packets.worker_packet(root, program, discover_program(root, program['raid'], program['mode']), packet_id)


def command(root: Path, args) -> dict:
    """Dispatch ``raid_workloop program <verb>``; every writing verb accepts --expect."""
    expect = getattr(args, 'expect', None)
    verb = args.program_command
    if verb == 'status':
        return status(root, args.boss)
    if verb == 'packet':
        result = packet(root, args.id)
        if args.output:
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return result
    if verb == 'plan':
        rounds.plan(root, args.boss or None, expect)
    elif verb == 'handoff':
        rounds.record_handoff(root, args.id, args.file, args.abandon, expect, args.external)
    elif verb == 'build':
        if args.dry_run:
            return rounds.build(root, dry_run=True)
        build = rounds.build(root, expect)
        return {'build': build, 'resume': resume(root)}
    elif verb == 'run-plan':
        return rounds.run_plans(root, expect) | {'resume': resume(root)}
    elif verb == 'run':
        rounds.record_run(root, args.shard_run, expect)
    elif verb == 'assess':
        rounds.assess(root, args.label, expect)
    elif verb == 'e2e':
        rounds.record_e2e(root, args.shard_run, expect)
    else:
        raise GraphError('unknown program command ' + str(verb))
    return resume(root)


def add_parser(subparsers) -> None:
    program = subparsers.add_parser('program', help='Raid-program rounds (after start "implement <raid> <mode> bots")')
    verbs = program.add_subparsers(dest='program_command', required=True)
    status_parser = verbs.add_parser('status', help='Compact per-boss table (read-only)')
    status_parser.add_argument('--boss', help='Full detail of one boss unit')
    packet_parser = verbs.add_parser('packet', help='Worker packet of one round packet (read-only)')
    packet_parser.add_argument('--id', required=True, help='boss:<key> or shards')
    packet_parser.add_argument('--output', type=Path)
    plan = verbs.add_parser('plan', help='Freeze this round\'s work packets')
    plan.add_argument('--boss', action='append', help='Limit packets to these open bosses (repeatable)')
    handoff = verbs.add_parser('handoff', help='Record one packet handoff')
    handoff.add_argument('--id', required=True)
    handoff.add_argument('--file', type=Path)
    handoff.add_argument('--abandon', metavar='REASON', help='The packet produced nothing this round')
    handoff.add_argument('--external', metavar='REASON', help='The packet\'s work landed outside the program (name the commits)')
    build = verbs.add_parser('build', help='One configure + worldserver build of the committed round')
    build.add_argument('--dry-run', action='store_true')
    verbs.add_parser('run-plan', help='Write the round\'s shard run plans (or the e2e plan)')
    run = verbs.add_parser('run', help='Record one shard_coordinator shard_run.json')
    run.add_argument('--shard-run', type=Path, required=True)
    assess = verbs.add_parser('assess', help='Judge every boss and open the next round or the e2e unit')
    assess.add_argument('--label', help='Scoreboard label holding this round\'s ingested kills')
    e2e = verbs.add_parser('e2e', help='Record the end-to-end run')
    e2e.add_argument('--shard-run', type=Path, required=True)
    for parser in (plan, handoff, build, verbs.choices['run-plan'], run, assess, e2e):
        parser.add_argument('--expect', help='state_sha256 from resume; rejects a stale writer')
