"""Actual native-console watchdog capture of a slow multi-chunk calibration reply."""
import base64
import inspect
import json
import textwrap
import pytest
from pathlib import Path
from types import SimpleNamespace

from tools.bot_ml import run_live_bot_validation as capture


@pytest.mark.parametrize("split_completion,large_reply", [(False,False),(True,False),(False,True)])
def test_worldserver_watchdog_retains_slow_calibration_reply(tmp_path, monkeypatch, split_completion, large_reply):
    # A response lasting longer than the early-prompt grace still belongs to
    # one command. Its bytes must not be spilled into prefix/cleanup sections.
    payload={'action':'botauto_calibrate_status','ok':True,'cohort_id':'default',
             'server_epoch':17,'attempt_id':1,'window_complete':True,'padding':'x'*1000}
    if large_reply:
        payload['padding']='x'*(1376*12288-256)
    raw=json.dumps(payload,separators=(',',':')).encode()
    chunk_size=12288 if large_reply else 100
    parts=[raw[i:i+chunk_size] for i in range(0,len(raw),chunk_size)]
    if large_reply:
        assert len(parts)==1376
    frames=[json.dumps({'action':'botauto_calibrate_status_chunk','ok':True,'cohort_id':'default',
        'calibration_status_chunk_schema_version':1,'sequence':i,'chunk_count':len(parts),
        'encoding':'base64','data':base64.b64encode(part).decode()},separators=(',',':')) for i,part in enumerate(parts)]
    frames.append(json.dumps({'action':'botauto_calibrate_status_complete','ok':True,'cohort_id':'default',
        'calibration_status_chunk_schema_version':1,'chunk_count':len(parts),'total_bytes':len(raw),'payload_ok':True},separators=(',',':')))
    fake=tmp_path/'console.py'
    fake.write_text('#!/usr/bin/env python3\nimport sys,time\nframes='+repr(frames)+'\nsplit_completion='+repr(split_completion)+'\nframe_delay='+repr(0 if large_reply else 0.11)+'''\nprint('TC> ',flush=True)
for line in sys.stdin:
 command=line.strip()
 if command=='.botauto calibrate status':
  print('TC> ',flush=True)
  for frame in frames:
   if split_completion and 'status_complete' in frame:
    marker='"action":"botauto_calibrate_status_complete"'
    split=frame.index(marker)+len(marker)
    print(frame[:split],end='',flush=True)
    time.sleep(0.15)
    print(frame[split:],flush=True)
   else:
    print(frame,flush=True)
   time.sleep(frame_delay)
 elif command=='.botauto combatlog':
  print('{"action":"botauto_combatlog_complete","chunk_count":0,"total_bytes":0}',flush=True)
 elif command=='.botauto calibrate stop':
  print('{"action":"botauto_calibrate_stop","ok":true}',flush=True)
  print('TC> ',flush=True)
 elif command=='.botauto stop':
  print('{"action":"botauto_stop","ok":true}',flush=True)
  print('TC> ',flush=True)
 elif command.startswith('server shutdown'):
  break
 else:
  print('TC> ',flush=True)
''')
    fake.chmod(0o755)
    # Retain the real launcher, console reader, section buffer and parser.
    # Only terminal policy/persistence are isolated from gameplay validation.
    observed=[]
    def report(*args,**kwargs):
        observed.append(capture.combined_calibration_status(capture.parse_json_objects(args[2])))
        return {'watchdog_state':{},'timed_out':False}
    monkeypatch.setattr(capture,'rolling_heartbeat_report',report)
    monkeypatch.setattr(capture,'advance_semantic_liveness',lambda *a,**k:{'receipt':{},'last_progress_total':0,'last_progress_monotonic':0})
    monkeypatch.setattr(capture,'persist_rolling_heartbeat',lambda *a,**k:None)
    monkeypatch.setattr(capture,'raid_terminal_watchdog_failure',lambda _: 'fixture_terminal')
    monkeypatch.setattr(capture,'finalize_raid_terminal_watchdog',lambda *a,**k:None)
    output,code,timed_out,_=capture.run_worldserver_completion_watchdog(fake,tmp_path/'config',10,
        '.botauto status\n.botauto calibrate status\n.botauto combatlog\n.botauto calibrate stop\n.botauto stop\nserver shutdown force 0\n',tmp_path,{}, {},heartbeat_sec=1)
    assert code==0 and not timed_out
    assert observed[-1][0]==payload
    decoded,transport=capture.combined_calibration_status(capture.parse_json_objects(output))
    assert decoded==payload
    assert 'botauto_calibrate_stop' in output and 'botauto_stop' in output
    assert len(output.encode()) <= capture.DEFAULT_MAX_WORLDSERVER_OUTPUT_BYTES
    assert transport['reassembled'] and transport['received_chunks']==len(parts)


def test_shared_heartbeat_budget_remains_hard_with_cleanup():
    buffer = capture.WatchdogOutputBuffer(max_bytes=1024, heartbeat_commands=['status', 'calibration'])
    buffer.append_heartbeat('status', 's'*20)
    buffer.append_heartbeat('calibration', 'x'*1000)
    buffer.append_cleanup('cleanup-complete')
    assert buffer.truncated
    assert capture.WORLDSERVER_OUTPUT_TRUNCATED_MARKER in buffer.render()
    assert 'cleanup-complete' in buffer.render()
    assert len(buffer.render().encode()) <= 1024
    buffer.append_heartbeat('third', 'z'*1000)
    assert len(buffer.render().encode()) <= 1024


@pytest.mark.parametrize('complete', [False, True])
def test_final_role_gate_distinguishes_native_transport_loss(monkeypatch, complete):
    called=[]
    def evaluate(*args, **kwargs):
        called.append(True)
        return {'identity':{}}, {'passed':False,'failure_reasons':['dps_floor']}
    monkeypatch.setattr(capture,'evaluate_runtime_calibration',evaluate)
    report={'combat_calibration_transport':{'expected_chunks':1376,'received_chunks':1376 if complete else 1265,
             'complete_marker':complete,'reassembled':complete},'calibration_acceptance':{'passed':True},
             'combat_calibration':{},'requested_calibration':{}}
    capture.apply_calibration_only_acceptance(report)
    result=capture.attach_phase8_role_calibration(report)
    capture.AcceptanceRecomputer().recompute(result,identity_required=False,session_required=False)
    assert not result['all_passed']
    assert bool(called)==complete
    if complete:
        assert result['completion_reason']=='combat_calibration_role_gate_failed'
        assert 'role_calibration:dps_floor' in result['failure_labels']
    else:
        assert result['completion_reason']=='infrastructure_loss'
        assert result['failure_labels']==['combat_calibration_transport_incomplete']
        assert not result['role_calibration_evaluation']['evaluated']


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('second_key', ['status', 'unknown'])
def test_exact_fill_followed_by_drop_is_reported(reverse, second_key):
    buffer=capture.WatchdogOutputBuffer(max_bytes=1024,heartbeat_commands=['status','calibration'])
    responses=[('calibration','x'*buffer._heartbeat_budget_bytes),(second_key,'status-response')]
    for key,value in reversed(responses) if reverse else responses:
        buffer.append_heartbeat(key,value)
    buffer.append_cleanup('cleanup-preserved')
    output=buffer.render()
    assert len(output.encode())<=1024
    assert capture.WORLDSERVER_OUTPUT_TRUNCATED_MARKER in output
    report=capture.live_validation_report(output)
    assert 'worldserver_output_truncated' in report['failure_labels']
    assert 'cleanup-preserved' in output
    # Replacing in either order cannot conceal a new dropped response.
    for key,value in responses:
        buffer.append_heartbeat(key,value)
    assert len(buffer.render().encode())<=1024
    assert capture.WORLDSERVER_OUTPUT_TRUNCATED_MARKER in buffer.render()


def test_tiny_watchdog_budget_rejected():
    with pytest.raises(ValueError,match='truncation markers'):
        capture.WatchdogOutputBuffer(max_bytes=1)


@pytest.mark.parametrize('signal', ['complete_marker','received_chunks','attempted'])
def test_incomplete_attempt_survives_acceptance_composition(monkeypatch, signal):
    def forbidden(*a,**k):
        raise AssertionError('role evaluator called for incomplete transport')
    monkeypatch.setattr(capture,'evaluate_runtime_calibration',forbidden)
    report={'combat_calibration_transport':{'expected_chunks':0,signal:True,'reassembled':False},
            'combat_calibration':{},'requested_calibration':{},'calibration_only':True}
    capture.apply_calibration_only_acceptance(report)
    capture.attach_phase8_role_calibration(report)
    capture.AcceptanceRecomputer().recompute(report,identity_required=False,session_required=False)
    assert report['completion_reason']=='infrastructure_loss'
    assert report['failure_reason']=='combat_calibration_transport_incomplete'
    assert not report['all_passed']


def test_malformed_chunk_attempt_and_legitimate_direct_payload():
    direct={'action':'botauto_calibrate_status','ok':True}
    _,transport=capture.combined_calibration_status([direct,{'action':'botauto_calibrate_status_chunk','sequence':'invalid'}])
    assert transport['attempted'] and not transport['direct'] and not transport['reassembled']
    payload,transport=capture.combined_calibration_status([direct])
    assert payload==direct and transport['direct'] and not transport['attempted']


def test_direct_transport_still_evaluates_real_role_gate(monkeypatch):
    called=[]
    def evaluate(*args,**kwargs):
        called.append(True)
        return {'identity':{}},{'passed':False,'failure_reasons':['dps_floor']}
    monkeypatch.setattr(capture,'evaluate_runtime_calibration',evaluate)
    report={'combat_calibration_transport':{'direct':True,'attempted':False,'reassembled':False},
            'combat_calibration':{'action':'botauto_calibrate_status'},'requested_calibration':{},'calibration_only':True}
    capture.apply_calibration_only_acceptance(report)
    capture.attach_phase8_role_calibration(report)
    capture.AcceptanceRecomputer().recompute(report,identity_required=False,session_required=False)
    assert called and report['completion_reason']=='combat_calibration_role_gate_failed'
    assert 'role_calibration:dps_floor' in report['failure_labels']


def test_marker_only_loss_survives_full_acceptance(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('role evaluation after capture truncation')
    monkeypatch.setattr(capture, 'evaluate_runtime_calibration', forbidden)
    report = capture.live_validation_report(capture.WORLDSERVER_OUTPUT_TRUNCATED_MARKER)
    report['calibration_only'] = True
    assert not report['combat_calibration_transport']['attempted']
    capture.apply_calibration_only_acceptance(report)
    capture.attach_phase8_role_calibration(report)
    capture.AcceptanceRecomputer().recompute(report, identity_required=False, session_required=False)
    assert report['completion_reason'] == 'infrastructure_loss'
    assert report['failure_reason'] == 'worldserver_output_truncated'
    assert not report['role_calibration_evaluation']['evaluated']
    assert not report['all_passed']


@pytest.mark.parametrize('initial', ['direct', 'reassembled'])
@pytest.mark.parametrize('malformed', ['chunk', 'complete'])
def test_new_malformed_export_invalidates_previous_authority(monkeypatch, initial, malformed):
    direct = {'action': 'botauto_calibrate_status', 'ok': True, 'cohort_id': 'default'}
    raw = json.dumps(direct).encode()
    chunk = {'action': 'botauto_calibrate_status_chunk', 'cohort_id': 'default',
             'sequence': 0, 'chunk_count': 1, 'encoding': 'base64',
             'calibration_status_chunk_schema_version': 1, 'data': base64.b64encode(raw).decode()}
    complete = {'action': 'botauto_calibrate_status_complete', 'cohort_id': 'default',
                'chunk_count': 1, 'total_bytes': len(raw), 'payload_ok': True,
                'calibration_status_chunk_schema_version': 1}
    prefix = [direct] if initial == 'direct' else [chunk, complete]
    assert capture.combined_calibration_status(prefix)[0] == direct
    broken = {'action': 'botauto_calibrate_status_' + malformed, 'sequence': 'bad', 'chunk_count': 'bad'}
    payload, transport = capture.combined_calibration_status(prefix + [broken])
    assert payload == {} and transport['attempted']
    assert not transport['direct'] and not transport['reassembled']
    def forbidden(*a, **k):
        raise AssertionError('role evaluated stale payload')
    monkeypatch.setattr(capture, 'evaluate_runtime_calibration', forbidden)
    report = {'combat_calibration': payload, 'combat_calibration_transport': transport, 'calibration_only': True}
    capture.apply_calibration_only_acceptance(report)
    capture.attach_phase8_role_calibration(report)
    capture.AcceptanceRecomputer().recompute(report, identity_required=False, session_required=False)
    assert report['completion_reason'] == 'infrastructure_loss' and not report['all_passed']
    # A later complete replacement or direct snapshot is independently authoritative.
    assert capture.combined_calibration_status(prefix + [broken, chunk, complete])[0] == direct
    payload, transport = capture.combined_calibration_status(prefix + [broken, direct])
    assert payload == direct and transport['direct'] and not transport['attempted']


@pytest.mark.parametrize('bad_field,bad_value', [
    ('chunk_count', 'bad'), ('cohort_id', 'another-cohort'),
    ('total_bytes', 1), ('payload_ok', False),
])
def test_rejected_completion_cannot_revive_previous_chunks(bad_field, bad_value):
    payload = {'action': 'botauto_calibrate_status', 'ok': True, 'cohort_id': 'default'}
    raw = json.dumps(payload).encode()
    chunk = {'action': 'botauto_calibrate_status_chunk', 'cohort_id': 'default',
             'sequence': 0, 'chunk_count': 1, 'encoding': 'base64',
             'calibration_status_chunk_schema_version': 1, 'data': base64.b64encode(raw).decode()}
    complete = {'action': 'botauto_calibrate_status_complete', 'cohort_id': 'default',
                'chunk_count': 1, 'total_bytes': len(raw), 'payload_ok': True,
                'calibration_status_chunk_schema_version': 1}
    broken = {**complete, bad_field: bad_value}
    observed, transport = capture.combined_calibration_status([chunk, broken, complete])
    assert observed == {} and not transport['reassembled']
    assert transport['received_chunks'] == 0
    assert capture.combined_calibration_status([chunk, broken, chunk, complete])[0] == payload


@pytest.mark.parametrize('late_truncation', [False, True])
def test_actual_main_final_drain_overrides_precleanup_watchdog_report(tmp_path, monkeypatch, late_truncation):
    direct = {'action': 'botauto_calibrate_status', 'ok': True, 'cohort_id': 'default'}
    before_cleanup = json.dumps(direct) + '\n'
    saved_report = capture.live_validation_report(before_cleanup)
    assert 'worldserver_output_truncated' not in saved_report['failure_labels']
    output = before_cleanup + (capture.WORLDSERVER_OUTPUT_TRUNCATED_MARKER if late_truncation else '')
    called = []

    def evaluate(*args, **kwargs):
        called.append(True)
        return {'identity': {}}, {'passed': False, 'failure_reasons': ['dps_floor']}

    monkeypatch.setattr(capture, 'evaluate_runtime_calibration', evaluate)
    source = inspect.getsource(capture.main)
    start = source.index('    if watchdog_report:', source.index('    retained_console_output ='))
    end = source.index('    if args.transport == "session":\n        attempt =', start)
    # Execute the actual saved-report merge, final-drain inspection, metadata,
    # calibration gates and AcceptanceRecomputer in their production order.
    # Only independent reference/route/build-envelope services are isolated.
    namespace = dict(vars(capture))
    namespace.update(
        watchdog_report=saved_report, output=output,
        parsed_output_payloads=capture.parse_json_objects(output),
        returncode=0, timed_out=False, command=[], incomplete_combat_transport=False,
        config_autostart=False, effective_config=tmp_path/'world.conf',
        pool_tag_filter='all_spec_candidate_pool', exact_party_specs=[],
        validation_route=None, validation_route_manifest=None, validation_route_manifest_path=None,
        send_start_command=True, calibration_reference_preflight={},
        validation_scenario_stage_preflight={}, runtime_asset_closure={},
        preparation={}, session_lifecycle={}, validation_context={},
        args=SimpleNamespace(config=tmp_path/'world.conf', party_pool_tag='all_spec_candidate_pool',
            calibration_only=True, calibration_reference_conditions=False,
            calibration_self_provided_baseline=True, preserve_worldserver=False,
            run_to_completion=False, timeout_sec=900, calibration_mode='single_target_300',
            calibration_target_spec='fire_mage', calibration_seed=1, transport='process',
            output_dir=tmp_path, role_calibration_policy=Path('unused-policy.json')),
        enrich_combat_calibration_reference=lambda value: value,
        build_live_validation_standard_marker=lambda *a: {},
        attach_stonecore_role_quality_audit=lambda *a: None,
        attempt_evidence_envelope=lambda *a: {},
    )
    exec(compile(textwrap.dedent(source[start:end]), str(Path(capture.__file__)), 'exec'), namespace)
    report = namespace['report']
    assert bool(called) is not late_truncation
    assert not report['all_passed']
    if late_truncation:
        assert report['combat_calibration_transport']['capture_truncated']
        assert report['completion_reason'] == 'infrastructure_loss'
        assert report['failure_reason'] == 'worldserver_output_truncated'
    else:
        assert report['completion_reason'] == 'combat_calibration_role_gate_failed'


def test_attempted_incomplete_export_keeps_specific_reason_with_truncation(monkeypatch):
    monkeypatch.setattr(capture, 'evaluate_runtime_calibration',
                        lambda *a, **k: pytest.fail('role evaluation after transport loss'))
    report = {'combat_calibration': {}, 'calibration_only': True,
              'combat_calibration_transport': {'expected_chunks': 1376, 'received_chunks': 1265,
                  'attempted': True, 'reassembled': False, 'capture_truncated': True}}
    capture.apply_calibration_only_acceptance(report)
    capture.attach_phase8_role_calibration(report)
    capture.AcceptanceRecomputer().recompute(report, identity_required=False, session_required=False)
    assert report['completion_reason'] == 'infrastructure_loss'
    assert report['failure_reason'] == 'combat_calibration_transport_incomplete'


def soulburn_receipt(retained, dropped=0):
    return {'schema': 'trinity_affliction_soulburn_decision_telemetry_v1',
            'capacity': 4096, 'attempted': retained + dropped, 'retained': retained,
            'dropped': dropped, 'first_attempted_elapsed_ms': 0,
            'last_attempted_elapsed_ms': (retained + dropped - 1) * 100,
            'first_retained_elapsed_ms': 0, 'last_retained_elapsed_ms': (retained - 1) * 100,
            'complete': dropped == 0}


def frame_calibration_payload(payload):
    raw = json.dumps(payload, separators=(',', ':')).encode()
    parts = [raw[i:i+12288] for i in range(0, len(raw), 12288)]
    frames = [json.dumps({'action': 'botauto_calibrate_status_chunk', 'ok': True,
        'cohort_id': 'default', 'calibration_status_chunk_schema_version': 1,
        'sequence': i, 'chunk_count': len(parts), 'encoding': 'base64',
        'data': base64.b64encode(part).decode()}, separators=(',', ':')) for i, part in enumerate(parts)]
    frames.append(json.dumps({'action': 'botauto_calibrate_status_complete', 'ok': True,
        'cohort_id': 'default', 'calibration_status_chunk_schema_version': 1,
        'chunk_count': len(parts), 'total_bytes': len(raw), 'payload_ok': True}, separators=(',', ':')))
    return '\n'.join(frames) + '\n'


@pytest.fixture(scope='module')
def retained_affliction_payload():
    import os
    directory = Path(os.environ.get('CAP002_CLOSED_AFFLICTION_DIR',
        '/home/runiir/Games/trinity-shared-instance-validation-03cb01db0b/calibration-affliction_warlock-ec02d7196a'))
    log = directory/'worldserver_output.log'
    if not log.is_file():
        pytest.skip('CAP-002 retained closed native payload not available; no hydration')
    output = log.read_text()
    payloads = capture.parse_json_objects(output)
    payload, transport = capture.combined_calibration_status(payloads)
    assert transport['reassembled'] and transport['total_bytes'] == 27504954
    assert len(payload['previous_window']['bots'][0]['affliction_soulburn_decisions']) == 2048
    statuses = [row for row in payloads if row.get('action') == 'botauto_status']
    status = json.dumps(statuses[-1], separators=(',', ':')) + '\n' if statuses else ''
    return payload, status


def extend_closed_soulburn_fixture(payload, dropped=0):
    import copy
    extended = copy.deepcopy(payload)
    # Synthetic size/acceptance fixture only. This does not repair historical
    # evidence or claim these unobserved decisions occurred during that run.
    for bot in [extended['bots'][0], extended['previous_window']['bots'][0],
                extended['best_windows']['single_target'][0]]:
        retained = 4096 if dropped else 3001
        original = bot['affliction_soulburn_decisions']
        bot['affliction_soulburn_decisions'] = [
            {**original[min(i, len(original)-1)], 'elapsed_ms': i * 100}
            for i in range(retained)]
        bot['affliction_soulburn_decision_telemetry'] = soulburn_receipt(retained, dropped)
    return extended


def test_full_300s_affliction_fixture_fits_actual_bounded_controller(retained_affliction_payload):
    original, status = retained_affliction_payload
    payload = extend_closed_soulburn_fixture(original)
    output = frame_calibration_payload(payload)
    buffer = capture.WatchdogOutputBuffer(heartbeat_commands=['status', 'calibration'])
    buffer.append_heartbeat('status', status)
    buffer.append_heartbeat('calibration', output)
    buffer.append_cleanup('cleanup-preserved\n')
    assert not buffer.truncated
    assert len(buffer.render().encode()) <= capture.DEFAULT_MAX_WORLDSERVER_OUTPUT_BYTES
    decoded, transport = capture.combined_calibration_status(capture.parse_json_objects(buffer.render()))
    assert decoded == payload and transport['reassembled']
    print({'synthetic_full_affliction_json_bytes': transport['total_bytes'],
           'chunk_count': transport['received_chunks'], 'framed_bytes': len(output.encode()),
           'latest_status_bytes': len(status.encode()), 'heartbeat_budget_bytes': buffer._heartbeat_budget_bytes,
           'heartbeat_headroom_bytes': buffer._heartbeat_budget_bytes - len(output.encode()) - len(status.encode())})


def assemble_affliction_final_report(tmp_path, payload):
    output = frame_calibration_payload(payload)
    # Direct framing here tests producer loss independently of console capacity.
    # The supported 3,001-row full response has its own bounded-controller test.
    saved_report = capture.live_validation_report(output)
    assert saved_report['combat_calibration_transport']['reassembled']
    source = inspect.getsource(capture.main)
    start = source.index('    if watchdog_report:', source.index('    retained_console_output ='))
    end = source.index('    if args.transport == "session":\n        attempt =', start)
    namespace = dict(vars(capture))
    namespace.update(
        watchdog_report=saved_report, output=output, parsed_output_payloads=capture.parse_json_objects(output),
        returncode=0, timed_out=False, command=[], incomplete_combat_transport=False,
        config_autostart=False, effective_config=tmp_path/'world.conf', pool_tag_filter='all_spec_candidate_pool',
        exact_party_specs=[], validation_route=None, validation_route_manifest=None, validation_route_manifest_path=None,
        send_start_command=True, calibration_reference_preflight={}, validation_scenario_stage_preflight={},
        runtime_asset_closure={}, preparation={}, session_lifecycle={}, validation_context={},
        args=SimpleNamespace(config=tmp_path/'world.conf', party_pool_tag='all_spec_candidate_pool',
            calibration_only=True, calibration_reference_conditions=False, calibration_self_provided_baseline=True,
            preserve_worldserver=False, run_to_completion=False, timeout_sec=900,
            calibration_mode='single_target_300', calibration_target_spec='affliction_warlock',
            calibration_seed=1, transport='process', output_dir=tmp_path,
            role_calibration_policy=Path('experiments/configs/all_spec_role_calibration_policy_v1.json')),
        enrich_combat_calibration_reference=lambda value: value,
        build_live_validation_standard_marker=lambda *a: {}, attach_stonecore_role_quality_audit=lambda *a: None,
        attempt_evidence_envelope=lambda *a: {"identity_complete": True,
            "evidence_class": "synthetic_test_only", "excluded_from_training_corpus": True},
    )
    exec(compile(textwrap.dedent(source[start:end]), str(Path(capture.__file__)), 'exec'), namespace)
    return namespace['report']


@pytest.mark.parametrize('dropped', [0, 1])
def test_closed_affliction_chunks_to_actual_final_acceptance_preserve_diagnostic_gate(
        tmp_path, retained_affliction_payload, dropped):
    payload = extend_closed_soulburn_fixture(retained_affliction_payload[0], dropped)
    report = assemble_affliction_final_report(tmp_path, payload)
    assert report['combat_calibration_transport']['reassembled']
    assert report['role_calibration_evaluation']['passed']
    assert report['role_calibration_record']['metrics']['measured_value'] == pytest.approx(29240.243333333332)
    target = report['combat_calibration']['previous_window']['bots'][0]
    assert target['healer_metrics'] == payload['previous_window']['bots'][0]['healer_metrics']
    assert report['calibration_acceptance']['transport_passed']
    assert report['calibration_acceptance']['diagnostics_passed'] is (dropped == 0)
    assert report['all_passed'] is (dropped == 0)
    assert report['failure_labels'] == (['affliction_soulburn_diagnostics_incomplete'] if dropped else [])


@pytest.mark.parametrize('mutation', [
    lambda bot: bot.pop('affliction_soulburn_decision_telemetry'),
    lambda bot: bot['affliction_soulburn_decision_telemetry'].update(attempted=3002),
    lambda bot: bot['affliction_soulburn_decision_telemetry'].update(retained=1),
    lambda bot: bot['affliction_soulburn_decision_telemetry'].update(complete=False),
    lambda bot: bot['affliction_soulburn_decision_telemetry'].update(dropped=True),
    lambda bot: bot['affliction_soulburn_decision_telemetry'].update(last_retained_elapsed_ms=10),
])
def test_missing_or_inconsistent_soulburn_receipt_is_not_complete(mutation):
    bot = {'guid': 1306, 'attempts': 3001, 'affliction_soulburn_decisions': [
        {'elapsed_ms': i*100} for i in range(3001)],
        'affliction_soulburn_decision_telemetry': soulburn_receipt(3001)}
    mutation(bot)
    report = {'requested_calibration': {'target_spec': 'affliction_warlock', 'mode': 'single_target_300'},
              'combat_calibration': {'target_guid': 1306, 'previous_window': {'bots': [bot]}}}
    capture.apply_calibration_only_acceptance(report)
    assert 'affliction_soulburn_diagnostics_incomplete' in report['failure_labels']


@pytest.mark.parametrize('spec,mode', [('fire_mage', 'single_target_300'),
                                      ('affliction_warlock', 'aoe_300')])
def test_soulburn_receipt_requirement_preserves_other_specs_and_modes(spec, mode):
    report = {'requested_calibration': {'target_spec': spec, 'mode': mode},
              'combat_calibration': {'target_guid': 1306,
                                    'previous_window': {'bots': [{'guid': 1306, 'attempts': 1}]}}}
    capture.apply_calibration_only_acceptance(report)
    assert 'affliction_soulburn_diagnostics_incomplete' not in report['failure_labels']


@pytest.mark.parametrize('dropped', [0, 1])
def test_synthetic_affliction_final_assembly_keeps_diagnostic_gate_without_raw_artifacts(
        tmp_path, monkeypatch, dropped):
    # Permanent compact fixture, never experiment or training evidence. It owns
    # its structural contract and does not read retained/evicted raw artifacts.
    retained = 4096 if dropped else 3001
    bot = {'guid': 1306, 'attempts': retained, 'dps': 29000.0,
           'healer_metrics': {'hps': 388.6},
           'affliction_soulburn_decisions': [{'elapsed_ms': i * 100} for i in range(retained)],
           'affliction_soulburn_decision_telemetry': soulburn_receipt(retained, dropped)}
    payload = {'action': 'botauto_calibrate_status', 'ok': True, 'cohort_id': 'default',
               'window_complete': True, 'phase': 'complete', 'mode': 'single_target_300',
               'target_spec': 'affliction_warlock', 'seed': 1, 'target_guid': 1306,
               'runtime_authority': 'explicit_sql_rule_profiles', 'runtime_mode': 'calibration_fixture',
               'non_certifying_assistance': True, 'generic_ml_runtime_authority': False,
               'reset_applied': True, 'reset_id': 'synthetic-cap002', 'cross_window_event_count': 0,
               'scored_seconds': 300.0, 'scored_started_at_ms': 1000, 'scored_ended_at_ms': 301000,
               'profile_generation': 1, 'profile_content_hash': 'a' * 64,
               'previous_window': {'bots': [bot]}}
    evaluations = []
    record = {'identity': {}, 'metrics': {'measured_value': 29000.0, 'hps': 388.6},
              'evidence_class': 'synthetic_test_only', 'excluded_from_training_corpus': True}
    evaluation = {'passed': True, 'failure_reasons': [], 'reference_ratio': 0.93}

    def evaluate(calibration, **kwargs):
        # Stub only the independent numeric/reference service; production
        # framing, parsing, diagnostics, attachment and final recomputation run.
        assert calibration == payload
        assert kwargs['target_spec'] == 'affliction_warlock'
        evaluations.append(True)
        return record, evaluation

    monkeypatch.setattr(capture, 'evaluate_runtime_calibration', evaluate)
    report = assemble_affliction_final_report(tmp_path, payload)
    assert evaluations == [True]
    assert report['combat_calibration_transport']['reassembled']
    assert report['calibration_acceptance']['transport_passed']
    assert report['role_calibration_record'] == record
    assert report['role_calibration_evaluation'] == evaluation
    assert report['combat_calibration']['previous_window']['bots'][0]['healer_metrics'] == {'hps': 388.6}
    assert report['calibration_acceptance']['diagnostics_passed'] is (dropped == 0)
    assert report['calibration_acceptance']['passed'] is (dropped == 0)
    assert report['all_passed'] is (dropped == 0)
    assert report['acceptable_final_evidence'] is (dropped == 0)
    assert report['failure_labels'] == (['affliction_soulburn_diagnostics_incomplete'] if dropped else [])
