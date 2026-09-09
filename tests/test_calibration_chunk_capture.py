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
