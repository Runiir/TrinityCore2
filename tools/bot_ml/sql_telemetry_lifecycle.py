"""Archive closed SQL experiment telemetry, verify DVC remotely, then delete it.

SQL is a staging area. Run status alone never authorizes deletion; the exact
current rows must match a freshly read remote archive under database locks.
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

from tools.bot_ml.extract_world_knowledge import (
    connect_mysql, database_url_from_worldserver_conf, sanitize_database_url,
)

TABLES = (
    'experiment_bot_runs', 'experiment_bot_segments', 'experiment_bot_events',
    'experiment_bot_decisions', 'experiment_bot_activities',
    'experiment_bot_replay_records', 'experiment_bot_clips', 'experiment_bot_clip_frames',
)
DIRECTORY = Path('artifacts/cata_raid_program/sql_telemetry')


def encoded(value):
    return (json.dumps(value, sort_keys=True, default=str, separators=(',', ':')) + '\n').encode()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def predicate(table):
    if table not in TABLES:
        raise ValueError('not an experiment telemetry table')
    if table == 'experiment_bot_runs':
        return 'id = %s'
    if table == 'experiment_bot_segments':
        return 'parent_run_id = %s'
    if table == 'experiment_bot_clip_frames':
        return 'clip_id IN (SELECT id FROM experiment_bot_clips WHERE run_id = %s)'
    return 'run_id = %s'


def rows(conn, table, run_id, *, lock=False):
    from pymysql.cursors import SSDictCursor
    with conn.cursor(SSDictCursor) as cursor:
        cursor.execute(f'SELECT * FROM `{table}` WHERE {predicate(table)} ORDER BY id'
                       + (' FOR UPDATE' if lock else ''), (run_id,))
        yield from cursor


def run_row(conn, run_id, *, lock=False):
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM experiment_bot_runs WHERE id = %s'
                       + (' FOR UPDATE' if lock else ''), (run_id,))
        return cursor.fetchone()


def require_closed(row):
    if not row or row['status'] != 'stopped' or row['ended_at'] is None:
        raise ValueError('SQL telemetry run is not stopped with an ended_at timestamp')


def export_run(conn, database, run_id, path):
    """Stream one consistent snapshot, including frames joined through clips."""
    conn.begin()
    try:
        run = run_row(conn, run_id)
        require_closed(run)
        header = {'schema': 'sql_telemetry_archive_v1', 'database': database,
                  'run_id': run_id, 'run': run, 'training_admission': 'unclassified'}
        summary = {}
        with gzip.open(path, 'wb') as stream:
            stream.write(encoded({'header': header}))
            for table in TABLES:
                digest = hashlib.sha256()
                count = 0
                with conn.cursor() as cursor:
                    cursor.execute(f'SHOW CREATE TABLE `{table}`')
                    ddl = cursor.fetchone()['Create Table']
                stream.write(encoded({'table_schema': table, 'ddl': ddl}))
                for row in rows(conn, table, run_id):
                    digest.update(encoded(row))
                    stream.write(encoded({'table': table, 'row': row}))
                    count += 1
                summary[table] = {'rows': count, 'sha256': digest.hexdigest()}
            stream.write(encoded({'tables': summary}))
        return header, summary
    finally:
        conn.rollback()


def read_archive(path):
    """Validate table membership and row digests from actual remote bytes."""
    digests = {t: hashlib.sha256() for t in TABLES}
    counts = dict.fromkeys(TABLES, 0)
    footer = None
    with gzip.open(path, 'rb') as stream:
        header = json.loads(next(stream))['header']
        if header['schema'] != 'sql_telemetry_archive_v1':
            raise ValueError('unknown SQL telemetry archive')
        for line in stream:
            event = json.loads(line)
            if footer is not None:
                raise ValueError('records after archive footer')
            if 'table' in event:
                table = event['table']
                digests[table].update(encoded(event['row']))
                counts[table] += 1
            elif 'tables' in event:
                footer = event['tables']
    observed = {t: {'rows': counts[t], 'sha256': digests[t].hexdigest()} for t in TABLES}
    if observed != footer or counts['experiment_bot_runs'] != 1:
        raise ValueError('SQL archive row count/hash mismatch')
    return header, observed


def verify_remote(root, pointer):
    """Read the remote directly. A local cache hit is not verification."""
    import yaml
    from dvc.repo import Repo
    entry, = yaml.safe_load(pointer.read_text())['outs']
    with Repo(str(root)) as repo, tempfile.TemporaryDirectory(prefix='sql-telemetry-verify-') as temp:
        remote = repo.cloud.get_remote_odb()
        path = Path(temp) / 'remote.jsonl.gz'
        digest = hashlib.md5()
        size = 0
        with remote.fs.open(remote.oid_to_path(entry['md5']), 'rb') as source, path.open('wb') as dest:
            while block := source.read(1024 * 1024):
                digest.update(block)
                size += len(block)
                dest.write(block)
        if digest.hexdigest() != entry['md5'] or size != entry['size']:
            raise ValueError('SQL telemetry remote bytes differ from DVC pointer')
        return read_archive(path)


def purge_verified(conn, database, header, expected):
    if header['database'] != database:
        raise ValueError('SQL telemetry database identity mismatch')
    run_id = header['run_id']
    conn.begin()
    try:
        current = run_row(conn, run_id, lock=True)
        if current is None:
            conn.rollback()
            return 'already_absent'
        require_closed(current)
        if encoded(current) != encoded(header['run']):
            raise ValueError('SQL run changed since export; preserving rows')
        # Lock the selected ranges until delete commits. Compare every row,
        # not just counts, so late writes and edits cannot be silently lost.
        for table in TABLES:
            digest = hashlib.sha256()
            count = 0
            for row in rows(conn, table, run_id, lock=True):
                digest.update(encoded(row))
                count += 1
            if expected[table] != {'rows': count, 'sha256': digest.hexdigest()}:
                raise ValueError(f'{table} changed since export; preserving rows')
        with conn.cursor() as cursor:
            for table in reversed(TABLES):
                cursor.execute(f'DELETE FROM `{table}` WHERE {predicate(table)}', (run_id,))
                if cursor.rowcount != expected[table]['rows']:
                    raise ValueError('SQL cleanup row count changed; rolling back')
        conn.commit()
        return 'deleted'
    except BaseException:
        conn.rollback()
        raise


def evict(root, pointer):
    import yaml
    from dvc.repo import Repo
    entry, = yaml.safe_load(pointer.read_text())['outs']
    (pointer.parent / entry['path']).unlink(missing_ok=True)
    with Repo(str(root)) as repo:
        Path(repo.cache.local.oid_to_path(entry['md5'])).unlink(missing_ok=True)


def publish_archive(root, archive, pointer):
    from tools.bot_ml.live_validation_session import dvc_repository_lock
    with dvc_repository_lock(root):
        commands = ('status', 'push') if pointer.exists() else ('add', 'status', 'push')
        for command in commands:
            target = archive if command == 'add' else pointer
            subprocess.run(['pixi', 'run', 'dvc', command, str(target.relative_to(root))],
                           cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return verify_remote(root, pointer)


def maintain(root, config, *, publish=False):
    """Sweep verified leftovers; optionally publish and clean other closed runs."""
    root, config = Path(root).resolve(), Path(config).resolve()
    folder = root / DIRECTORY
    receipts = sorted(folder.glob('*.receipt.json'))
    pending = [p for p in receipts if not json.loads(p.read_text()).get('cleanup')]
    if not publish and not pending:
        return {'cleaned': [], 'unexported_preserved': True}
    url = database_url_from_worldserver_conf(config, 'CharacterDatabaseInfo')
    database = sanitize_database_url(url)
    database.pop('user')
    conn = connect_mysql(url)
    cleaned = []
    lock = 'sql-telemetry-' + hashlib.sha256(encoded(database)).hexdigest()[:32]
    try:
        with conn.cursor() as cursor:
            cursor.execute('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute('SET SESSION innodb_lock_wait_timeout = 5')
            cursor.execute('SELECT GET_LOCK(%s, 5) AS acquired', (lock,))
            if cursor.fetchone()['acquired'] != 1:
                raise RuntimeError('another SQL telemetry cleanup is running')
        for path in pending:
            receipt = json.loads(path.read_text())
            if receipt['database'] != database:
                continue
            pointer = root / receipt['pointer']
            if not receipt.get('remote_verified'):
                if not publish:
                    continue
                header, summary = publish_archive(root, root / receipt['archive'], pointer)
                receipt['remote_verified'] = True
                save(path, receipt)
            else:
                header, summary = verify_remote(root, pointer)
            receipt['cleanup'] = purge_verified(conn, database, header, summary)
            evict(root, pointer)
            save(path, receipt)
            cleaned.append(header['run_id'])
        if publish:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM experiment_bot_runs WHERE status = 'stopped' AND ended_at IS NOT NULL ORDER BY id")
                ids = [row['id'] for row in cursor.fetchall()]
            conn.rollback()
            folder.mkdir(parents=True, exist_ok=True)
            for run_id in ids:
                with tempfile.TemporaryDirectory(prefix='sql-telemetry-export-') as temp:
                    draft = Path(temp) / 'run.jsonl.gz'
                    header, _ = export_run(conn, database, run_id, draft)
                    # Include bytes, so a changed run never overwrites a published snapshot.
                    with draft.open('rb') as stream:
                        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                    path = folder / f'run-{run_id}-{digest[:20]}.jsonl.gz'
                    shutil.move(str(draft), path)
                pointer = path.with_name(path.name + '.dvc')
                receipt_path = path.with_name(path.name + '.receipt.json')
                receipt = {'database': database, 'run_id': run_id,
                           'archive': str(path.relative_to(root)),
                           'pointer': str(pointer.relative_to(root)), 'remote_verified': False}
                save(receipt_path, receipt)
                remote_header, summary = publish_archive(root, path, pointer)
                receipt['remote_verified'] = True
                save(receipt_path, receipt)
                receipt['cleanup'] = purge_verified(conn, database, remote_header, summary)
                evict(root, pointer)
                save(receipt_path, receipt)
                cleaned.append(run_id)
        return {'cleaned': cleaned, 'unexported_preserved': True}
    finally:
        conn.rollback()
        with conn.cursor() as cursor:
            cursor.execute('SELECT RELEASE_LOCK(%s)', (lock,))
        conn.close()


@contextlib.contextmanager
def experiment_telemetry(root, config):
    maintain(root, config)
    yield
    # A normal failed-run result is still closed evidence. An uncaught
    # controller/preflight exception leaves SQL intact for explicit recovery.
    maintain(root, config, publish=True)


def run_with_telemetry(callback, root, argv=None):
    """Wrap the legacy runner without enabling writes for offline/dry modes."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--config', type=Path, default=Path('trinity-worldserver-test.conf'))
    parser.add_argument('--input-log')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--help', '-h', action='store_true')
    args, _ = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    if args.input_log or args.dry_run or args.prepare_only or args.help:
        return callback()
    with experiment_telemetry(root, args.config):
        return callback()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['sweep', 'publish'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--config', type=Path, default=Path('trinity-worldserver-test.conf'))
    args = parser.parse_args()
    print(json.dumps(maintain(args.root, args.config, publish=args.action == 'publish')))


if __name__ == '__main__':
    main()
