"""Current performance acceptance. Diagnostic repairs never waive this gate."""
from __future__ import annotations

import math
from pathlib import Path

MINIMUM_RATIO = 0.95


def evaluate(measured, reference, *, scoring_seconds, attributable, setup_admitted,
             explained_dtr_dps=0):
    values = (measured, reference, scoring_seconds, explained_dtr_dps)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('DPS gate requires finite observed values')
    if measured < 0 or reference <= 0 or explained_dtr_dps < 0:
        raise ValueError('invalid DPS/reference/attribution values')
    ratio = measured/reference
    checks = {'exact_300_seconds': scoring_seconds == 300,
              'attributable_run': attributable is True,
              'joined_setup_admitted': setup_admitted is True,
              'at_least_95_percent': ratio >= MINIMUM_RATIO}
    gap = reference-measured
    return {'schema': 'raid_dps_gate_v1', 'minimum_ratio': MINIMUM_RATIO,
            'measured_dps': measured, 'reference_dps': reference, 'ratio': ratio,
            'required_dps': MINIMUM_RATIO*reference, 'gap_dps': gap,
            'remaining_to_gate_dps': max(0, MINIMUM_RATIO*reference-measured),
            'explained_dtr_dps': explained_dtr_dps,
            'unexplained_gap_dps': max(0, gap-explained_dtr_dps),
            'dtr_is_extra_allowance': False, 'checks': checks, 'passed': all(checks.values())}


def verify_packet(root: Path, packet_ref: dict, *, actor_id: str, spec: str, expected_build: dict | None = None):
    """Recompute from run-bound raw damage and current promoted reference, not a verdict."""
    from tools.raid_program.development_graph import file_ref, read
    from tools.raid_program.evidence_inputs import load_input
    from tools.raid_program.evidence_metrics import native_actors, simulator_actor
    from tools.raid_program.evidence_admission import admission
    from tools.raid_program.evidence_task import confined
    from tools.raid_program.raid_workloop import build_spec_work_unit

    packet = read(file_ref(root, packet_ref))
    run = read(file_ref(root, packet['run']))
    build = run.get('build_identity', {})
    import re
    if (not re.fullmatch('[0-9a-f]{64}', str(build.get('binary_sha256', '')))
            or not re.fullmatch('[0-9a-f]{40}', str(build.get('source_commit', '')))):
        raise ValueError('DPS calibration lacks source/binary identity')
    if expected_build is not None and build != expected_build:
        raise ValueError('DPS calibration is not from the current validated build')
    identity = run.get('validation_identity', {})
    if str(packet.get('actor_id')) != actor_id or identity.get('actor_id') != actor_id or identity.get('spec') != spec:
        raise ValueError('DPS calibration actor/spec binding mismatch')
    if run.get('scenario_kind') != 'dummy' or identity.get('mode') != 'single_target_300':
        raise ValueError('role/raid validation cannot substitute for isolated DPS calibration')
    if run.get('scoring_ms') != 300000 or run.get('terminal_reason') != 'measurement_complete':
        raise ValueError('DPS calibration scoring incomplete')
    raw = packet['native_input']
    path, sep, member = raw.partition('::')
    raw = str(confined(root, path)) + (sep+member if sep else '')
    document, receipt = load_input(raw)
    if (run.get('calibration_observation_mode') == 'explicit_probe'
            or document.get('calibration_observation_mode') == 'explicit_probe'):
        raise ValueError('explicit diagnostic probe cannot qualify DPS')
    if document.get('calibration_acceptance', {}).get('passed') is False:
        raise ValueError('native calibration acceptance failed')
    if receipt['payload_sha256'] != run.get('report_summary', {}).get('actor_report_sha256'):
        raise ValueError('native DPS report is not bound by run receipt')
    actor = str(packet['native_actor'])
    native = native_actors(document)[actor]
    if native.get('spec') != spec:
        raise ValueError('native calibration spec mismatch')
    benchmark = build_spec_work_unit(spec, root)['benchmark']
    if benchmark.get('state') != 'ready' or benchmark.get('accepted_dps_reference_class') != 'self_provided_baseline':
        raise ValueError('current exact self-provided simulator reference is not ready')
    refs = benchmark['rotation_review_reference_artifacts']
    paths = {key: str(confined(root, refs[key])) for key in ('raid_sim_request', 'raid_sim_result', 'compute_stats')}
    from hashlib import sha256
    for path in paths.values():
        if sha256(Path(path).read_bytes()).hexdigest() != Path(path).stem:
            raise ValueError('promoted content-addressed reference hash mismatch')
    joined, _ = admission(raw, paths['raid_sim_request'], paths['raid_sim_result'], paths['compute_stats'], 'self_provided_baseline', actor)
    sim = simulator_actor(load_input(paths['raid_sim_result'])[0])
    if abs(sim['dps']-benchmark['accepted_dps']) > 0.001:
        raise ValueError('simulator result differs from promoted catalog')
    result = evaluate(native['dps'], sim['dps'], scoring_seconds=native['duration_seconds'],
                      attributable=all(run.get(k) is True for k in ('closed', 'cleanup_verified', 'evidence_identity_complete')),
                      setup_admitted=joined['setup_comparison_admitted'])
    if not result['passed']:
        raise ValueError('95% DPS gate failed: ' + ', '.join(k for k,v in result['checks'].items() if not v))
    return result


def verify_assessment(root: Path, graph: dict, assessment: dict):
    """DPS acceptance cannot be replaced by a role review or a raid total."""
    if not assessment['performance_accepted']:
        return {}
    results = {}
    selected = {graph['requirements'][key].get('actor_id')
                for key in graph.get('unit', {}).get('requirements', [])}
    selected.discard(None)
    if any(graph['requirements'][key].get('needs_all_actors')
           for key in graph.get('unit', {}).get('requirements', [])):
        selected = set()
    for actor, review in assessment['actor_reviews'].items():
        if selected and actor not in selected and review.get('accepted') is not True:
            continue
        rows = [r for r in graph['requirements'].values() if r.get('actor_id') == actor]
        roles = {'dps' if r.get('role') in ('ranged_dps', 'melee_dps') else r.get('role') for r in rows}
        specs = {r.get('spec') for r in rows}
        if len(roles) != 1 or next(iter(roles)) not in ('dps', 'tank', 'healer'):
            raise ValueError('accepted actor needs an explicit roster role: ' + actor)
        if roles == {'dps'}:
            if len(specs) != 1 or not next(iter(specs)):
                raise ValueError('accepted DPS actor needs an exact spec: ' + actor)
            if not review.get('dps_calibration'):
                raise ValueError('95% DPS gate needs a run-bound calibration packet: ' + actor)
            results[actor] = verify_packet(root, review['dps_calibration'], actor_id=actor,
                spec=next(iter(specs)), expected_build=graph.get('build_identity', {}))
    return results


def main():
    """Create a checked packet from explicit retained inputs; never print raw data."""
    import argparse
    import json
    from tools.raid_program.development_graph import snapshot
    from tools.raid_program.evidence_task import confined
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--run', required=True)
    parser.add_argument('--native-input', required=True, help='JSON or archive::member')
    parser.add_argument('--actor-id', required=True, help='Frozen roster actor')
    parser.add_argument('--native-actor', required=True, help='Measured calibration actor GUID')
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    run_path = confined(root, args.run).relative_to(root).as_posix()
    output = confined(root, args.output)
    packet = {'schema': 'raid_dps_calibration_packet_v1', 'actor_id': args.actor_id,
              'run': {'path': run_path, 'sha256': snapshot(root, [run_path])[run_path]},
              'native_input': args.native_input, 'native_actor': args.native_actor}
    # Exclusive creation keeps previously retained packets immutable.
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(packet, stream, indent=2)
        stream.write('\n')
    relative = output.relative_to(root).as_posix()
    ref = {'path': relative, 'sha256': snapshot(root, [relative])[relative]}
    try:
        result = verify_packet(root, ref, actor_id=args.actor_id, spec=args.spec)
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'packet': ref, 'passed': False, 'reason': str(exc)}))
        return 1
    print(json.dumps({'packet': ref, **result}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
