"""Cached credential renewal must not revive expired, revoked or banned tickets."""
import base64
import http.client
import json
import pytest

from tools.client_compatibility.auth import accounts, rpc
from tools.client_compatibility.auth.tests.test_protocol import Writer, rest_server


@pytest.mark.parametrize('stored_expiry', [87400, None])
def test_refresh_keeps_only_hashed_ticket_and_rechecks_expiration(monkeypatch, stored_expiry):
    statements = []
    rows = iter([(stored_expiry,) if stored_expiry else None])

    class Database:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return self
        def execute(self, sql, values): statements.append((sql, values))
        def fetchone(self): return next(rows)

    monkeypatch.setattr(accounts, 'from_ticket', lambda _: {'id': 1, 'expires': 1001, 'mode': 'launcher'})
    monkeypatch.setattr(accounts, 'connection', Database)
    monkeypatch.setattr(accounts.time, 'time', lambda: 1000)
    result = accounts.refresh('TC-public-test-only')
    assert result is None if stored_expiry is None else result['expires'] == stored_expiry
    assert statements[0][1][0] == 87400
    assert isinstance(statements[0][1][1], bytes) and len(statements[0][1][1]) == 32
    assert all('TC-public-test-only' not in str(values) for _, values in statements)
    assert all('expires>%s' in sql for sql, _ in statements)


def test_refresh_rejects_invalid_or_expired_ticket_without_database_update(monkeypatch):
    monkeypatch.setattr(accounts, 'from_ticket', lambda _: None)
    monkeypatch.setattr(accounts, 'connection', lambda: (_ for _ in ()).throw(AssertionError('must not revive a ticket')))
    assert accounts.refresh('TC-public-test-only') is None


def test_cached_rpc_credentials_reject_revocation(monkeypatch):
    session = rpc.Session(None, Writer())
    session.account = {'id': 1, 'expires': 99999}
    session.ticket = 'TC-public-test-only'
    monkeypatch.setattr(accounts, 'refresh', lambda _: None)
    assert session.dispatch('auth', 8, b'') == (3, None)
    assert session.account is None and not session.ticket


def test_rest_refresh_returns_renewed_expiry_and_never_exposes_ticket(rest_server, monkeypatch):
    monkeypatch.setattr(accounts, 'refresh', lambda token: {'id': 1, 'mode': 'launcher', 'expires': 87400}
                        if token == 'TC-public-test-only' else None)
    conn = http.client.HTTPConnection('127.0.0.1', rest_server, timeout=3)
    for token, expected in [('TC-public-test-only', {'login_ticket_expiry': 87400, 'is_expired': False}),
                            ('TC-revoked', {'login_ticket_expiry': 0, 'is_expired': True})]:
        header = base64.b64encode((token + ':').encode()).decode()
        conn.request('POST', '/bnetserver/refreshLoginTicket/', '{}',
                     {'Content-Type': 'application/json', 'Authorization': 'Basic ' + header})
        response = conn.getresponse()
        assert response.status == 200 and json.loads(response.read()) == expected
    conn.close()
