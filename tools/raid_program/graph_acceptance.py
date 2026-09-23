"""Numeric finish line: actor and encounter requirements close only on a scoreboard verdict.

The target file (`experiments/configs/raid_targets/<scenario>.json`, schema
raid_target_v1) defines the ratio, kill count and death limits. The scoreboard
turns retained kills into a raid_target_verdict_v1. An actor requirement is
accepted when its verdict row is `pass`; an encounter requirement (one with
`needs_all_actors`) when the overall verdict is `pass`. `no_reference` is
missing reference work and never acceptance. Other requirements keep the
reviewed repair assessment.

CLI: `python -m tools.raid_program.graph_acceptance verdict --label <label>`
writes the verdict file to cite as the assessment adapter's `verdict`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from tools.raid_program import development_graph as graph

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = Path('experiments/configs/raid_targets')
VERDICT_DIR = Path('artifacts/cata_raid_program/verdicts')
VERDICT_SCHEMA = 'raid_target_verdict_v1'
TARGET_SCHEMA = 'raid_target_v1'
CONTRACT = ('schema', 'scenario', 'label', 'kills', 'target_path', 'actors', 'encounter', 'status')
UNATTRIBUTABLE = ('infrastructure_loss', 'contamination', 'interruption')
RULE = ('Actor requirements close when their scoreboard verdict row is pass; encounter requirements '
        'when the overall verdict is pass. The target file sets ratio, kill count and death limits. '
        'no_reference/insufficient_kills/fail keep the requirement open.')


def scenario_id(encounter: dict) -> str:
    return f"{encounter['raid']}_{encounter['mode'].lower()}_{encounter['boss']}"


def target_pointer(g: dict) -> dict:
    """Saved pointer for new scenarios; the path convention for older saved states."""
    saved = g.get('raid_target')
    if saved:
        return saved
    scenario = scenario_id(g['encounter'])
    return {'scenario': scenario, 'path': (TARGET_DIR / (scenario + '.json')).as_posix()}


def scope(requirement: dict) -> str | None:
    if requirement.get('actor_id'):
        return 'actor'
    return 'encounter' if requirement.get('needs_all_actors') else None


def evaluate(root: Path, scenario: str, label: str) -> dict:
    try:
        from tools.raid_program.scoreboard import evaluate_target
    except ImportError as exc:
        raise graph.GraphError('scoreboard unavailable: ' + str(exc)) from exc
    try:
        verdict = evaluate_target(root, scenario, label)
    except (ValueError, KeyError, OSError) as exc:
        raise graph.GraphError('scoreboard verdict failed: ' + str(exc)) from exc
    if not isinstance(verdict, dict) or verdict.get('schema') != VERDICT_SCHEMA:
        raise graph.GraphError('scoreboard returned no ' + VERDICT_SCHEMA)
    return verdict


def _contract(verdict: dict) -> dict:
    return json.loads(json.dumps({key: verdict.get(key) for key in CONTRACT}))


def load_verdict(root: Path, g: dict, ref: dict) -> dict:
    """The cited verdict must be this run's batch and match a fresh recomputation."""
    verdict = graph.read(graph.file_ref(root, ref))
    if verdict.get('schema') != VERDICT_SCHEMA:
        raise graph.GraphError('verdict must be ' + VERDICT_SCHEMA)
    pointer = target_pointer(g)
    if verdict.get('scenario') != pointer['scenario']:
        raise graph.GraphError('verdict scenario differs from the program encounter')
    label = (g.get('run') or {}).get('scoreboard_label')
    if not label or verdict.get('label') != label:
        raise graph.GraphError("verdict label must equal the validated run's scoreboard_label")
    if _contract(evaluate(root, pointer['scenario'], label)) != _contract(verdict):
        raise graph.GraphError('verdict file differs from the scoreboard recomputation; regenerate it')
    return verdict


def check_requirement(key: str, requirement: dict, verdict: dict) -> None:
    if scope(requirement) == 'actor':
        row = (verdict.get('actors') or {}).get(requirement['actor_id'])
        if not isinstance(row, dict):
            raise graph.GraphError(key + ': actor missing from scoreboard verdict')
        if requirement.get('spec') and row.get('spec') != requirement['spec']:
            raise graph.GraphError(key + ': verdict spec differs from the roster actor')
        status = row.get('status')
    else:
        status = verdict.get('status')
    if status == 'no_reference':
        raise graph.GraphError(key + ': no matched WCL reference; that is reference work, never acceptance')
    if status != 'pass':
        raise graph.GraphError(f'{key}: scoreboard verdict is {status}, not pass')


def record(requirement: dict, ref: dict, verdict: dict) -> dict:
    """Compact acceptance record kept on the requirement."""
    base = {'receipt': ref, 'label': verdict['label'], 'kills': verdict.get('kills'),
            'target_path': verdict.get('target_path')}
    if scope(requirement) == 'actor':
        row = verdict['actors'][requirement['actor_id']]
        return base | {key: row.get(key) for key in ('status', 'spec', 'n', 'mean_dps', 'target_dps', 'ratio')}
    return base | {'status': verdict['status'], 'encounter': verdict.get('encounter'),
                   'ratios': {actor: row.get('ratio') for actor, row in verdict['actors'].items()}}


def check_target_file(root: Path, g: dict) -> None:
    pointer = target_pointer(g)
    try:
        target = graph.read(root / pointer['path'])
    except (OSError, ValueError) as exc:
        raise graph.GraphError('raid target file missing or invalid: ' + pointer['path']) from exc
    if target.get('schema') != TARGET_SCHEMA or target.get('scenario', pointer['scenario']) != pointer['scenario']:
        raise graph.GraphError('raid target must be ' + TARGET_SCHEMA + ' for ' + pointer['scenario'])


def _flag(r: dict, key: str, default=None):
    value = r.get(key, default)
    if type(value) is not bool:
        raise graph.GraphError('separate boolean outcome required: ' + key)
    return value


def _actor_reviews(root: Path, g: dict, reviews) -> None:
    if not isinstance(reviews, dict) or set(reviews) != set(g['actor_ids']):
        raise graph.GraphError('every roster actor needs a review or explicit not_exercised in actor_reviews')
    for review in reviews.values():
        if review.get('status') == 'reviewed':
            graph.file_ref(root, review.get('receipt'))
        elif review.get('status') == 'not_exercised':
            graph.required(review, 'reason')
        else:
            raise graph.GraphError('invalid actor review disposition')


def assess(root: Path, g: dict, r: dict) -> None:
    """Record proposed acceptance for publication; mutates the graph copy."""
    run = g['run']
    if r.get('attempt_id') != run['attempt_id']:
        raise graph.GraphError('assessment attempt mismatch')
    verdict = load_verdict(root, g, r['verdict']) if r.get('verdict') is not None else None
    if verdict is None:
        graph.required(r, 'baseline', 'comparison', 'actor_reviews')
    for key in ('baseline', 'comparison'):
        if r.get(key) is not None:
            graph.file_ref(root, r[key])
    if verdict is None or r.get('actor_reviews') is not None:
        _actor_reviews(root, g, r.get('actor_reviews'))
    clear = _flag(r, 'encounter_clear')
    repair = _flag(r, 'repair_accepted', False if verdict else None)
    if verdict is not None and 'performance_accepted' in r:
        raise graph.GraphError('performance comes from the verdict; omit performance_accepted')
    # Legacy performance means the reviewed dummy/baseline gate, not the verdict.
    legacy_performance = False if verdict else _flag(r, 'performance_accepted')
    if clear and (run['scenario_kind'] != 'raid' or run['terminal_reason'] != 'clear'):
        raise graph.GraphError('no observed raid clear')
    accepted = r.get('accepted_requirements', [])
    if not isinstance(accepted, list) or len(set(accepted)) != len(accepted):
        raise graph.GraphError('accepted_requirements must be a unique list')
    if run.get('source_scope') == 'recorded_source_only' and (accepted or repair or legacy_performance):
        raise graph.GraphError('historical run closure cannot accept the current source; preserve evidence and route the next edge')
    if run['terminal_reason'] in UNATTRIBUTABLE and (accepted or repair or legacy_performance):
        raise graph.GraphError('unattributable/incomplete run cannot accept a repair or performance')
    if legacy_performance and (r.get('baseline_matched') is not True or r.get('unexplained_material_decline') is not False):
        raise graph.GraphError('performance needs matched baseline and no unexplained decline')
    if not set(accepted) <= set(g['unit']['requirements']):
        raise graph.GraphError('cannot accept requirements outside current unit')
    pending_verdict = {}
    for key in accepted:
        requirement = g['requirements'][key]
        if requirement.get('needs_raid') and not clear:
            raise graph.GraphError('requirement needs raid validation')
        if scope(requirement):
            if verdict is None:
                raise graph.GraphError(key + ': actor and encounter requirements are accepted only from a scoreboard verdict')
            check_requirement(key, requirement, verdict)
            pending_verdict[key] = record(requirement, r['verdict'], verdict)
            continue
        if not repair:
            raise graph.GraphError('requirement acceptance needs end-to-end repair acceptance')
        if key == 'raid_target':
            check_target_file(root, g)
        if requirement.get('needs_performance') and not legacy_performance:
            raise graph.GraphError('requirement needs performance acceptance')
    if verdict is None:
        from tools.raid_program.dps_gate import verify_assessment
        try:
            verify_assessment(root, g, r)
        except (ValueError, KeyError, OSError) as exc:
            raise graph.GraphError('DPS performance acceptance: ' + str(exc)) from exc
    g['pending_acceptance'] = accepted
    if pending_verdict:
        g['pending_verdict'] = pending_verdict
    g['outcomes'] = {'encounter_clear': clear, 'repair_accepted': repair,
                     'performance_accepted': verdict['status'] == 'pass' if verdict else legacy_performance}
    if verdict is not None:
        g['outcomes'].update(verdict_status=verdict['status'], verdict_label=verdict['label'])
    if not accepted:
        edge = g['unit']['edge']
        g['failures'][edge] = g['failures'].get(edge, 0) + 1


def finish_line(root: Path, g: dict) -> dict:
    pointer = target_pointer(g)
    present = (root / pointer['path']).is_file()
    open_by_scope = {'actor': [], 'encounter': []}
    for key, requirement in g['requirements'].items():
        if requirement['status'] != 'accepted' and scope(requirement):
            open_by_scope[scope(requirement)].append(key)
    return {'scenario': pointer['scenario'], 'target_path': pointer['path'], 'target_present': present,
            'rule': RULE, 'open_actor_requirements': open_by_scope['actor'],
            'open_encounter_requirements': open_by_scope['encounter'],
            'verdict_command': 'pixi run python -m tools.raid_program.graph_acceptance verdict --label <scoreboard_label>',
            'work_item': None if present else
                f"Author {pointer['path']} ({TARGET_SCHEMA}) from matched WCL kills; no actor or encounter requirement can close without it."}


def write_verdict(root: Path, label: str, *, write: bool = True) -> dict:
    """Evaluate the active scenario's batch and retain the verdict content-addressed."""
    state = graph.read(root / graph.STATE_PATH)
    graph.check_state(root, state)
    g = state['development_graph']
    scenario = target_pointer(g)['scenario']
    verdict = evaluate(root, scenario, label)
    acceptable = []
    for key in g['unit']['requirements']:
        requirement = g['requirements'][key]
        if requirement['status'] == 'open' and scope(requirement):
            try:
                check_requirement(key, requirement, verdict)
                acceptable.append(key)
            except graph.GraphError:
                pass
    result = {'status': verdict['status'], 'label': label, 'kills': verdict.get('kills'),
              'actors': {actor: {k: row.get(k) for k in ('spec', 'status', 'ratio')}
                         for actor, row in (verdict.get('actors') or {}).items()},
              'encounter': verdict.get('encounter'), 'acceptable_unit_requirements': acceptable}
    if not write:
        return result
    payload = (json.dumps(verdict, indent=2, sort_keys=True) + '\n').encode()
    sha = graph.digest(payload)
    name = f"{scenario}-{re.sub(r'[^A-Za-z0-9._-]', '_', label)}-{sha[:12]}.json"
    path = root / VERDICT_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open('xb') as stream:
            stream.write(payload)
    ref = {'path': (VERDICT_DIR / name).as_posix(), 'sha256': sha}
    graph.file_ref(root, ref)
    return result | {'verdict': ref, 'next': 'Cite "verdict" in the assessment adapter with encounter_clear and '
                     'accepted_requirements drawn from acceptable_unit_requirements.'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    verdict = commands.add_parser('verdict', help='Evaluate a scoreboard batch for the active scenario')
    verdict.add_argument('--label', required=True)
    verdict.add_argument('--print-only', action='store_true', help='Do not write the verdict file')
    args = parser.parse_args(argv)
    try:
        result = write_verdict(args.root.resolve(), args.label, write=not args.print_only)
    except (graph.GraphError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
