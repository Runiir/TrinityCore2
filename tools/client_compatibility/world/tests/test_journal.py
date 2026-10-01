from tools.client_compatibility.world import events
from tools.client_compatibility.observation.journal import Cursor, entries


def test_live_cursor_reads_rotation_once_and_retains_historical_receipts(tmp_path, monkeypatch):
    path=tmp_path/'packets.jsonl';cursor=Cursor(path)
    monkeypatch.setattr(events,'ROTATE_BYTES',1)
    events.append(path,{'n':1});assert list(cursor.poll())==[{'n':1}]
    events.append(path,{'n':2});events.append(path,{'n':3})
    assert list(cursor.poll())==[{'n':2},{'n':3}]
    assert list(cursor.poll())==[]
    assert list(entries(path))==[{'n':1},{'n':2},{'n':3}]
