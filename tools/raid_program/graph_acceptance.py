"""Numeric finish line: actor and encounter requirements close only on a scoreboard verdict.

The target file (`experiments/configs/raid_targets/<scenario>.json`, schema
raid_target_v1) defines the ratio, kill count and death limits. The scoreboard
turns retained kills into a raid_target_verdict_v1. An actor requirement is
accepted when its verdict row and the encounter are `pass`; an encounter
requirement (one with `needs_all_actors`) when the overall verdict is `pass`
and its roster covers every program actor. `no_reference` is missing reference
work and never acceptance. Other requirements keep the reviewed assessment.

A verdict only counts for the unit that produced it: every counted kill ran the
unit's binary, every kill was recorded after the unit claimed validation, the
label was not used by an earlier acceptance, and the target/WCL inputs still
hash to what the scoreboard judged. It is recomputed at assessment and again at
publication.

CLI:
  receipt --label L --cleanup-verified   write the validate (run) adapter for a batch
  verdict --label L                      write the verdict file to cite at assessment
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from tools.raid_program import development_graph as graph
from tools.raid_program.play_mode_guard import PLAY_EXCLUSION_REASON, PLAY_TERMINAL_REASON, find_play_markers

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = Path('experiments/configs/raid_targets')
VERDICT_DIR = Path('artifacts/cata_raid_program/verdicts')
RUN_DIR = Path('artifacts/cata_raid_program')  # top level: completed_operation scans it for run receipts
VERDICT_SCHEMA = 'raid_target_verdict_v1'
TARGET_SCHEMA = 'raid_target_v1'
UNATTRIBUTABLE = ('infrastructure_loss', 'contamination', 'interruption', PLAY_TERMINAL_REASON)
RULE = ('Actor requirements close when their scoreboard verdict row and the encounter are pass; encounter '
        'requirements when the overall verdict is pass with the full roster. The target file sets ratio, kill '
        'count and death limits. Kills must come from the unit binary after its validation claim, on a label no '
        'earlier acceptance used. no_reference/insufficient_kills/fail keep the requirement open.')


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


def check_not_play(evidence: dict, what: str) -> None:
    """Human play-mode evidence is recorded for ML only and never closes or records a requirement."""
    reasons = find_play_markers(evidence) + [
        f"kill {k.get('kill_id')} is {PLAY_EXCLUSION_REASON}" for k in evidence.get('kills_detail') or []
        if isinstance(k, dict) and k.get('exclusion_reason') == PLAY_EXCLUSION_REASON]
    if reasons:
        raise graph.GraphError(f'{what}: play-mode evidence is never accepted ({"; ".join(reasons[:5])})')


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


def _normal(value) -> object:
    return json.loads(json.dumps(value, sort_keys=True))


def _time(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError as exc:
        raise graph.GraphError('invalid timestamp: ' + str(value)) from exc


def check_inputs(root: Path, g: dict, verdict: dict) -> None:
    """The judged target, WCL reference and WoWSims fallback index files are the current ones."""
    pointer = target_pointer(g)
    if verdict.get('target_path') != pointer['path']:
        raise graph.GraphError('verdict target differs from the program raid target')
    target_file = root / pointer['path']
    if not target_file.is_file() or verdict.get('target_sha256') != graph.digest(target_file.read_bytes()):
        raise graph.GraphError('raid target changed since the verdict (target_sha256)')
    target = graph.read(target_file)
    for field, key in (('wcl_manifest_sha256', 'wcl_reference_manifest'), ('wcl_timelines_sha256', 'wcl_cast_timelines')):
        path = target.get(key)
        if path is None and field == 'wcl_timelines_sha256' and verdict.get(field) is None:
            continue
        reference = root / str(path or '')
        if not path or not reference.is_file() or verdict.get(field) != graph.digest(reference.read_bytes()):
            raise graph.GraphError(f'WCL reference changed since the verdict ({field})')
    index = (target.get('fallback_reference') or {}).get('promotion_index')
    if target.get('fallback_reference') is None:
        if verdict.get('fallback_index_sha256') is not None:
            raise graph.GraphError('verdict pins a WoWSims fallback index the target does not declare')
    elif (not index or not (root / index).is_file()
          or verdict.get('fallback_index_sha256') != graph.digest((root / index).read_bytes())):
        raise graph.GraphError('WoWSims fallback index changed since the verdict (fallback_index_sha256)')


def check_kills(g: dict, verdict: dict) -> None:
    """Every kill belongs to this unit's validated run and binary."""
    run, binary = g['run'], g['build_identity']['binary_sha256']
    kills = verdict.get('kills_detail')
    if not isinstance(kills, list) or not kills:
        raise graph.GraphError('verdict has no kills_detail')
    counted = [k for k in kills if k.get('counted')]
    if not counted:
        raise graph.GraphError('verdict counts no kills')
    if verdict.get('worldserver_sha256') != binary or any(k.get('worldserver_sha256') != binary for k in counted):
        raise graph.GraphError("counted kills did not all run the unit's binary " + binary[:12])
    if not run.get('claimed_at'):
        raise graph.GraphError('validation claim has no claimed_at; claim validation again before measuring')
    claimed = _time(run['claimed_at'])
    if any(_time(k.get('recorded_at')) < claimed for k in kills):
        raise graph.GraphError("verdict includes kills recorded before the unit's validation claim")
    if run.get('kill_ids') is not None and sorted(k.get('kill_id') for k in kills) != sorted(run['kill_ids']):
        raise graph.GraphError("verdict kills differ from the validated run's kill_ids")


def check_label_unused(g: dict, label: str) -> None:
    for key, requirement in g['requirements'].items():
        if requirement['status'] == 'accepted' and (requirement.get('verdict') or {}).get('label') == label:
            raise graph.GraphError(f'label {label} already accepted {key}; measure a new batch')


def verify_verdict(root: Path, g: dict, ref: dict) -> dict:
    """The cited verdict is this unit's batch and matches a fresh recomputation."""
    verdict = graph.read(graph.file_ref(root, ref))
    if verdict.get('schema') != VERDICT_SCHEMA:
        raise graph.GraphError('verdict must be ' + VERDICT_SCHEMA)
    check_not_play(verdict, 'verdict')
    scenario = target_pointer(g)['scenario']
    if verdict.get('scenario') != scenario:
        raise graph.GraphError('verdict scenario differs from the program encounter')
    label = (g.get('run') or {}).get('scoreboard_label')
    if not label or verdict.get('label') != label:
        raise graph.GraphError("verdict label must equal the validated run's scoreboard_label")
    if _normal(evaluate(root, scenario, label)) != _normal(verdict):
        raise graph.GraphError('verdict file differs from the scoreboard recomputation; regenerate it')
    check_inputs(root, g, verdict)
    check_kills(g, verdict)
    check_label_unused(g, label)
    return verdict


def check_requirement(key: str, requirement: dict, verdict: dict, actor_ids: list[str]) -> None:
    if scope(requirement) == 'actor':
        row = (verdict.get('actors') or {}).get(requirement['actor_id'])
        if not isinstance(row, dict):
            raise graph.GraphError(key + ': actor missing from scoreboard verdict')
        if requirement.get('spec') and row.get('spec') != requirement['spec']:
            raise graph.GraphError(key + ': verdict spec differs from the roster actor')
        status = row.get('status')
        encounter = (verdict.get('encounter') or {}).get('status')
        if status == 'pass' and encounter != 'pass':
            raise graph.GraphError(f'{key}: encounter verdict is {encounter}, not pass')
    else:
        status = verdict.get('status')
        roster = verdict.get('roster') or {}
        if (roster.get('missing') or not set(actor_ids) <= set(roster.get('expected') or [])
                or not set(actor_ids) <= set(verdict.get('actors') or {})):
            raise graph.GraphError(key + ': verdict roster must cover every program actor with none missing')
    if status == 'no_reference':
        raise graph.GraphError(key + ': no matched WCL reference or verified WoWSims fallback; that is reference work, never acceptance')
    if status != 'pass':
        raise graph.GraphError(f'{key}: scoreboard verdict is {status}, not pass')


def record(requirement: dict, ref: dict, verdict: dict) -> dict:
    """Compact acceptance record kept on the requirement, pinning the judged inputs."""
    base = {'receipt': ref, 'label': verdict['label'], 'kills': verdict.get('kills'),
            'kill_ids': [k['kill_id'] for k in verdict['kills_detail'] if k.get('counted')],
            **{key: verdict.get(key) for key in ('worldserver_sha256', 'target_path', 'target_sha256',
                                                  'wcl_manifest_sha256', 'wcl_timelines_sha256',
                                                  'fallback_index_sha256')}}
    if scope(requirement) == 'actor':
        row = verdict['actors'][requirement['actor_id']]
        return base | {key: row.get(key) for key in ('status', 'spec', 'n', 'mean_dps', 'target_dps', 'ratio',
                                                     'reference_basis', 'required_ratio', 'required_dps')} | {
            'encounter_status': verdict['encounter']['status']}
    return base | {'status': verdict['status'], 'encounter': verdict.get('encounter'), 'roster': verdict.get('roster'),
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
    check_not_play(r, 'assessment')
    verdict = verify_verdict(root, g, r['verdict']) if r.get('verdict') is not None else None
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
            check_requirement(key, requirement, verdict, g['actor_ids'])
            pending_verdict[key] = record(requirement, r['verdict'], verdict)
            continue
        if not repair:
            raise graph.GraphError('requirement acceptance needs end-to-end repair acceptance')
        if key == 'raid_target':
            check_target_file(root, g)
        if key == 'encounter_damage_fidelity':
            # Blizzlike boss damage: closes only when every boss entry of the
            # scenario is calibrated (or not applicable) in the registry.
            from tools.bot_ml.live_validation_fidelity import check_scenario_damage_fidelity
            try:
                check_scenario_damage_fidelity(root, g['encounter'])
            except ValueError as exc:
                raise graph.GraphError(str(exc)) from exc
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
        if requirement['status'] == 'open' and scope(requirement):
            open_by_scope[scope(requirement)].append(key)
    return {'scenario': pointer['scenario'], 'target_path': pointer['path'], 'target_present': present,
            'rule': RULE, 'open_actor_requirements': open_by_scope['actor'],
            'open_encounter_requirements': open_by_scope['encounter'],
            'run_receipt_command': 'pixi run python -m tools.raid_program.graph_acceptance receipt --label <label> --cleanup-verified',
            'verdict_command': 'pixi run python -m tools.raid_program.graph_acceptance verdict --label <scoreboard_label>',
            'work_item': None if present else
                f"Author {pointer['path']} ({TARGET_SCHEMA}) from matched WCL kills; no actor or encounter requirement can close without it."}


def _active(root: Path) -> dict:
    state = graph.read(root / graph.STATE_PATH)
    graph.check_state(root, state)
    return state['development_graph']


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open('xb') as stream:
            stream.write(payload)


def _safe(label: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]', '_', label)


def write_run_receipt(root: Path, label: str, *, producer: str, cleanup_verified: bool,
                      terminal_reason: str | None = None) -> dict:
    """Validate adapter for one labelled scoreboard batch of the claimed unit."""
    g = _active(root)
    claim = g.get('claim')
    if g['stage'] != 'validate' or not claim:
        raise graph.GraphError('claim the validate stage before writing its run receipt')
    if not cleanup_verified:
        raise graph.GraphError('check that every attempt closed and was cleaned up, then pass --cleanup-verified')
    identity = g['assignment']['validation_identity']
    if identity.get('scenario_kind') != 'raid':
        raise graph.GraphError('scoreboard batches validate raid units only')
    verdict = evaluate(root, target_pointer(g)['scenario'], label)
    check_not_play(verdict, 'label ' + label)
    kills = verdict.get('kills_detail') or []
    if not kills:
        raise graph.GraphError('label has no recorded kills: ' + label)
    binary = g['build_identity']['binary_sha256']
    foreign = [str(k.get('kill_id')) for k in kills if k.get('worldserver_sha256') != binary]
    if foreign:
        raise graph.GraphError("kills did not run the unit's binary " + binary[:12] + ': ' + ', '.join(foreign[:5]))
    if claim.get('claimed_at') and any(_time(k.get('recorded_at')) < _time(claim['claimed_at']) for k in kills):
        raise graph.GraphError('label has kills recorded before this validation claim; use a new label')
    if terminal_reason is None:
        if not all(k.get('native_clear') for k in kills):
            raise graph.GraphError('not every kill cleared natively; pass --terminal-reason')
        terminal_reason = 'clear'
    pointers = sorted({k['evidence_dvc_pointer'] for k in kills if k.get('evidence_dvc_pointer')})
    from tools.raid_program.workflow_step import receipt_reference
    evidence = [receipt_reference(root, pointer) for pointer in pointers]
    if not evidence:
        raise graph.GraphError("the label's kills name no evidence_dvc_pointer")
    receipt = {'authority': 'coordinator_attestation', 'kind': 'run', 'unit_id': g['unit']['id'],
               'producer': producer, 'evidence': evidence, 'operation_id': claim['operation_id'],
               'build_identity': g['build_identity'], 'validation_identity': identity,
               'scenario_kind': 'raid', 'clock': 'completion_watchdog', 'attempt_id': 'scoreboard:' + label,
               'server_epoch': verdict.get('first_recorded_at') or min(k['recorded_at'] for k in kills),
               'closed': True, 'cleanup_verified': True, 'terminal_reason': terminal_reason,
               'scoreboard_label': label, 'kill_ids': [k['kill_id'] for k in kills]}
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    sha = graph.digest(payload)
    relative = RUN_DIR / f'scoreboard-run-{_safe(label)}-{sha[:12]}.json'
    _write_once(root / relative, payload)
    from tools.raid_program.workflow_step import apply_step
    result = {'receipt': {'path': relative.as_posix(), 'sha256': sha}, 'kills': len(kills),
              'next_command': f"pixi run python -m tools.raid_program.workflow_step advance --receipt {relative.as_posix()} "
                              f"--owner {claim['owner']}"}
    try:
        preview = apply_step(root, relative, owner=claim['owner'], dry_run=True)
        result['dry_run'] = {'from_stage': preview['from_stage'], 'to_stage': preview['to_stage']}
    except (graph.GraphError, ValueError, OSError) as exc:
        result['dry_run_error'] = str(exc)
    return result


def write_verdict(root: Path, label: str, *, write: bool = True) -> dict:
    """Evaluate the active scenario's batch and retain the verdict content-addressed."""
    g = _active(root)
    scenario = target_pointer(g)['scenario']
    verdict = evaluate(root, scenario, label)
    check_not_play(verdict, 'label ' + label)
    acceptable = []
    for key in g['unit']['requirements']:
        requirement = g['requirements'][key]
        if requirement['status'] == 'open' and scope(requirement):
            try:
                check_requirement(key, requirement, verdict, g['actor_ids'])
                acceptable.append(key)
            except graph.GraphError:
                pass
    result = {'status': verdict['status'], 'label': label, 'kills': verdict.get('kills'),
              'actors': {actor: {k: row.get(k) for k in ('spec', 'status', 'ratio')}
                         for actor, row in (verdict.get('actors') or {}).items()},
              'encounter': verdict.get('encounter'), 'acceptable_unit_requirements': acceptable}
    if g['stage'] == 'assess':
        try:
            check_inputs(root, g, verdict)
            check_kills(g, verdict)
            check_label_unused(g, label)
        except graph.GraphError as exc:
            result['binding_error'] = str(exc)
    if not write:
        return result
    payload = (json.dumps(verdict, indent=2, sort_keys=True) + '\n').encode()
    sha = graph.digest(payload)
    relative = VERDICT_DIR / f'{scenario}-{_safe(label)}-{sha[:12]}.json'
    _write_once(root / relative, payload)
    ref = {'path': relative.as_posix(), 'sha256': sha}
    graph.file_ref(root, ref)
    return result | {'verdict': ref, 'next': 'Cite "verdict" in the assessment adapter with encounter_clear and '
                     'accepted_requirements drawn from acceptable_unit_requirements.'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('receipt', help='Write the validate (run) adapter for a scoreboard batch')
    run.add_argument('--label', required=True)
    run.add_argument('--producer', default='coordinator')
    run.add_argument('--cleanup-verified', action='store_true', help='Attest every attempt closed and was cleaned up')
    run.add_argument('--terminal-reason', help='Required when not every kill cleared natively')
    verdict = commands.add_parser('verdict', help='Evaluate a scoreboard batch for the active scenario')
    verdict.add_argument('--label', required=True)
    verdict.add_argument('--print-only', action='store_true', help='Do not write the verdict file')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'receipt':
            result = write_run_receipt(root, args.label, producer=args.producer,
                                       cleanup_verified=args.cleanup_verified, terminal_reason=args.terminal_reason)
        else:
            result = write_verdict(root, args.label, write=not args.print_only)
    except (graph.GraphError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
