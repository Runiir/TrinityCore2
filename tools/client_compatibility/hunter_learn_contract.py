"""Exact Beast Lore1462 contract; no gameplay input or fixture writes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import struct

from . import lab_runtime as lab
from .hunter_revive_fixture import dead_snapshot

SPELL = 1462
NAME = 'Beast Lore'
TRAINER = 40
TRAINER_NAME = 'Benjamin Foxworthy'
TRAINER_GUID = 17379592752471406478
PRICE = 646
MONEY = 8708
BASE_SPELLS = [[1515, 1, 0], [79682, 1, 0]]
HUNTER_IDENTITY = (6, 2, 'Harnesshunt', 1, 3, 10)
TRAINER_ROW = [280678, 46983, TRAINER_NAME, 0, -9464.94, 117.432, 58.046, 1.39626, 49, 0, 40]
EFFECT = [460, 6, 0, 121, 0, 0, 1065353216, 1065353216, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 25, 0, 1462, 0, 0]
ABILITY = [7273, 50, 1462, 0, 4, 0, 0, 1, 0, 0, 0, 0, 1, 0]
DBC_HASHES = {
    'Spell': '088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f',
    'SpellEffect': 'e3d9a470bbcb5cea4e3f2947911a908b816cc60e6ffeb9f70b4cfb123bad6252',
    'SkillLineAbility': '6b71b4746e0a950ba0414f53905c308119f0485429240651733747c252fcaadf',
    'Achievement_Criteria': '0e94bf3fba4c12a67289d6712b280dc897a8083c6fd1904d531df41a8a258c70',
}
RELATION_QUERIES = {
    'learn': 'SELECT entry,SpellID,Active FROM client442_world.spell_learn_spell WHERE entry=1462 OR SpellID=1462 ORDER BY entry,SpellID',
    'required': 'SELECT spell_id,req_spell FROM client442_world.spell_required WHERE spell_id=1462 OR req_spell=1462 ORDER BY spell_id,req_spell',
    'pet': 'SELECT spell,effectId,pet,aura FROM client442_world.spell_pet_auras WHERE spell=1462 OR aura=1462 ORDER BY spell,effectId,pet',
    'linked': 'SELECT spell_trigger,spell_effect,type FROM client442_world.spell_linked_spell WHERE ABS(spell_trigger)=1462 OR ABS(spell_effect)=1462 ORDER BY spell_trigger,spell_effect,type',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def owned_snapshot(value, offline=True):
    require(set(value) == {str(g) for g in range(1, 7)}, 'requires the complete six-actor snapshot')
    require(all(v['native']['guid'] == int(g) for g, v in value.items()), 'snapshot actor identity differs')
    if offline:
        require(all(v['native']['online'] == 0 for v in value.values()), 'all six actors must be offline')
    h = value['6']
    require(tuple(h['native'].get(k) for k in ('guid', 'account', 'name', 'race', 'class', 'level')) == HUNTER_IDENTITY,
        'owned Hunter identity differs')
    return h


def untrained_boundary(value):
    h = owned_snapshot(value)
    require(h['native']['money'] == MONEY and h['saved']['spells'] == BASE_SPELLS,
        'untrained Hunter spells or money differ')
    # Validate both exact living pet identities without staging the dead result.
    dead_snapshot(value)
    return h


def dbc_rows(path, fields, stride=None):
    body = Path(path).read_bytes()
    magic, count, width, size, strings = struct.unpack_from('<4s4I', body)
    require(magic == b'WDBC' and width == fields and size == (stride or fields * 4) and
        len(body) == 20 + count * size + strings, 'pinned native DBC layout differs')
    return [list(struct.unpack_from('<' + str(fields) + 'I', body, 20 + n * size)) for n in range(count)]


def static_prerequisites(directory=None):
    directory = Path(directory or lab.ROOT / 'data/dbc/enUS')
    paths = {name: directory / (name + '.dbc') for name in DBC_HASHES}
    require({name: lab.sha256(path) for name, path in paths.items()} == DBC_HASHES,
        'Beast Lore pinned native DBC hashes differ')
    effects = [r for r in dbc_rows(paths['SpellEffect'], 27) if r[24] == SPELL]
    spell = [r for r in dbc_rows(paths['Spell'], 48) if r[0] == SPELL]
    abilities = [r for r in dbc_rows(paths['SkillLineAbility'], 14) if r[2] == SPELL]
    criteria = [r for r in dbc_rows(paths['Achievement_Criteria'], 23, 96)
        if (r[2] == 34 and r[3] == SPELL) or (r[2] in (75, 112) and r[3] == 50)]
    require(len(spell) == 1 and spell[0][1] == 65536 and spell[0][2] == 132096 and
        not spell[0][1] & 0x40 and not spell[0][2] & 0x80000000 and
        effects == [EFFECT] and abilities == [ABILITY] and not criteria,
        'direct1462 effect, acquisition, successor or achievement prerequisite differs')
    return {'dbc_hashes': DBC_HASHES, 'spell': spell, 'effects': effects, 'abilities': abilities, 'matching_criteria': criteria}


def native_prerequisites():
    """Root may execute this read-only fingerprint before any ordinary input."""
    with lab.connection() as con, con.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
            'COALESCE(NULLIF(c.npcflag,0),t.npcflag),c.MovementType,ct.TrainerId '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id '
            'JOIN client442_world.creature_trainer ct ON ct.CreatureId=c.id WHERE c.guid=280678 AND c.id=46983 AND c.map=0')
        trainers = [list(r) for r in q.fetchall()]
        q.execute('SELECT TrainerId,SpellId,MoneyCost,ReqSkillLine,ReqSkillRank,ReqAbility1,ReqAbility2,ReqAbility3,ReqLevel '
            'FROM client442_world.trainer_spell WHERE TrainerId=40 AND SpellId=1462')
        lessons = [list(r) for r in q.fetchall()]
        relations = {}
        for key, query in RELATION_QUERIES.items():
            q.execute(query)
            relations[key] = [list(r) for r in q.fetchall()]
    require(trainers == [TRAINER_ROW] and lessons == [[40, 1462, 680, 0, 0, 0, 0, 0, 10]] and
        not any(relations.values()), 'Beast Lore native trainer or dependency fingerprint differs')
    value = {**static_prerequisites(), 'trainer': trainers, 'lesson': lessons, 'relations': relations}
    return {**value, 'sha256': fingerprint(value)}


def clean_name(value):
    return re.sub(r'\|c[0-9a-fA-F]{8}|\|r', '', value or '').strip()


def book_row(probe, learned):
    rows = [r for r in probe.get('rows', []) if r.get('id') == SPELL]
    require(len(rows) == 1, 'one stock Beast Lore row is required')
    row = rows[0]
    tab = next((r for r in probe.get('tabs', []) if r.get('index') == probe.get('skill_line')), {})
    require(probe.get('visible') is True and probe.get('book_type') == 'spell' and
        tab.get('name') == 'Beast Mastery' and tab.get('checked') is True and
        row.get('id') == row.get('api_id') == row.get('action') == SPELL and
        row.get('kind') == row.get('api_kind') == ('SPELL' if learned else 'FUTURESPELL') and
        row.get('known') is learned and row.get('trainer') is (not learned) and
        clean_name(row.get('shown_name')) == clean_name(row.get('name')) == NAME and
        bool(re.fullmatch(r'SpellButton\d+', row.get('button', ''))), 'stock Beast Lore identity or learned transition differs')
    return row


def learned_checks(rows, before_spells, after_spells, before, after, session, since, until):
    scoped = [p for p in rows if p.get('session') == session and since <= p.get('time', 0) <= until]
    relevant = [p for p in scoped if (p.get('direction'), p.get('name')) in {
        ('to_native', 'CMSG_TRAINER_BUY_SPELL'), ('from_native', 'SMSG_LEARNED_SPELL'),
        ('to_client', 'SMSG_LEARNED_SPELLS')}]
    expected = [('to_native', 'CMSG_TRAINER_BUY_SPELL', struct.pack('<QII', TRAINER_GUID, TRAINER, SPELL).hex()),
        ('from_native', 'SMSG_LEARNED_SPELL', struct.pack('<II', SPELL, 0).hex()),
        ('to_client', 'SMSG_LEARNED_SPELLS', struct.pack('<IIBIB', 1, 0, 0, SPELL, 0).hex())]
    matched = [[p for p in relevant if (p.get('direction'), p.get('name'), p.get('body')) == e] for e in expected]
    exact = len(relevant) == 3 and all(len(v) == 1 for v in matched)
    times = [v[0]['time'] for v in matched] if exact else []
    return {'one_exact_native_purchase': exact,
        'owned_ordered_learn_delivery': exact and times[0] <= times[1] <= times[2] and times[2] - times[1] < 2,
        'no_purchase_failure': not any(p.get('name') == 'SMSG_TRAINER_BUY_FAILED' for p in scoped),
        'saved_direct_spell_only': before_spells == BASE_SPELLS and after_spells == sorted(BASE_SPELLS + [[SPELL, 1, 0]]),
        'exact_charge_resources': before.get('money') == MONEY and after == {**before, 'money': MONEY - PRICE}}


def reconciled_known(login_ids, rows, checks):
    require(SPELL not in login_ids and checks and all(v is True for v in checks.values()),
        'learned authority requires an untrained login and the exact new event')
    native = [p for p in rows if p.get('direction') == 'from_native' and p.get('name') == 'SMSG_LEARNED_SPELL']
    require(len(native) == 1 and native[0].get('body') == struct.pack('<II', SPELL, 0).hex(),
        'exact newly learned native event is absent')
    return set(login_ids) | {SPELL}


def cleanup_expected(before, parked):
    """Permit only the accepted new row and charge; leave accounting untouched."""
    old, now = owned_snapshot(before), owned_snapshot(parked)
    require(old['saved']['spells'] == BASE_SPELLS and old['native']['money'] == MONEY and
        now['saved'] == {**old['saved'], 'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])} and
        now['native']['money'] == MONEY - PRICE and now['inventory'] == old['inventory'] and
        all(parked[str(g)] == before[str(g)] for g in range(1, 6)),
        'offline cleanup refuses unexpected saved, resource or protected changes')
    # Accounting/rest/pose and reload metadata are checked by the source-bound
    # parking closure before this transaction; here they remain exact.
    expected = deepcopy(parked)
    expected['6']['saved']['spells'] = deepcopy(BASE_SPELLS)
    expected['6']['native']['money'] = MONEY
    return expected
