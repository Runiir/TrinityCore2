"""Destructive-path checks use connection-local MariaDB temporary tables only."""
import contextlib
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.bot_ml import sql_telemetry_lifecycle as lifecycle
from tools.bot_ml.export_bot_dataset import export_table


@pytest.fixture
def database():
    config = os.environ.get('TC_SQL_TELEMETRY_TEST_CONFIG')
    if not config:
        pytest.skip('set TC_SQL_TELEMETRY_TEST_CONFIG for MariaDB temporary-table checks')
    conn = lifecycle.connect_mysql(lifecycle.database_url_from_worldserver_conf(Path(config), 'CharacterDatabaseInfo'))
    with conn.cursor() as cursor:
        cursor.execute('CREATE TEMPORARY TABLE experiment_bot_runs '
                       '(id BIGINT PRIMARY KEY, status TEXT, ended_at DATETIME, summary_json TEXT) ENGINE=InnoDB')
        cursor.execute("INSERT INTO experiment_bot_runs VALUES (1,'stopped','2026-09-22','one'),"
                       "(2,'running',NULL,'active'),(3,'stopped','2026-09-22','unexported')")
        for table in lifecycle.TABLES[1:]:
            column = ('parent_run_id' if table.endswith('segments') else
                      'clip_id' if table.endswith('clip_frames') else 'run_id')
            cursor.execute(f'CREATE TEMPORARY TABLE {table} '
                           f'(id BIGINT PRIMARY KEY, {column} BIGINT, payload TEXT, INDEX owner ({column})) ENGINE=InnoDB')
            cursor.execute(f'INSERT INTO {table} VALUES (1,1,\'one\'),(2,2,\'active\'),(3,3,\'unexported\')')
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def counts(conn):
    result = {}
    with conn.cursor() as cursor:
        for table in lifecycle.TABLES:
            cursor.execute(f'SELECT id FROM {table} ORDER BY id')
            result[table] = [r['id'] for r in cursor.fetchall()]
    conn.rollback()
    return result


def archived(conn, tmp_path):
    path = tmp_path / 'run.gz'
    lifecycle.export_run(conn, {'database': 'test'}, 1, path)
    return lifecycle.read_archive(path)


def test_exact_run_deleted_other_active_and_unexported_preserved(database, tmp_path):
    header, summary = archived(database, tmp_path)
    assert lifecycle.purge_verified(database, {'database': 'test'}, header, summary) == 'deleted'
    assert all(v == [2, 3] for v in counts(database).values())
    assert lifecycle.purge_verified(database, {'database': 'test'}, header, summary) == 'already_absent'


@pytest.mark.parametrize('mutation', [
    "UPDATE experiment_bot_events SET payload='changed' WHERE id=1",
    "INSERT INTO experiment_bot_clip_frames VALUES (4,1,'late frame')",
    "UPDATE experiment_bot_runs SET status='running',ended_at=NULL WHERE id=1",
])
def test_changed_or_reactivated_run_never_deleted(database, tmp_path, mutation):
    header, summary = archived(database, tmp_path)
    with database.cursor() as cursor:
        cursor.execute(mutation)
    database.commit()
    before = counts(database)
    with pytest.raises(ValueError):
        lifecycle.purge_verified(database, {'database': 'test'}, header, summary)
    assert counts(database) == before


def test_wrong_database_and_active_export_rejected(database, tmp_path):
    header, summary = archived(database, tmp_path)
    with pytest.raises(ValueError, match='database identity'):
        lifecycle.purge_verified(database, {'database': 'other'}, header, summary)
    with pytest.raises(ValueError, match='not stopped'):
        lifecycle.export_run(database, {}, 2, tmp_path / 'active.gz')
    assert all(v == [1, 2, 3] for v in counts(database).values())


def test_delete_error_rolls_back_all_tables(database, tmp_path, monkeypatch):
    header, summary = archived(database, tmp_path)
    predicate = lifecycle.predicate
    calls = {}
    def fail_late(table):
        calls[table] = calls.get(table, 0) + 1
        # First call is the locking read; the second is the delete, after
        # clip/frame deletion. The entire transaction must roll back.
        if table == 'experiment_bot_events' and calls[table] == 2:
            raise RuntimeError('injected delete failure')
        return predicate(table)
    monkeypatch.setattr(lifecycle, 'predicate', fail_late)
    with pytest.raises(RuntimeError, match='injected'):
        lifecycle.purge_verified(database, {'database': 'test'}, header, summary)
    assert all(v == [1, 2, 3] for v in counts(database).values())


def test_existing_exporter_scopes_frames_and_segments(database):
    for table in ('experiment_bot_clip_frames', 'experiment_bot_segments'):
        assert [r['id'] for r in export_table(database, table, [1])] == [1]


def test_archive_footer_corruption_rejected(database, tmp_path):
    archived(database, tmp_path)
    path = tmp_path / 'run.gz'
    records = gzip.decompress(path.read_bytes()).splitlines()
    footer = json.loads(records[-1]);footer['tables']['experiment_bot_events']['rows'] = 0
    records[-1] = lifecycle.encoded(footer).rstrip()
    path.write_bytes(gzip.compress(b'\n'.join(records) + b'\n'))
    with pytest.raises(ValueError, match='row count/hash'):
        lifecycle.read_archive(path)


@pytest.mark.parametrize('argv', [['--dry-run'], ['--prepare-only'], ['--input-log', 'x'], ['--help']])
def test_offline_modes_do_not_touch_database(monkeypatch, argv):
    def forbidden(*a, **kw):
        raise AssertionError('offline SQL mutation')
    monkeypatch.setattr(lifecycle, 'maintain', forbidden)
    assert lifecycle.run_with_telemetry(lambda: 7, Path('.'), argv) == 7


def test_failed_run_still_publishes_and_startup_only_sweeps(monkeypatch):
    calls = []
    monkeypatch.setattr(lifecycle, 'maintain', lambda *a, **kw: calls.append(kw))
    assert lifecycle.run_with_telemetry(lambda: 2, Path('.'), []) == 2
    assert calls == [{}, {'publish': True}]


def test_legacy_entrypoint_calls_lifecycle(monkeypatch):
    from tools.bot_ml import run_live_bot_validation as runner
    calls = []
    monkeypatch.setattr(lifecycle, 'maintain', lambda *a, **kw: calls.append(kw))
    monkeypatch.setattr(sys, 'argv', ['run_live_bot_validation'])
    monkeypatch.setattr(runner, '_main', lambda: 2)
    assert runner.main() == 2
    assert calls == [{}, {'publish': True}]


def test_uncaught_controller_error_preserves_unexported_sql(monkeypatch):
    calls = []
    monkeypatch.setattr(lifecycle, 'maintain', lambda *a, **kw: calls.append(kw))
    with pytest.raises(RuntimeError, match='controller interrupted'):
        with lifecycle.experiment_telemetry(Path('.'), Path('test.conf')):
            raise RuntimeError('controller interrupted')
    assert calls == [{}]


def test_capture_entrypoint_uses_same_lifecycle(monkeypatch):
    from types import SimpleNamespace
    from tools.raid_program import capture_phase1_raid_foundation as capture
    calls = []
    monkeypatch.setattr(lifecycle, 'maintain', lambda *a, **kw: calls.append(kw))
    monkeypatch.setattr(capture, 'prepare_capture_setup', lambda **kw: SimpleNamespace(config=Path('test.conf')))
    monkeypatch.setattr(capture, 'execute_capture_run', lambda setup: 'run')
    monkeypatch.setattr(capture, 'finalize_capture', lambda setup, run: 2)
    assert capture.main() == 2
    assert calls == [{}, {'publish': True}]


def test_no_receipts_no_database_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, 'connect_mysql', lambda url: pytest.fail('unneeded connection'))
    assert lifecycle.maintain(tmp_path, tmp_path / 'absent.conf')['cleaned'] == []


@pytest.mark.parametrize('fail_remote', [False, True])
def test_real_dvc_publication_and_recovery(database, tmp_path, monkeypatch, fail_remote):
    """Use real DVC and a local remote; no gameplay or production rows."""
    root = tmp_path / 'repo';root.mkdir()
    command = subprocess.run
    command(['git', 'init', '-q', str(root)], check=True)
    command([sys.executable, '-m', 'dvc', 'init', '-q'], cwd=root, check=True)
    command([sys.executable, '-m', 'dvc', 'remote', 'add', '-d', 'test', str(tmp_path / 'remote')],
            cwd=root, check=True, stdout=subprocess.PIPE)
    def run(args, **kwargs):
        if args[:3] == ['pixi', 'run', 'dvc']:
            args = [sys.executable, '-m', 'dvc'] + args[3:]
        return command(args, **kwargs)
    monkeypatch.setattr(lifecycle.subprocess, 'run', run)
    monkeypatch.setattr(lifecycle, 'database_url_from_worldserver_conf', lambda *a: 'mysql://test@localhost/test')
    monkeypatch.setattr(lifecycle, 'connect_mysql', lambda url: database)
    monkeypatch.setattr(database, 'close', lambda: None)
    verify = lifecycle.verify_remote
    if fail_remote:
        monkeypatch.setattr(lifecycle, 'verify_remote', lambda *a: (_ for _ in ()).throw(OSError('remote unavailable')))
        with pytest.raises(OSError, match='remote unavailable'):
            lifecycle.maintain(root, tmp_path / 'unused', publish=True)
        assert all(v == [1, 2, 3] for v in counts(database).values())
        monkeypatch.setattr(lifecycle, 'verify_remote', verify)
        # Unverified leftovers must not authorize startup deletion.
        assert lifecycle.maintain(root, tmp_path / 'unused')['cleaned'] == []
        # Retry the existing upload, without duplicating the run archive.
        assert lifecycle.maintain(root, tmp_path / 'unused', publish=True)['cleaned'] == [1, 3]
        assert len(list((root / lifecycle.DIRECTORY).glob('*.dvc'))) == 2
        assert all(v == [2] for v in counts(database).values())
        return
    # Crash after verified publication but before SQL deletion.
    purge = lifecycle.purge_verified
    monkeypatch.setattr(lifecycle, 'purge_verified', lambda *a: (_ for _ in ()).throw(RuntimeError('crash')))
    with pytest.raises(RuntimeError, match='crash'):
        lifecycle.maintain(root, tmp_path / 'unused', publish=True)
    monkeypatch.setattr(lifecycle, 'purge_verified', purge)
    assert lifecycle.maintain(root, tmp_path / 'unused')['cleaned'] == [1]
    assert all(v == [2, 3] for v in counts(database).values())
    result = lifecycle.maintain(root, tmp_path / 'unused', publish=True)
    assert result['cleaned'] == [3]
    assert all(v == [2] for v in counts(database).values())
    assert not list((root / lifecycle.DIRECTORY).glob('*.jsonl.gz'))
    assert len(list((root / lifecycle.DIRECTORY).glob('*.dvc'))) == 2
