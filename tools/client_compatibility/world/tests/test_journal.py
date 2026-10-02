from tools.client_compatibility.world import events
from tools.client_compatibility.observation.journal import Cursor, entries,latest,player_entry


def test_live_cursor_reads_rotation_once_and_retains_historical_receipts(tmp_path, monkeypatch):
    path=tmp_path/'packets.jsonl';cursor=Cursor(path)
    monkeypatch.setattr(events,'ROTATE_BYTES',1)
    events.append(path,{'n':1});assert list(cursor.poll())==[{'n':1}]
    events.append(path,{'n':2});events.append(path,{'n':3})
    assert list(cursor.poll())==[{'n':2},{'n':3}]
    assert list(cursor.poll())==[]
    assert list(entries(path))==[{'n':1},{'n':2},{'n':3}]


def test_latest_owned_session_reads_newest_rotation_and_skips_incomplete_tail(tmp_path):
    folder=tmp_path/'logs';folder.mkdir();path=folder/'modern_world.jsonl'
    (folder/(path.name+'.part-01')).write_text('invalid old bytes never needed for this match\n')
    (folder/(path.name+'.part-02')).write_text(
        '{"event":"native_player_created","guid":1,"session":"current"}\n')
    path.write_text('{"event":"native_player_created","guid":2,"session":"scout"}\n'
        '{"event":"native_player_created","guid":1,"session":"incomplete"}')
    assert player_entry(tmp_path,1)['session']=='current'
    assert player_entry(tmp_path,2)['session']=='scout'
    assert latest(path,lambda r:r.get('guid')==2)['session']=='scout'
