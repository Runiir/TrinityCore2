"""Acceptance tests; fixtures do not establish live DPS or class correctness."""
import hashlib
import json
from pathlib import Path

import pytest

from tools.raid_program import dps_gate


@pytest.mark.parametrize('ratio,passed', [(0.75, False), (0.85, False), (0.94999, False), (0.95, True), (1, True)])
def test_exact_gate_and_dtr_is_not_extra_allowance(ratio, passed):
    result = dps_gate.evaluate(40000 * ratio, 40000, scoring_seconds=300,
        attributable=True, setup_admitted=True, explained_dtr_dps=1000)
    assert result['passed'] is passed
    assert result['required_dps'] == 38000
    assert result['dtr_is_extra_allowance'] is False


@pytest.mark.parametrize('changes', [dict(scoring_seconds=299), dict(scoring_seconds=315),
    dict(attributable=False), dict(setup_admitted=False)])
def test_high_dps_cannot_replace_identity_setup_or_exact_window(changes):
    args = dict(scoring_seconds=300, attributable=True, setup_admitted=True)
    args.update(changes)
    assert not dps_gate.evaluate(50000, 40000, **args)['passed']


@pytest.mark.parametrize('role,mode,passed', [('dps', 'single_target_300', False),
    ('tank', 'tank_threat_300', True), ('healer', 'healer_controlled_damage_300', True)])
def test_current_role_policy_does_not_waive_dps_or_raise_other_role_thresholds(role, mode, passed):
    from tools.bot_ml.role_calibration_harness import evaluate_calibration
    root = Path(__file__).resolve().parents[1]
    policy = json.loads((root/'experiments/configs/all_spec_role_calibration_policy_v3.json').read_text())
    # Other role/setup checks intentionally lack evidence here. Exercise only
    # the numerical reference decision through the real role evaluator.
    result = evaluate_calibration({'role': role, 'mode': mode,
        'metrics': {'reference_value': 40000, 'measured_value': 35000}}, policy)
    assert result['hard_floor_passed'] is passed
    assert result['optimization_target_met'] is passed
    assert not result['passed']  # Missing identity/setup never qualifies a run.


def put(root, name, doc):
    data = json.dumps(doc).encode()
    path = root / name
    path.write_bytes(data)
    return {'path': name, 'sha256': hashlib.sha256(data).hexdigest()}


@pytest.fixture
def packet(tmp_path, monkeypatch):
    from tools.raid_program import raid_workloop, evidence_admission
    raw = {'combat_calibration': {'window_complete': True, 'scored_seconds': 300,
        'target_spec': 'balance_druid', 'bots': [{'guid': 55, 'damage': 11400000}]}}
    native = put(tmp_path, 'native.json', raw)
    run = {'validation_identity': {'actor_id': '1', 'spec': 'balance_druid', 'mode': 'single_target_300'},
        'build_identity': {'source_commit': 'a'*40, 'binary_sha256': 'b'*64},
        'scenario_kind': 'dummy', 'terminal_reason': 'measurement_complete', 'scoring_ms': 300000,
        'closed': True, 'cleanup_verified': True, 'evidence_identity_complete': True,
        'report_summary': {'actor_report_sha256': native['sha256']}}
    sim = {'schema': 'rotation_review_wowsims_result_v1', 'avg_iteration_duration_seconds': 300,
           'player_dps': {'avg': 40000}}
    sim_ref = put(tmp_path, 'sim.json', sim)
    sim_path = sim_ref['sha256']+'.json'
    (tmp_path/'sim.json').rename(tmp_path/sim_path)
    monkeypatch.setattr(raid_workloop, 'build_spec_work_unit', lambda *a: {'benchmark': {
        'state': 'ready', 'accepted_dps': 40000, 'accepted_dps_reference_class': 'self_provided_baseline',
        'rotation_review_reference_artifacts': {k: sim_path for k in ('raid_sim_request', 'raid_sim_result', 'compute_stats')}}})
    # Setup admission has its own behavioral tests; this fixture exercises binding
    # and ratio recomputation against raw native totals, not a copied verdict.
    monkeypatch.setattr(evidence_admission, 'admission', lambda *a: ({'setup_comparison_admitted': True}, {}))
    def make(**changes):
        actual = {**run, **changes}
        return put(tmp_path, 'packet.json', {'actor_id': '1', 'native_actor': '55',
            'native_input': 'native.json', 'run': put(tmp_path, 'run.json', actual)})
    return tmp_path, make, raw


def test_packet_recomputes_exact_bound_native_damage(packet):
    root, make, raw = packet
    result = dps_gate.verify_packet(root, make(), actor_id='1', spec='balance_druid')
    assert result['ratio'] == .95
    raw['combat_calibration']['bots'][0]['damage'] -= 1
    native = put(root, 'native.json', raw)
    with pytest.raises(ValueError, match='95% DPS gate failed'):
        dps_gate.verify_packet(root, make(report_summary={'actor_report_sha256': native['sha256']}), actor_id='1', spec='balance_druid')


@pytest.mark.parametrize('changes,reason', [
    ({'evidence_identity_complete': False}, 'attributable_run'),
    ({'report_summary': {'actor_report_sha256': 'stale'}}, 'not bound'),
    ({'validation_identity': {'actor_id': '1', 'spec': 'balance_druid', 'mode': 'tank_threat_300'}}, 'cannot substitute'),
    ({'scoring_ms': 285000}, 'scoring incomplete'),
    ({'calibration_observation_mode': 'explicit_probe'}, 'diagnostic probe'),
])
def test_packet_rejects_role_or_stale_evidence(packet, changes, reason):
    root, make, _ = packet
    with pytest.raises(ValueError, match=reason):
        dps_gate.verify_packet(root, make(**changes), actor_id='1', spec='balance_druid')


def test_previous_build_cannot_qualify_current_performance(packet):
    root, make, _ = packet
    with pytest.raises(ValueError, match='current validated build'):
        dps_gate.verify_packet(root, make(), actor_id='1', spec='balance_druid',
            expected_build={'source_commit': 'c'*40, 'binary_sha256': 'd'*64})


def test_reviewed_reuse_still_recomputes_the_95_percent_gate(packet, monkeypatch):
    from tools.raid_program import calibration_reuse
    root, make, raw = packet
    calls = []
    monkeypatch.setattr(calibration_reuse, 'verify_compatibility',
        lambda *args, **kwargs: calls.append(kwargs))
    options = dict(actor_id='1', spec='balance_druid',
        expected_build={'source_commit': 'c'*40, 'binary_sha256': 'd'*64},
        compatibility_ref={'path': 'proof.json', 'sha256': 'e'*64},
        validation_identity={'scenario_kind': 'raid', 'boss': 'new_boss'})
    assert dps_gate.verify_packet(root, make(), **options)['ratio'] == .95
    assert calls[0]['validation_identity'] == options['validation_identity']
    raw['combat_calibration']['bots'][0]['damage'] -= 1
    native = put(root, 'native.json', raw)
    with pytest.raises(ValueError, match='95% DPS gate failed'):
        dps_gate.verify_packet(root,
            make(report_summary={'actor_report_sha256': native['sha256']}), **options)


def test_another_roster_actor_needs_reviewed_setup_mapping(packet, monkeypatch):
    from tools.raid_program import calibration_reuse
    root, make, _ = packet
    options = dict(actor_id='another-roster-slot', spec='balance_druid',
        expected_build={'source_commit': 'a'*40, 'binary_sha256': 'b'*64})
    with pytest.raises(ValueError, match='reviewed compatibility required'):
        dps_gate.verify_packet(root, make(), **options)
    calls = []
    monkeypatch.setattr(calibration_reuse, 'verify_compatibility',
        lambda *args, **kwargs: calls.append(kwargs))
    options.update(compatibility_ref={'path': 'proof.json', 'sha256': 'e'*64},
                   validation_identity={'scenario_kind': 'raid', 'boss': 'another_boss'})
    assert dps_gate.verify_packet(root, make(), **options)['ratio'] == .95
    assert calls[0]['actor_id'] == 'another-roster-slot'
    assert json.loads((root/'packet.json').read_text())['actor_id'] == '1'


def test_each_accepted_dps_needs_own_calibration(packet):
    root, make, _ = packet
    graph = {'build_identity': {'source_commit': 'a'*40, 'binary_sha256': 'b'*64},
             'requirements': {'a': {'actor_id': '1', 'role': 'dps', 'spec': 'balance_druid'},
                              'b': {'actor_id': '2', 'role': 'ranged_dps', 'spec': 'fire_mage'}}}
    assessment = {'performance_accepted': True, 'actor_reviews': {
        '1': {'accepted': True, 'dps_calibration': make()}, '2': {'accepted': True}}}
    with pytest.raises(ValueError, match='packet: 2'):
        dps_gate.verify_assessment(root, graph, assessment)
    # An observation repair may proceed while both performance requirements stay open.
    assessment['performance_accepted'] = False
    assert dps_gate.verify_assessment(root, graph, assessment) == {}
