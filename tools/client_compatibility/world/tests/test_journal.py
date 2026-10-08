from tools.client_compatibility.world import events
from tools.client_compatibility.observation.journal import Cursor, entries,latest,player_entry
from tools.client_compatibility.observation import journal
import json
from pathlib import Path
import pytest


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


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


@pytest.mark.parametrize('recreate', [True, False])
def test_one_shot_entry_history_keeps_login_chain_rotated_after_enumeration(tmp_path, monkeypatch, recreate):
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    path = tmp_path / 'packets.jsonl'
    old = Path(str(path) + '.part-1')
    rotated = Path(str(path) + '.part-2')
    chain = [{'time': 12 + i / 10, 'session': 'owned', 'name': name, 'direction': direction, 'body': ''}
        for i, (name, direction) in enumerate((('CMSG_PLAYER_LOGIN', 'from_client'),
            ('CMSG_PLAYER_LOGIN', 'to_native'), ('SMSG_LOGIN_VERIFY_WORLD', 'from_native'),
            ('SMSG_LOGIN_VERIFY_WORLD', 'to_client')))]
    write_rows(old, [{'time': 1, 'session': 'foreign'}])
    write_rows(path, chain)
    original = journal.paths
    calls = 0

    def enumerate_then_rotate(source):
        nonlocal calls
        listed = original(source)
        calls += 1
        if calls == 1:
            path.rename(rotated)
            if recreate:
                write_rows(path, [{'time': 21, 'session': 'foreign'}])
        return listed

    monkeypatch.setattr(journal, 'paths', enumerate_then_rotate)
    monkeypatch.setattr(continuation, 'packets', lambda: journal.entries(path))
    assert continuation.history_packets('owned', 10, 20) == chain
    assert calls <= 4


def test_poll_pins_active_inode_before_streaming_older_parts(tmp_path):
    path = tmp_path / 'packets.jsonl'
    write_rows(Path(str(path) + '.part-1'), [{'n': 1}])
    write_rows(path, [{'n': 2}])
    cursor = Cursor(path)
    stream = cursor.poll()
    assert next(stream) == {'n': 1}
    path.rename(Path(str(path) + '.part-2'))
    write_rows(path, [{'n': 3}])
    assert list(stream) == [{'n': 2}]
    assert list(cursor.poll()) == [{'n': 3}]
    assert list(cursor.poll()) == []


def test_continuous_rotation_fails_closed_with_bounded_discovery(tmp_path, monkeypatch):
    path = tmp_path / 'packets.jsonl'
    write_rows(path, [{'n': 0}])
    original = journal.paths
    calls = 0

    def rotate_every_inventory(source):
        nonlocal calls
        listed = original(source)
        calls += 1
        path.rename(Path(str(path) + f'.part-{calls:03}'))
        write_rows(path, [{'n': calls}])
        return listed

    monkeypatch.setattr(journal, 'paths', rotate_every_inventory)
    with pytest.raises(RuntimeError, match='journal.*stabil'):
        list(Cursor(path).poll())
    assert calls <= 8


def test_disappeared_historical_part_cannot_be_silently_skipped(tmp_path, monkeypatch):
    path = tmp_path / 'packets.jsonl'
    part = Path(str(path) + '.part-1')
    write_rows(part, [{'n': 1}])
    write_rows(path, [{'n': 2}])
    original = journal.paths

    def remove_part_after_inventory(source):
        listed = original(source)
        part.unlink()
        return listed

    monkeypatch.setattr(journal, 'paths', remove_part_after_inventory)
    with pytest.raises(RuntimeError, match='historical journal.*disappeared'):
        list(Cursor(path).poll())


def test_partial_current_row_remains_pending_and_appended_row_is_seen_once(tmp_path):
    path = tmp_path / 'packets.jsonl'
    path.write_text('{"n":1}\n{"n":')
    cursor = Cursor(path)
    assert list(cursor.poll()) == [{'n': 1}]
    assert list(cursor.poll()) == []
    with path.open('a') as handle:
        handle.write('2}\n')
    assert list(cursor.poll()) == [{'n': 2}]
    assert list(cursor.poll()) == []


def test_truncation_and_non_missing_open_errors_still_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / 'packets.jsonl'
    write_rows(path, [{'n': 12345}])
    cursor = Cursor(path)
    assert list(cursor.poll()) == [{'n': 12345}]
    path.write_text('{"n":0}\n')
    with pytest.raises(RuntimeError, match='truncated before checkpoint'):
        list(cursor.poll())

    original = Path.open
    def deny(source, *args, **kwargs):
        if source == path:
            raise PermissionError('fixture access denied')
        return original(source, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', deny)
    with pytest.raises(PermissionError, match='fixture access denied'):
        list(Cursor(path).poll())


@pytest.mark.parametrize('fault', ['disappeared', 'replaced'])
def test_retry_retains_pinned_historical_path_and_inode_obligations(tmp_path, monkeypatch, fault):
    path = tmp_path / 'packets.jsonl'
    historical = Path(str(path) + '.part-1')
    rotated = Path(str(path) + '.part-2')
    write_rows(historical, [{'n': 1}])
    write_rows(path, [{'n': 2}])
    original_open = Path.open
    changed = False
    opened = []

    def open_then_change_inventory(source, *args, **kwargs):
        nonlocal changed
        if source == path and not changed:
            changed = True
            historical.unlink()
            if fault == 'replaced':
                with original_open(historical, 'w') as handle:
                    handle.write('{"n":99}\n')
            path.rename(rotated)
            with original_open(path, 'w') as handle:
                handle.write('{"n":3}\n')
        handle = original_open(source, *args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(Path, 'open', open_then_change_inventory)
    with pytest.raises(RuntimeError, match='historical journal.*disappeared|historical journal.*replaced'):
        list(Cursor(path).poll())
    assert changed
    assert all(handle.closed for handle in opened)
