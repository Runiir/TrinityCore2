"""Advertise a reviewed public client-table record through normal hotfix messages."""
from functools import lru_cache
import json
from .. import lab_runtime as lab
from ..auth.realms import ADDRESS
from .buffer import Reader,Writer
from .control_skill_metadata import records as control_skills


@lru_cache(maxsize=1)
def records():
    data=json.loads((lab.REPO/'experiments/configs/client_harness/public_portal_hotfix_v1.json').read_text())
    if data['client_build']!=60895:raise ValueError('public hotfix build mismatch')
    rows=data['records']
    if len(rows)!=2 or {(row['table_hash'],row['record_id']) for row in rows}!={(0x1A5081E1,4352),(0x1A5081E1,4354)}:
        raise ValueError('public hotfix allowlist mismatch')
    if any(len(bytes.fromhex(row['data']))!=55 for row in rows):raise ValueError('public portal hotfix layout mismatch')
    return rows+control_skills()


def available():
    rows=records();w=Writer().pack('II',ADDRESS,len(rows))
    for row in rows:w.pack('iI',row['push_id'],row['unique_id'])
    return w.finish()


def lookup(table,entry):
    return next((bytes.fromhex(row['data']) for row in records() if (table,entry)==(row['table_hash'],row['record_id'])),None)


def request(session,body):
    r=Reader(body);build,internal,count=r.unpack('III')
    if build!=60895 or count>512:raise ValueError('unsupported hotfix request build or count')
    ids=set(r.unpack('i'*count));r.end()
    rows=[row for row in records() if row['push_id'] in ids]
    if ids-{row['push_id'] for row in rows}:raise ValueError('unadvertised hotfix requested')
    w=Writer().pack('I',len(rows));data=b''
    for row in rows:
        payload=bytes.fromhex(row['data']);data+=payload
        w.pack('IIIiI',row['push_id'],row['unique_id'],row['table_hash'],row['record_id'],len(payload)).bits(1,3)
    # CONNECT completes the login-time hotfix exchange. MESSAGE has the same
    # record layout but is a later update and leaves character loading pending.
    session.send('SMSG_HOTFIX_CONNECT',w.pack('I',len(data)).raw(data).finish())
