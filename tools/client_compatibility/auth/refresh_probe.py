"""Live REST renewal using disposable owned credentials, never persisted in evidence."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from . import accounts
from .. import lab_runtime as lab


def probe(output):
    if output.exists():
        raise RuntimeError('renewal evidence path already exists')
    saved = json.loads((lab.client_root() / 'secrets/game_account.json').read_text())
    account = accounts.check_password(saved['username'], saved['password'])
    if not account:
        raise RuntimeError('owned login credentials are invalid')
    receipt = {'source': 'code_fixture_live_rest', 'started_at': time.time(),
               'account_id': account['id'], 'completed': False, 'cases': []}
    token = accounts.issue(account, 'launcher')
    digest = hashlib.sha256(token.encode()).digest()
    try:
        for label, seconds in [('valid_near_expiry', 30), ('expired', -1)]:
            now = int(time.time())
            with lab.connection() as con, con.cursor() as cur:
                cur.execute('UPDATE client442_auth.lab_login_tickets SET expires=%s WHERE ticket_hash=%s',
                            (now + seconds, digest))
            header = base64.b64encode((token + ':').encode()).decode()
            request = urllib.request.Request('http://127.0.0.1:18081/bnetserver/refreshLoginTicket/',
                data=b'{}', headers={'Content-Type': 'application/json', 'Authorization': 'Basic ' + header})
            with urllib.request.urlopen(request, timeout=3) as response:
                result = json.load(response)
            expected = (result['is_expired'] and result['login_ticket_expiry'] == 0) if seconds < 0 else (
                not result['is_expired'] and result['login_ticket_expiry'] >= now + accounts.TICKET_DURATION)
            receipt['cases'].append({'id': label, 'before_expiry': now + seconds,
                                    'response': result, 'passed': expected})
            if not expected:
                raise RuntimeError('live login renewal result differs from expected expiration behavior')
        receipt['completed'] = True
    finally:
        with lab.connection() as con, con.cursor() as cur:
            cur.execute('DELETE FROM client442_auth.lab_login_tickets WHERE ticket_hash=%s', (digest,))
            cur.execute('SELECT COUNT(*) FROM client442_auth.lab_login_tickets WHERE ticket_hash=%s', (digest,))
            receipt['disposable_ticket_removed'] = cur.fetchone()[0] == 0
        receipt['finished_at'] = time.time()
        lab.private_write(output, json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'completed': receipt['completed'], 'disposable_ticket_removed': receipt['disposable_ticket_removed']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    probe(parser.parse_args().output)
