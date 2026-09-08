"""Execute the live contract's SQL against native-shaped local tables."""
import sqlite3
from pathlib import Path

import pytest

from tools.bot_ml import build_phase4_rotation_contract as contract


class Cursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()
        self.columns = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.close()

    def execute(self, sql):
        self.columns = None
        if sql == 'SHOW COLUMNS FROM bot_rotation_action':
            self.columns = [{'Field': row[1]} for row in self.cursor.execute(
                'PRAGMA table_info(bot_rotation_action)')]
        else:
            self.cursor.execute(sql)

    def fetchall(self):
        return self.columns if self.columns is not None else [dict(r) for r in self.cursor.fetchall()]

    def fetchone(self):
        return dict(self.cursor.fetchone())


class Connection:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return Cursor(self.db)

    def close(self):
        pass  # pytest owns the in-memory connection lifetime


@pytest.fixture
def database(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE bot_rotation_profile (id INTEGER PRIMARY KEY, class_id INTEGER, spec_tag TEXT, role TEXT, enabled INTEGER)')
    columns = ', '.join(f'"{column}" INTEGER' for column in sorted(contract.TYPED_COLUMNS))
    db.execute(f'CREATE TABLE bot_rotation_action (id INTEGER PRIMARY KEY, profile_id INTEGER, category TEXT, enabled INTEGER, {columns})')
    for profile_id, key in enumerate(sorted(contract.EXPECTED_KEYS), 1):
        class_id, spec, role = key.split(':')
        db.execute('INSERT INTO bot_rotation_profile VALUES (?,?,?,?,1)', (profile_id, int(class_id), spec, role))
    monkeypatch.setattr(contract, 'database_url_from_worldserver_conf', lambda *args: 'local')
    monkeypatch.setattr(contract, 'connect_mysql', lambda url: Connection(db))
    yield db
    db.close()


def populate(db, total, *, empty_profile=False):
    count = 30 if empty_profile else 31
    category = sorted(contract.KNOWN_CATEGORIES)[0]
    db.executemany('INSERT INTO bot_rotation_action (id,profile_id,category,enabled) VALUES (?,?,?,1)',
                   [(index + 1, index % count + 1, category) for index in range(total)])


@pytest.mark.parametrize('total', [260, 368])
def test_every_profile_covered_passes_independent_of_action_total(database, total):
    populate(database, total)
    result = contract.live_database_contract(Path('unused.conf'))
    assert result['passed']
    assert result['action_count'] == total
    assert result['profile_count'] == 31
    assert result['missing_action_profile_ids'] == []


@pytest.mark.parametrize('disabled_action', [False, True])
def test_empty_enabled_profile_fails_even_at_historical_total(database, disabled_action):
    populate(database, 260, empty_profile=True)
    if disabled_action:
        database.execute("INSERT INTO bot_rotation_action (id,profile_id,category,enabled) VALUES (261,31,'damage',0)")
    result = contract.live_database_contract(Path('unused.conf'))
    assert not result['passed']
    assert not result['checks']['enabled_actions_present']
    assert result['action_count'] == 260
    assert result['missing_action_profile_ids'] == [31]


@pytest.mark.parametrize('drift', ['profile_key', 'category'])
def test_existing_identity_and_category_guards_remain(database, drift):
    populate(database, 368)
    if drift == 'profile_key':
        database.execute("UPDATE bot_rotation_profile SET spec_tag='unknown_spec' WHERE id=1")
        failed = 'exact_catalog_keys'
    else:
        database.execute("UPDATE bot_rotation_action SET category='unknown_category' WHERE id=1")
        failed = 'all_categories_known'
    result = contract.live_database_contract(Path('unused.conf'))
    assert not result['passed']
    assert not result['checks'][failed]
    assert result['checks']['enabled_actions_present']
