"""Check public crit/ranged stats and stock rows, optionally across a helmet swap."""
import argparse,json,math,re,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require
from .interaction_equipment_sets import detail
from .interaction_equipment_set_roundtrip import open_character,restore_display,stable
from .interaction_character_damage import close
from .interaction_equipment import change
from .interaction_tooltips import baseline
from .observation.inventory import Inventory
from .observation.journal import Cursor
from .world.native_objects import find_self,records
from .world.objects import INDEX


def native(oracle):
    fields=oracle.poll().objects.get(oracle.guid,{})
    def value(name,offset=0,floating=True):
        raw=fields.get(INDEX[name]+offset,0)
        return struct.unpack('<f',struct.pack('<I',raw))[0] if floating else raw
    required=['UNIT_FIELD_RANGEDATTACKTIME','UNIT_FIELD_MINRANGEDDAMAGE',
        'UNIT_FIELD_MAXRANGEDDAMAGE','PLAYER_FIELD_MOD_DAMAGE_DONE_PCT','PLAYER_CRIT_PERCENTAGE']
    if any(INDEX[name] not in fields for name in required):
        raise RuntimeError('native nonzero combat fixture fields are absent')
    speed=value(required[0],floating=False)/1000
    low,high,pct,crit=[value(name) for name in required[1:]]
    if not all(math.isfinite(n) and n>0 for n in [speed,low,high,pct,crit]):
        raise RuntimeError('requires positive finite native combat fixture')
    names=required+['PLAYER_RANGED_CRIT_PERCENTAGE','PLAYER_OFFHAND_CRIT_PERCENTAGE',
        'PLAYER_SHIELD_BLOCK_CRIT_PERCENTAGE']
    return {'crit':crit,'ranged_crit':value('PLAYER_RANGED_CRIT_PERCENTAGE'),
        'spell_crit':[value('PLAYER_SPELL_CRIT_PERCENTAGE1',i) for i in range(7)],
        'ranged_damage':{'speed':speed,'minimum':low,'maximum':high,'percentage':pct,'dps':(low+high)/2/speed},
        'fields':{name:{'index':INDEX[name],'raw':fields.get(INDEX[name],0)} for name in names},
        'school_fields':[{'index':INDEX['PLAYER_SPELL_CRIT_PERCENTAGE1']+i,
            'raw':fields.get(INDEX['PLAYER_SPELL_CRIT_PERCENTAGE1']+i,0)} for i in range(7)]}


def text_value(sheet,category,label):
    clean=lambda value:re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',value or '').strip()
    rows=[r for r in sheet if r.get('category')==category and clean(r.get('label')).removesuffix(':')==label]
    text=clean(rows[0].get('text')) if len(rows)==1 else ''
    try:number=float(text.replace(',','').removesuffix('%'))
    except ValueError:number=None
    return text,number


def verify(t,oracle,label):
    def outcome(b,a,s):
        expected=native(oracle);public=detail(t,label)['stats'];ranged=public.get('ranged_damage') or []
        crit_text,shown_crit=text_value(public['sheet'],'MELEE','Crit Chance')
        dps_text,shown_dps=text_value(public['sheet'],'RANGED','DPS')
        damage=expected['ranged_damage'];schools=public.get('spell_crit') or []
        checks={'ordinary_hover':s=='inspect','public_melee_crit':close(public.get('crit'),expected['crit']),
            'public_ranged_crit':close(public.get('ranged_crit'),expected['ranged_crit']),
            'public_school_crit':len(schools)==7 and all(close(a,b) for a,b in zip(schools,expected['spell_crit'])),
            'public_ranged_damage':len(ranged)==6 and close(ranged[1],damage['minimum']) and close(ranged[2],damage['maximum']),
            'public_ranged_speed':len(ranged)==6 and close(ranged[0],damage['speed'],.001),
            'public_ranged_percentage':len(ranged)==6 and close(ranged[5],damage['percentage'],1e-6),
            'rendered_melee_crit':close(shown_crit,expected['crit']),
            'rendered_ranged_dps':close(shown_dps,damage['dps'],.1),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'character_combat_display_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native':expected,'public':public,
                'rendered_melee_crit_text':crit_text,'rendered_ranged_dps_text':dps_text}}
    row=t.step('character.stats.combat.'+label,'Inspect stock crit and ranged damage against native fields.',
        {'inspect':{'kind':'hover','value':[1110,580],'description':'Move the pointer away from stat rows.'}},
        outcome,diagnostic_action='inspect')
    require(row,'character_combat_display_pass')
    return row['oracle']['native']


def suite(t,roundtrip):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned geared primary warrior')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    original=stable(baseline());t.receipt.update(baseline=original,native_session=session)
    create=None
    for row in Cursor(lab.ROOT/'evidence/world_packets.jsonl').poll():
        if row.get('session')==session and row.get('direction')=='from_native' and row.get('name')=='SMSG_UPDATE_OBJECT':
            if snapshot:=find_self(bytes.fromhex(row['body']),1):
                create={'time':row['time'],'session':session,'body_sha256':row['sha256'],
                    'self_guid':snapshot['guid'],'zero_fields':'Native full self creation omits zero words.'}
    if not create:raise RuntimeError('native full self creation is not attributable')
    t.receipt['native_creation']=create;t.persist();collapsed=None;item=None;destination=None
    try:
        open_character(t,'combat.character')
        collapsed=not any(c['name']=='PaperDollSidebarTab1' for c in controls(t))
        t.receipt['display_baseline']={'collapsed':collapsed};t.persist()
        if collapsed:
            require(click_case(t,'combat.expand','Expand the stock character sidebar.',
                lambda c:c['name']=='CharacterFrameExpandButton',
                lambda b,a,s:{'status':'character_expand_pass' if s and a.get('character_expanded') else
                    'client_or_protocol_failure'},await_state=lambda a:a.get('character_expanded') is True),'character_expand_pass')
        require(click_case(t,'combat.stats','Select the stock character stats sidebar.',
            lambda c:c['name']=='PaperDollSidebarTab1',
            lambda b,a,s:{'status':'character_stats_sidebar_pass' if s and detail(t,'selected_stats')['stats']['sheet'] else
                'client_or_protocol_failure'}),'character_stats_sidebar_pass')
        equipped=verify(t,oracle,'equipped_before')
        if roundtrip:
            item=oracle.equipment(1);empty=[s for s in range(1,17) if not oracle.slot(0,s)['guid']]
            if not item['guid'] or not empty:raise RuntimeError('requires helmet and empty backpack slot')
            destination=(0,empty[-1]);t.receipt['helmet_fixture']={'item':item,'destination':destination};t.persist()
            t.execute({'kind':'key','value':'b'});started=time.time()
            require(change(t,oracle,item,destination),'equipment_change_pass')
            unequipped=verify(t,oracle,'unequipped')
            if close(unequipped['crit'],equipped['crit']):raise RuntimeError('helmet did not change native crit; sparse update remains untested')
            require(change(t,oracle,item,destination,True),'equipment_change_pass')
            restored=verify(t,oracle,'equipped_after')
            if restored!=equipped:raise RuntimeError('native combat fields did not restore')
            updates=[]
            for row in Cursor(lab.ROOT/'evidence/world_packets.jsonl').poll():
                if (row.get('time',0)<started or row.get('session')!=session or
                    row.get('direction')!='from_native' or row.get('name')!='SMSG_UPDATE_OBJECT'):continue
                for record in records(bytes.fromhex(row['body'])):
                    changed={str(i):v for i,v in record.get('fields',{}).items() if 1024<=i<=1035}
                    if record['guid']==1 and record['update_type']==0 and changed:
                        updates.append({'time':row['time'],'sha256':row['sha256'],'fields':changed})
            if not updates:raise RuntimeError('native sparse crit update is not attributable')
            t.receipt['native_sparse_crit_updates']=updates;t.persist()
    finally:
        try:
            if item and destination and not oracle.poll().equipment(1)['guid'] and oracle.slot(*destination)==item:
                require(change(t,oracle,item,destination,True),'equipment_change_pass')
        finally:
            try:restore_display(t,collapsed)
            finally:
                t.receipt['native_after']=stable(baseline());t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
                if not t.receipt['native_resources_preserved']:raise RuntimeError('combat trial did not restore all native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--helmet-roundtrip',action='store_true');a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.helmet_roundtrip);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
