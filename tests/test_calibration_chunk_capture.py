"""Actual native-console watchdog capture of a slow multi-chunk calibration reply."""
import base64
import json
import pytest
from pathlib import Path

from tools.bot_ml import run_live_bot_validation as capture


@pytest.mark.parametrize("split_completion", [False, True])
def test_worldserver_watchdog_retains_slow_calibration_reply(tmp_path, monkeypatch, split_completion):
    # A response lasting longer than the early-prompt grace still belongs to
    # one command. Its bytes must not be spilled into prefix/cleanup sections.
    payload={'action':'botauto_calibrate_status','ok':True,'cohort_id':'default',
             'server_epoch':17,'attempt_id':1,'window_complete':True,'padding':'x'*1000}
    raw=json.dumps(payload,separators=(',',':')).encode()
    parts=[raw[i:i+100] for i in range(0,len(raw),100)]
    frames=[json.dumps({'action':'botauto_calibrate_status_chunk','ok':True,'cohort_id':'default',
        'calibration_status_chunk_schema_version':1,'sequence':i,'chunk_count':len(parts),
        'encoding':'base64','data':base64.b64encode(part).decode()},separators=(',',':')) for i,part in enumerate(parts)]
    frames.append(json.dumps({'action':'botauto_calibrate_status_complete','ok':True,'cohort_id':'default',
        'calibration_status_chunk_schema_version':1,'chunk_count':len(parts),'total_bytes':len(raw),'payload_ok':True},separators=(',',':')))
    fake=tmp_path/'console.py'
    fake.write_text('#!/usr/bin/env python3\nimport sys,time\nframes='+repr(frames)+'\nsplit_completion='+repr(split_completion)+'''\nprint('TC> ',flush=True)
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
   time.sleep(0.11)
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
        '.botauto calibrate status\n',tmp_path,{}, {},heartbeat_sec=1)
    assert code==0 and not timed_out
    assert observed[-1][0]==payload
    decoded,transport=capture.combined_calibration_status(capture.parse_json_objects(output))
    assert decoded==payload
    assert transport['reassembled'] and transport['received_chunks']==len(parts)
