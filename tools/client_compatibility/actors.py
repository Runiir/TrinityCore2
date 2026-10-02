"""Separate normal-account fixtures and owned clients; shared services stay fixed."""
import argparse
import asyncio
import json
import re
import shutil
from . import lab_runtime as lab
from .auth import accounts
from .observation.journal import character_guid


def register(guid):
    guid=character_guid(guid)
    credentials=json.loads((lab.client_root()/'secrets/game_account.json').read_text())
    with lab.connection() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT name,race,class,level FROM client442_characters.characters WHERE guid=%s AND account=%s',
            (guid,credentials['account_id']))
        character=cursor.fetchone()
    if not character:raise ValueError('actor character is not owned by its normal lab account')
    fixture={'schema':'client442_actor_v1','actor':lab.actor_name(),'guid':guid,'account_id':credentials['account_id'],
        'character_name':character[0],'race':character[1],'class':character[2],'level':character[3]}
    lab.private_write(lab.client_root()/'actor.json',json.dumps(fixture,indent=2)+'\n')
    return fixture


def load():
    fixture=json.loads((lab.client_root()/'actor.json').read_text())
    if fixture.get('schema')!='client442_actor_v1' or fixture.get('actor')!=lab.actor_name():
        raise ValueError('actor identity does not match the selected client root')
    character_guid(fixture['guid'])
    return fixture


def session_entry(fixture):
    from .observation.journal import player_entry,entries
    entry=player_entry(lab.ROOT,fixture['guid'])
    authenticated=next((row for row in entries(lab.ROOT/'logs/modern_world.jsonl')
        if row.get('event')=='world_authenticated' and row.get('session')==entry['session']),None)
    if not authenticated or authenticated['account_id']!=fixture['account_id']:
        raise RuntimeError('native actor entry is not bound to its authenticated account')
    return entry


async def create_character(name,race,klass):
    from .world.legacy import Native
    if not re.fullmatch(r'[A-Za-z]{2,12}',name):raise ValueError('fixture character name must be 2-12 ASCII letters')
    credentials=json.loads((lab.client_root()/'secrets/game_account.json').read_text())
    with lab.connection() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT guid FROM client442_characters.characters WHERE account=%s AND name=%s',
            (credentials['account_id'],name))
        existing=cursor.fetchone()
    if existing:return register(existing[0])
    native=Native('fixture_'+lab.actor_name())
    try:
        await asyncio.wait_for(native.connect(credentials['account_id'],credentials['username']),15)
        native.send('CMSG_CHAR_CREATE',name.encode()+b'\0'+bytes([race,klass,0,0,0,0,0,0,0]))
        for _ in range(100):
            opcode,body=await asyncio.wait_for(native.receive(),15)
            if opcode=='SMSG_CREATE_CHAR':
                if body!=bytes([47]):raise RuntimeError('native character creation rejected: '+body.hex())
                break
        else:raise RuntimeError('native character creation response absent')
    finally:await native.close()
    with lab.connection() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT guid FROM client442_characters.characters WHERE account=%s AND name=%s',
            (credentials['account_id'],name));row=cursor.fetchone()
    if not row:raise RuntimeError('created native fixture not persisted')
    return register(row[0])


def provision(name,race,klass):
    if lab.actor_name()=='primary':raise ValueError('register the existing primary; provision a separately named actor')
    if lab.owned_process('client'):raise RuntimeError('cannot provision a running actor client')
    lab.prepare_client()
    addon=lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness'
    shutil.copytree(addon,lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness',dirs_exist_ok=True)
    path=lab.client_root()/'secrets/game_account.json'
    if not path.exists():lab.create_account()
    credentials=json.loads(path.read_text());accounts.migrate();accounts.provision(credentials['username'],credentials['password'])
    print(json.dumps(asyncio.run(create_character(name,race,klass))))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['register','provision','status'])
    p.add_argument('--guid',type=int);p.add_argument('--character');p.add_argument('--race',type=int,default=1)
    p.add_argument('--class',dest='klass',type=int,default=1);a=p.parse_args()
    if a.action=='register':
        if a.guid is None:p.error('register requires --guid')
        print(json.dumps(register(a.guid)))
    elif a.action=='provision':
        if not a.character:p.error('provision requires --character')
        provision(a.character,a.race,a.klass)
    else:print(json.dumps({'actor':lab.actor_name(),'root':str(lab.client_root()),'client':lab.owned_process('client')}))


if __name__=='__main__':main()
