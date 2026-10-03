"""Native/public/rendered character ratings checks with ordinary helmet inputs."""
import argparse,hashlib,json,math,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require
from .interaction_equipment_sets import detail
from .interaction_equipment_set_roundtrip import open_character,restore_display,stable
from .interaction_equipment import change
from .interaction_character_combat import text_value
from .interaction_character_damage import close
from .interaction_tooltips import baseline
from .observation.inventory import Inventory
from .observation.journal import Cursor
from .world.native_objects import find_self,records
from .world.objects import INDEX

SUPPORTED={*range(2,11),14,15,17,18,19,23,25}


def native(oracle):
    fields=oracle.poll().objects.get(1,{})
    def value(name,floating=True):
        raw=fields.get(INDEX[name],0)
        return struct.unpack('<f',struct.pack('<I',raw))[0] if floating else raw
    names=['PLAYER_FIELD_MOD_HASTE','PLAYER_FIELD_MOD_RANGED_HASTE','PLAYER_MASTERY','PLAYER_EXPERTISE',
        'PLAYER_OFFHAND_EXPERTISE','PLAYER_DODGE_PERCENTAGE','PLAYER_PARRY_PERCENTAGE']
    if any(INDEX[n] not in fields for n in names):raise RuntimeError('requires the nonzero geared native stats fixture')
    haste,ranged=value(names[0]),value(names[1])
    if not all(math.isfinite(n) and n>0 for n in [haste,ranged]):raise RuntimeError('native haste multiplier invalid')
    return {'melee_haste':(1/haste-1)*100,'ranged_haste':(1/ranged-1)*100,
        'haste_multiplier':haste,'ranged_haste_multiplier':ranged,'mastery':value('PLAYER_MASTERY'),
        'expertise':[value('PLAYER_EXPERTISE',False),value('PLAYER_OFFHAND_EXPERTISE',False)],
        'dodge':value('PLAYER_DODGE_PERCENTAGE'),'parry':value('PLAYER_PARRY_PERCENTAGE'),
        'ratings':[fields.get(INDEX['PLAYER_FIELD_COMBAT_RATING_1']+i,0) if i in SUPPORTED else 0 for i in range(26)],
        'crit':value('PLAYER_CRIT_PERCENTAGE'),'ranged_speed':value('UNIT_FIELD_RANGEDATTACKTIME',False)/1000,
        'fields':{n:{'index':INDEX[n],'raw':fields[INDEX[n]]} for n in names}}


def verify(t,oracle,label):
    def outcome(b,a,s):
        expected=native(oracle);public=detail(t,label)['stats'];sheet=public['sheet'];expertise=public.get('expertise') or []
        haste_text,haste=text_value(sheet,'MELEE','Haste');mastery_text,mastery=text_value(sheet,'MELEE','Mastery')
        expertise_text,shown_expertise=text_value(sheet,'MELEE','Expertise')
        checks={'ordinary_hover':s=='inspect','public_melee_haste':close(public.get('melee_haste'),expected['melee_haste']),
            'public_ranged_haste':close(public.get('ranged_haste'),expected['ranged_haste']),
            'public_mastery':close(public.get('mastery'),expected['mastery']),
            'public_main_expertise':bool(expertise) and close(expertise[0],expected['expertise'][0]),
            'public_ratings':public.get('ratings')==expected['ratings'],
            'public_dodge':close(public.get('dodge'),expected['dodge']),
            'public_parry':close(public.get('parry'),expected['parry']),
            'rendered_melee_haste':close(haste,expected['melee_haste']),
            'rendered_mastery':close(mastery,expected['mastery']),
            'rendered_main_expertise':close(shown_expertise,expected['expertise'][0]),
            'existing_crit_preserved':close(public.get('crit'),expected['crit']),
            'existing_ranged_speed_preserved':bool(public.get('ranged_damage')) and close(public['ranged_damage'][0],expected['ranged_speed'],.001),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'character_ratings_display_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native':expected,'public':public,
                'rendered':{'melee_haste':haste_text,'mastery':mastery_text,'expertise':expertise_text},
                'offhand_expertise_if_reported':len(expertise)==2 and close(expertise[1],expected['expertise'][1])}}
    row=t.step('character.stats.ratings.'+label,'Inspect native ratings, haste, expertise, mastery and defense.',
        {'inspect':{'kind':'hover','value':[1110,580],'description':'Move the pointer away from stat rows.'}},
        outcome,diagnostic_action='inspect');require(row,'character_ratings_display_pass');return row['oracle']['native']


def suite(t,roundtrip):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned geared primary warrior')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    original=stable(baseline());t.receipt.update(baseline=original,native_session=session);creation=None
    for row in Cursor(lab.ROOT/'evidence/world_packets.jsonl').poll():
        if row.get('session')==session and row.get('direction')=='from_native' and row.get('name')=='SMSG_UPDATE_OBJECT':
            if find_self(bytes.fromhex(row['body']),1):
                creation={'time':row['time'],'session':session,'body_sha256':hashlib.sha256(bytes.fromhex(row['body'])).hexdigest()}
    if not creation:raise RuntimeError('native full creation is not attributable')
    t.receipt['native_creation']=creation;t.persist();collapsed=None;item=destination=None
    try:
        open_character(t,'ratings.character');collapsed=not any(c['name']=='PaperDollSidebarTab1' for c in controls(t))
        t.receipt['display_baseline']={'collapsed':collapsed};t.persist()
        if collapsed:
            require(click_case(t,'ratings.expand','Expand the stock character sidebar.',
                lambda c:c['name']=='CharacterFrameExpandButton',
                lambda b,a,s:{'status':'character_expand_pass' if s and a.get('character_expanded') else
                    'client_or_protocol_failure'},await_state=lambda a:a.get('character_expanded') is True),'character_expand_pass')
        require(click_case(t,'ratings.stats','Select stock character stats.',lambda c:c['name']=='PaperDollSidebarTab1',
            lambda b,a,s:{'status':'character_stats_sidebar_pass' if s and detail(t,'selected_stats')['stats']['sheet'] else
                'client_or_protocol_failure'}),'character_stats_sidebar_pass')
        equipped=verify(t,oracle,'equipped_before')
        if roundtrip:
            item=oracle.equipment(1);empty=[s for s in range(1,17) if not oracle.slot(0,s)['guid']]
            if not item['guid'] or not empty:raise RuntimeError('requires helmet and empty backpack slot')
            destination=(0,empty[-1]);t.receipt['helmet_fixture']={'item':item,'destination':destination};t.persist()
            t.execute({'kind':'key','value':'b'});started=time.time();require(change(t,oracle,item,destination),'equipment_change_pass')
            unequipped=verify(t,oracle,'unequipped')
            if unequipped['ratings']==equipped['ratings'] or close(unequipped['mastery'],equipped['mastery']):
                raise RuntimeError('helmet did not change ratings/mastery; update remains untested')
            require(change(t,oracle,item,destination,True),'equipment_change_pass')
            if verify(t,oracle,'equipped_after')!=equipped:raise RuntimeError('native ratings did not restore')
            updates=[]
            for row in Cursor(lab.ROOT/'evidence/world_packets.jsonl').poll():
                if (row.get('time',0)<started or row.get('session')!=session or
                    row.get('direction')!='from_native' or row.get('name')!='SMSG_UPDATE_OBJECT'):continue
                for record in records(bytes.fromhex(row['body'])):
                    fields={str(i):v for i,v in record.get('fields',{}).items() if i==INDEX['PLAYER_MASTERY'] or
                        INDEX['PLAYER_FIELD_COMBAT_RATING_1']<=i<INDEX['PLAYER_FIELD_COMBAT_RATING_1']+26}
                    if record['guid']==1 and record['update_type']==0 and fields:
                        updates.append({'time':row['time'],'body_sha256':hashlib.sha256(bytes.fromhex(row['body'])).hexdigest(),'fields':fields})
            if not updates:raise RuntimeError('native sparse ratings are not attributable')
            t.receipt['native_sparse_ratings_updates']=updates;t.persist()
    finally:
        try:
            if item and destination and not oracle.poll().equipment(1)['guid'] and oracle.slot(*destination)==item:
                require(change(t,oracle,item,destination,True),'equipment_change_pass')
        finally:
            try:restore_display(t,collapsed)
            finally:
                t.receipt['native_after']=stable(baseline());t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
                if not t.receipt['native_resources_preserved']:raise RuntimeError('ratings trial did not restore every native resource')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--helmet-roundtrip',action='store_true');a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.helmet_roundtrip);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
