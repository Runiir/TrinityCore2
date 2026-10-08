"""Recovery capture preserves rotated interval evidence without live activity."""
import json
from pathlib import Path

import pytest

from tools.client_compatibility import interaction_bag_swap_offline_boundary as capture
from tools.client_compatibility.world import joins


def records(path, times):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps({'time': time, 'event': 'retained', 'order': i}) + '\n'
        for i, time in enumerate(times)))


def test_complete_interval_crosses_rotations_and_keeps_row_order(tmp_path, monkeypatch):
    monkeypatch.setattr(capture.lab, 'ROOT', tmp_path)
    for member in ('evidence/world_packets.jsonl', 'logs/modern_world.jsonl'):
        path = tmp_path / member
        records(Path(str(path) + '.part-001'), [1, 10, 11])
        records(path, [12, 13, 30])
    out = tmp_path / 'captured'
    out.mkdir()
    refs, observations = capture.journals(out, 10, 13)
    for role in ('packets', 'events'):
        rows = capture.journal_rows(refs[role])
        assert [row['time'] for row in rows] == [10, 11, 12, 13]
        assert [row['order'] for row in rows] == [1, 2, 0, 1]
        assert observations[role]['rows'] == 4
        assert observations[role]['first_time'] == 10
        assert observations[role]['last_time'] == 13
        assert len(observations[role]['rotations']) == 2
        assert observations[role]['source'] == refs[role]


def test_partial_rotated_row_cannot_be_hidden_at_interval_cutoff(tmp_path, monkeypatch):
    monkeypatch.setattr(capture.lab, 'ROOT', tmp_path)
    path = tmp_path / 'evidence/world_packets.jsonl'
    records(path, [10])
    Path(str(path) + '.part-001').write_text('{"time":1}')
    out = tmp_path / 'captured'
    out.mkdir()
    with pytest.raises(RuntimeError, match='partial journal'):
        capture.journals(out, 10, 20)


def test_copy_is_byte_exact_and_never_rewrites_a_prior_diagnostic(tmp_path):
    original = tmp_path / 'source.json'
    original.write_bytes(b'{ "preserve_whitespace": true }\n')
    copied = tmp_path / 'copy.json'
    row = capture.copy_file(original, copied, 1024)
    assert copied.read_bytes() == original.read_bytes()
    assert row['original_source']['sha256'] == row['copy_source']['sha256']
    with pytest.raises(RuntimeError, match='bounded immutable'):
        capture.copy_file(original, copied, 1024)


class SQL:
    def __init__(self, indexes=None):
        self.statements = []
        self.rows = [('ticket_hash', 'binary', 'binary(32)', 'NO', 32, None),
            ('native_id', 'int', 'int(10) unsigned', 'NO', None, None),
            ('key_data', 'binary', 'binary(64)', 'NO', 64, None),
            ('expires', 'bigint', 'bigint(20) unsigned', 'NO', None, None),
            ('consumed', 'tinyint', 'tinyint(1)', 'NO', None, '0')]
        self.indexes = indexes or [('expires', 'expires', 1, 1), ('PRIMARY', 'ticket_hash', 0, 1)]
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self
    def execute(self, text): self.statements.append(text)
    def fetchall(self): return self.rows if len(self.statements) == 1 else self.indexes


def test_existing_schema_verification_issues_only_read_only_metadata_queries(monkeypatch):
    sql = SQL()
    monkeypatch.setattr(joins.lab, 'connection', lambda: sql)
    result = joins.verify_schema()
    assert len(sql.statements) == 2
    assert all(statement.startswith('SELECT ') for statement in sql.statements)
    assert result['ddl_sent'] is result['mutation_sent'] is False


@pytest.mark.parametrize('fault', ['missing_column', 'signed_id', 'missing_index', 'wrong_consumed_default'])
def test_existing_schema_mismatch_fails_closed_without_migration(monkeypatch, fault):
    sql = SQL()
    if fault == 'missing_column': sql.rows.pop()
    elif fault == 'signed_id': sql.rows[1] = ('native_id', 'int', 'int(10)', 'NO', None, None)
    elif fault == 'missing_index': sql.indexes.pop()
    else: sql.rows[4] = ('consumed', 'tinyint', 'tinyint(1)', 'NO', None, '1')
    monkeypatch.setattr(joins.lab, 'connection', lambda: sql)
    with pytest.raises(RuntimeError, match='migration is refused'):
        joins.verify_schema()
    assert all(statement.startswith('SELECT ') for statement in sql.statements)
