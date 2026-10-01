import json
from pathlib import Path
from tools.client_compatibility.observation.archaeology import collected
from tools.client_compatibility import lab_runtime as lab


def test_collection_reports_awarded_fragments_not_total_balance(tmp_path,monkeypatch):
    fixture=Path(__file__).with_name('fixtures')/'archaeology_collection.json'
    replies=json.loads(fixture.read_text());(tmp_path/'evidence').mkdir()
    (tmp_path/'evidence/world_packets.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in replies))
    monkeypatch.setattr(lab,'ROOT',tmp_path)
    result=collected(replies[0]['session'],replies[0]['time'])
    assert result['currency']==394 and result['quantity']==5 and result['balance']==13
    assert collected('another-session',0) is None
