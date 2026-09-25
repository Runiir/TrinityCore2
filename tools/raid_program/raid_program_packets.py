"""Worker packets and handoffs for one raid-program round.

A round has one packet per open boss unit (``boss:<key>``); a ``shards`` packet
that owns the raid's shared shard data (composition, scenario rows, runtime
profiles, route composition, prerequisite graph) when shard inputs are missing
or the end-to-end unit is due; and a ``research`` packet for raid-level research
inputs (strategy catalog, script-readiness audit). The audit is refreshed only
once the end-to-end unit is due, because boss packets change native scripts.
Packets own disjoint files; anything else goes into the handoff as a patch
request. Coordinator-only files (native runtime outside the boss's content
directory, instance script, fidelity registry, CMake, skills, AGENTS.md and both
state files) are never owned. Globs are segment-aware: ``*`` stays inside one
path segment and ``**`` spans any number of segments.
"""
from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path

from tools.raid_program.development_graph import GraphError, STATE_PATH as BOSS_STATE_PATH
from tools.raid_program.raid_program_inputs import COMPOSITIONS, PREREQUISITES, PROFILES, ROUTE_COMPOSITIONS
from tools.raid_program.raid_program_state import STATE_PATH
from tools.raid_program.scenario_catalog import READINESS, ROUTES, STRATEGIES

PACKET_SCHEMA = 'raid_program_worker_packet_v1'
HANDOFF_SCHEMA = 'raid_program_handoff_v1'
SHARDS = 'shards'
RESEARCH = 'research'
SHARD_OWNER = 'raid-shard-architecture'
RESEARCH_OWNER = 'raid-encounter-research'
PATCH_TARGETS = (SHARDS, RESEARCH, 'coordinator')
COORDINATOR_FILES = ['src/**', 'dep/**', 'cmake/**', '**/CMakeLists.txt', 'AGENTS.md', 'CLAUDE.md', '.agents/skills/**',
                     'experiments/configs/encounter_fidelity/**', READINESS.as_posix(), STRATEGIES.as_posix(),
                     BOSS_STATE_PATH.as_posix(), STATE_PATH.as_posix(), 'dvc.lock']
COORDINATOR_ROUTES = ['the instance script, strategy dispatch and any other file under src/ outside owned_files',
                      'experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json',
                      'CMake lists, AGENTS.md, skills and both state files']
HANDOFF_FIELDS = {'packet_id': str, 'round': int, 'changed_files': list, 'new_files': list, 'tests': list,
                  'patch_requests': list, 'validation_neutrality': str, 'risks': list, 'open_items': list,
                  'resolved_inputs': list}
RULES = [
    'Edit only owned_files; send every other change as an exact patch_request (to: shards, research or coordinator).',
    'Never commit, stash, reset, checkout, build, run dvc repro/push, or start/stop a server.',
    'Use raid_workloop start --preview and program status read-only; never select or advance program or boss state.',
    'Keep CPU modest: focused tests only; prefix heavy commands with nice -n 10.',
    'C/C++ files stay below 1,000 lines; split by concern.',
    'Lawful play only: no invented auras, buffs, damage, teleports, casts or forced targets.',
    'Seeded lockouts are diagnostic assistance and never certify a predecessor kill.',
    'Stop editing after the handoff; the coordinator builds only when every packet is handed off.',
]


def _glob_regex(pattern: str) -> re.Pattern[str]:
    out, index = [], 0
    while index < len(pattern):
        if pattern.startswith('**/', index):
            out.append('(?:[^/]+/)*')
            index += 3
        elif pattern.startswith('**', index):
            out.append('.*')
            index += 2
        elif pattern[index] == '*':
            out.append('[^/]*')
            index += 1
        elif pattern[index] == '?':
            out.append('[^/]')
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile(''.join(out) + r'\Z')


def glob_match(path: str, pattern: str) -> bool:
    """Segment-aware glob: ``*`` and ``?`` never cross ``/``; ``**`` spans segments."""
    return bool(_glob_regex(pattern).match(path))


def matches(path: str, patterns: list[str]) -> bool:
    return any(glob_match(path, pattern) for pattern in patterns)


def normalize_path(value) -> str:
    """A repository-relative POSIX path, or GraphError (absolute, '..', '.', backslash, empty)."""
    if not isinstance(value, str) or not value or '\\' in value or value.startswith('/'):
        raise GraphError(f'handoff path must be repository-relative POSIX: {value!r}')
    parts = value.split('/')
    if any(part in ('', '.', '..') for part in parts) or posixpath.normpath(value) != value:
        raise GraphError(f'handoff path must be normalized without . or ..: {value!r}')
    return value


def _shard_files(discovery: dict) -> list[str]:
    raid, token = discovery['raid'], discovery['mode_token']
    return [discovery.get('composition') or f'{COMPOSITIONS.as_posix()}/{raid}_{token}.json', ROUTES.as_posix(),
            PROFILES.as_posix(), f'{ROUTE_COMPOSITIONS.as_posix()}/{raid}_{token}.json',
            f'{PREREQUISITES.as_posix()}/{raid}.json', 'dvc.yaml', f'tests/test_raid_shard_{raid}_*.py']


def _research_inputs(discovery: dict, e2e_due: bool) -> list[dict]:
    """Raid-level research inputs; the script-readiness audit waits until no boss packet edits scripts."""
    return [dict(item, unit='raid') for item in discovery['raid_inputs'] if item['owner_skill'] == RESEARCH_OWNER
            and (e2e_due or item['input'] != 'script_readiness_audit')]


def _shard_inputs(discovery: dict, e2e_due: bool, e2e_failure: dict | None = None) -> list[dict]:
    rows = [dict(item, unit='raid') for item in discovery['raid_inputs'] if item['owner_skill'] == SHARD_OWNER]
    rows += [dict(item, unit=unit['boss_key']) for unit in discovery['units'] for item in unit['missing_inputs']
             if item['owner_skill'] == SHARD_OWNER]
    rows += [dict(item, unit='e2e') for item in discovery['e2e']['missing_inputs']]
    if e2e_due and e2e_failure:
        rows.append({'input': 'e2e_run', 'unit': 'e2e', 'owner_skill': SHARD_OWNER, 'blocks': 'acceptance',
                     'detail': 'the last end-to-end run failed: ' + ', '.join(e2e_failure.get('problems') or [])})
    return rows


def boss_task(unit: dict, last: dict | None) -> tuple[str, str]:
    """(owner skill, task) for a boss packet from its boss-domain inputs and last result."""
    own = [item for item in unit['missing_inputs'] if item['owner_skill'] != SHARD_OWNER]
    names = {item['input'] for item in own}
    if 'native_script' in names:
        return 'raid-encounter-implementation', 'Implement the missing native boss script, then continue with research.'
    if names & {'encounter_research', 'strategy_catalog_row', 'strategy_mode', 'encounter_damage_fidelity'}:
        return 'raid-encounter-research', ('Research the encounter (WCL references by browser extraction), audit the native '
                                           'script against it, calibrate damage fidelity (staged SQL plus a registry patch '
                                           'request), write the raid target, then replace any stub strategy.')
    if 'raid_target' in names:
        return 'raid-tuning-playbook', 'Author the raid target from matched WCL kills, then continue the strategy.'
    if last and last.get('outcome') == 'clear' and (last.get('verdict') or {}).get('status') not in (None, 'pass'):
        return 'raid-tuning-playbook', ('Take the largest actor gap of the last verdict (scoreboard show) and make one '
                                        'mechanism change per actor, bundling below 0.85 of target.')
    if last and last.get('outcome') not in (None, 'clear', 'not_run'):
        return 'raid-performance-loop', ('Route the typed stall of the last shard run (' + str(last.get('outcome'))
                                         + ') to its owning mechanism and repair it.')
    return 'raid-encounter-implementation', ('Implement or repair the bot strategy for the canonical composition so the '
                                             'shard reaches a native clear.')


def build_packets(discovery: dict, program: dict, bosses: list[str] | None, e2e_due: bool,
                  e2e_failure: dict | None = None) -> dict[str, dict]:
    open_units = [unit for unit in discovery['units'] if program['units'].get(unit['boss_key'], {}).get('status') != 'accepted']
    if bosses:
        unknown = set(bosses) - {unit['boss_key'] for unit in open_units}
        if unknown:
            raise GraphError('not an open boss unit of this program: ' + ', '.join(sorted(unknown)))
        open_units = [unit for unit in open_units if unit['boss_key'] in bosses]
    packets: dict[str, dict] = {}
    for unit in open_units:
        results = program['units'].get(unit['boss_key'], {}).get('results') or []
        owner, task = boss_task(unit, results[-1] if results else None)
        packets['boss:' + unit['boss_key']] = {
            'packet_id': 'boss:' + unit['boss_key'], 'units': [unit['unit_id']], 'owner_skill': owner, 'task': task,
            'owned_files': unit['files']['owned'], 'focused_tests': [unit['files']['focused_tests']],
            'inputs': [item for item in unit['missing_inputs'] if item['owner_skill'] != SHARD_OWNER],
            'handoff': None}
    shard_inputs = _shard_inputs(discovery, e2e_due, e2e_failure)
    if shard_inputs:
        raid = discovery['raid']
        packets[SHARDS] = {
            'packet_id': SHARDS, 'units': sorted({f"raid:{raid}:{discovery['mode']}:{row['unit']}" for row in shard_inputs}),
            'owner_skill': SHARD_OWNER,
            'task': ('Provide the shard infrastructure: canonical composition and spec selections, per-cohort scenario '
                     'rows and runtime profiles, seeded-lockout prerequisite data, the composed full-raid route and '
                     'its roster binding. Apply boss packets\' patch requests to these files as they arrive.'),
            'owned_files': _shard_files(discovery),
            'focused_tests': ['pixi run python -m pytest -q ' + ' '.join(discovery.get('shard_tests') or ['tests/test_raid_program.py'])],
            'inputs': shard_inputs, 'handoff': None}
    research_inputs = _research_inputs(discovery, e2e_due)
    if research_inputs:
        packets[RESEARCH] = {
            'packet_id': RESEARCH, 'units': [f"raid:{discovery['raid']}:{discovery['mode']}:raid"],
            'owner_skill': RESEARCH_OWNER,
            'task': ('Close the raid-level research inputs: audit every changed native script of this raid against its '
                     'contract and refresh the script-readiness audit (source_tree_sha256), and add missing strategy '
                     'catalog rows. Change no native script; route script defects to the coordinator.'),
            'owned_files': [READINESS.as_posix(), STRATEGIES.as_posix()],
            'focused_tests': ['pixi run python -m pytest -q tests/test_raid_workloop.py tests/test_raid_program.py'],
            'inputs': research_inputs, 'handoff': None}
    if not packets:
        raise GraphError('no open unit needs a packet this round')
    overlaps = ownership_overlaps(packets)
    if overlaps:
        raise GraphError('packets would share owned files: ' + json.dumps(overlaps)[:600])
    return packets


def _probe(pattern: str) -> str:
    """A concrete path the pattern matches: every wildcard becomes one letter segment or run."""
    return re.sub(r'\*\*/?|\*|\?', lambda match: 'q/' if match.group(0) == '**/' else 'q', pattern)


def ownership_overlaps(packets: dict[str, dict]) -> list[dict]:
    """Pairs of packets whose owned patterns can name one file (identical, concrete or probe match)."""
    overlaps = []
    items = sorted(packets.items())
    for index, (left, first) in enumerate(items):
        for right, second in items[index + 1:]:
            shared = [path for path in first['owned_files']
                      if path in second['owned_files'] or matches(_probe(path), second['owned_files'])]
            shared += [path for path in second['owned_files'] if matches(_probe(path), first['owned_files'])]
            if shared:
                overlaps.append({'packets': [left, right], 'files': sorted(set(shared))})
    return overlaps


def changed_file_owners(packets: dict[str, dict], files: list[str]) -> dict:
    """Owners of each changed file; a file two packets can own is a conflict."""
    owners = {path: [key for key, row in sorted(packets.items()) if matches(path, row['owned_files'])] for path in files}
    return {'owned': {path: names[0] for path, names in owners.items() if len(names) == 1},
            'unowned': sorted(path for path, names in owners.items() if not names),
            'conflicts': {path: names for path, names in owners.items() if len(names) > 1}}


def worker_packet(root: Path, program: dict, discovery: dict, packet_id: str) -> dict:
    """The full packet an implementation agent receives (the handoff contract included)."""
    current = program['rounds'][-1] if program['rounds'] else {}
    packets = current.get('packets') or {}
    if program['stage'] != 'implement' or packet_id not in packets:
        raise GraphError('no packet ' + packet_id + ' in the current implement stage')
    packet = packets[packet_id]
    others = [path for other, row in sorted(packets.items()) if other != packet_id for path in row['owned_files']]
    units = {unit['unit_id']: unit for unit in discovery['units']}
    boss_units = [units[unit_id] for unit_id in packet['units'] if unit_id in units]
    handoff_dir = handoff_directory(program)
    routes = {'coordinator': list(COORDINATOR_ROUTES)}
    if packet_id != SHARDS:
        if SHARDS in packets:
            routes[SHARDS] = _shard_files(discovery)
        else:
            routes['coordinator'] = _shard_files(discovery) + routes['coordinator']
    if packet_id != RESEARCH:
        research_files = [READINESS.as_posix(), STRATEGIES.as_posix()]
        if RESEARCH in packets:
            routes[RESEARCH] = research_files
        else:
            routes['coordinator'] = research_files + routes['coordinator']
    return {
        'schema': PACKET_SCHEMA, 'program_id': program['program_id'], 'round': program['round'],
        'packet_id': packet_id, 'objective': program['objective'], 'owner_skill': packet['owner_skill'],
        'task': packet['task'], 'coordinator_worktree': str(root.resolve()),
        'units': [{key: unit.get(key) for key in ('unit_id', 'boss_key', 'strategy_slug', 'boss_scenario', 'cohort_id',
                                                  'scenario_id', 'lockout', 'native_script', 'research', 'raid_target')}
                  for unit in boss_units],
        'inputs': packet['inputs'],
        'last_results': {unit['boss_key']: (program['units'].get(unit['boss_key'], {}).get('results') or [None])[-1]
                         for unit in boss_units},
        'owned_files': packet['owned_files'],
        'forbidden_files': sorted(set(others + COORDINATOR_FILES) - set(packet['owned_files'])),
        'precedence': 'owned_files override the broader forbidden_files patterns',
        'patch_request_routes': routes,
        'focused_tests': packet['focused_tests'],
        'rules': RULES,
        'handoff': {'schema': HANDOFF_SCHEMA, 'save_as': f'{handoff_dir}/{packet_file(packet_id)}.handoff.json',
                    'required_fields': {name: kind.__name__ for name, kind in HANDOFF_FIELDS.items()},
                    'tests_item': {'command': 'str', 'result': 'str'},
                    'patch_requests_item': {'to': '|'.join(PATCH_TARGETS), 'file': 'str', 'patch': 'exact text'},
                    'resolved_inputs': 'names of this packet\'s inputs the change resolves',
                    'return': 'End your final message with this JSON object only.'},
    }


def packet_file(packet_id: str) -> str:
    return packet_id.replace(':', '_')


def handoff_directory(program: dict) -> str:
    slug = program['program_id'].replace(':', '_').lower()
    return f"artifacts/cata_raid_program/raid_programs/{slug}/round{program['round']:02d}"


def validate_handoff(handoff: dict, packet: dict, round_number: int) -> None:
    if not isinstance(handoff, dict):
        raise GraphError('handoff must be a JSON object')
    problems = [name for name, kind in HANDOFF_FIELDS.items()
                if not isinstance(handoff.get(name), kind) or kind is int and isinstance(handoff.get(name), bool)]
    if problems:
        raise GraphError('handoff fields missing or mistyped: ' + ', '.join(problems))
    if handoff['packet_id'] != packet['packet_id'] or handoff['round'] != round_number:
        raise GraphError('handoff names another packet or round')
    files = [normalize_path(path) for path in handoff['changed_files'] + handoff['new_files']]
    outside = [path for path in files if not matches(path, packet['owned_files'])]
    if outside:
        raise GraphError('handoff changed files outside its packet (send patch_requests instead): ' + ', '.join(outside))
    for test in handoff['tests']:
        if not isinstance(test, dict) or not isinstance(test.get('command'), str) or 'result' not in test:
            raise GraphError('each handoff test needs command and result')
    for request in handoff['patch_requests']:
        if not isinstance(request, dict) or request.get('to') not in PATCH_TARGETS \
                or not isinstance(request.get('file'), str) or not isinstance(request.get('patch'), str):
            raise GraphError('each patch_request needs to (' + '|'.join(PATCH_TARGETS) + '), file and patch')
        normalize_path(request['file'])
