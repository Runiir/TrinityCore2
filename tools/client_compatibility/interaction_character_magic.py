"""Inspect visible spell/defense rows and public spell haste across a belt swap."""
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


def native(oracle):
    fields=oracle.poll().objects.get(1,{})
    def floating(name):
        if INDEX[name] not in fields:raise RuntimeError('native field is absent: '+name)
        return struct.unpack('<f',struct.pack('<I',fields[INDEX[name]]))[0]
    cast,haste=floating('UNIT_MOD_CAST_SPEED'),floating('UNIT_MOD_CAST_HASTE')
    if not all(math.isfinite(v) and v>0 for v in [cast,haste]):raise RuntimeError('requires positive native cast multipliers')
    return {'casting_multiplier':cast,'spell_multiplier':haste,'spell_haste':(1/haste-1)*100,
        'dodge':floating('PLAYER_DODGE_PERCENTAGE'),'parry':floating('PLAYER_PARRY_PERCENTAGE'),
        'spell_crit':floating('PLAYER_SPELL_CRIT_PERCENTAGE1') if fields.get(INDEX['PLAYER_SPELL_CRIT_PERCENTAGE1']) else 0,
        'fields':{name:{'index':INDEX[name],'raw':fields[INDEX[name]]} for name in ['UNIT_MOD_CAST_SPEED','UNIT_MOD_CAST_HASTE']}}


def categories(t,label):return {row['category']:row for row in detail(t,label)['stats']['categories']}


def toggle(t,category,want,label):
    row=categories(t,label+'_before')[category]
    if row['collapsed']==want:return
    def outcome(b,a,s):
        current=categories(t,label+'_after')[category]
        return {'status':'stat_category_toggle_pass' if s and current['collapsed']==want else 'client_or_protocol_failure',
            'oracle':{'category':category,'collapsed':current['collapsed'],'expected':want}}
    require(click_case(t,'character.stats.category.'+label,'Set the stock '+category+' category layout.',
        lambda c:c['name']==row['name']+'Toolbar',outcome),'stat_category_toggle_pass')


def verify(t,oracle,label):
    def outcome(b,a,s):
        expected=native(oracle);public=detail(t,label)['stats'];sheet=public['sheet']
        haste_text,haste=text_value(sheet,'SPELL','Haste')
        dodge_text,dodge=text_value(sheet,'DEFENSE','Dodge');parry_text,parry=text_value(sheet,'DEFENSE','Parry')
        checks={'ordinary_hover':s=='inspect','public_spell_haste':close(public.get('spell_haste'),expected['spell_haste']),
            'rendered_spell_haste':close(haste,expected['spell_haste']),
            'rendered_dodge':close(dodge,expected['dodge']),'rendered_parry':close(parry,expected['parry']),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'character_spell_defense_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native':expected,'public':public,
                'rendered':{'spell_haste':haste_text,'dodge':dodge_text,'parry':parry_text}}}
    row=t.step('character.stats.spell.'+label,'Inspect visible spell and defense stats against native fields.',
        {'inspect':{'kind':'hover','value':[1110,580],'description':'Move the pointer away from the stat rows.'}},
        outcome,diagnostic_action='inspect');require(row,'character_spell_defense_pass');return row['oracle']['native']


def suite(t,roundtrip):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned geared primary warrior')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    original=stable(baseline());t.receipt.update(baseline=original,native_session=session);t.persist()
    creation=None
    for row in Cursor(lab.ROOT/'evidence/world_packets.jsonl').poll():
        if row.get('session')==session and row.get('direction')=='from_native' and row.get('name')=='SMSG_UPDATE_OBJECT':
            if find_self(bytes.fromhex(row['body']),1):creation={'time':row['time'],'body_sha256':hashlib.sha256(bytes.fromhex(row['body'])).hexdigest()}
    if not creation:raise RuntimeError('native self creation is not attributable')
    t.receipt['native_creation']=creation;t.persist();collapsed=None;layout=None;settings=None;changed=[];item=destination=None
    try:
        open_character(t,'spell.character');collapsed=not any(c['name']=='PaperDollSidebarTab1' for c in controls(t))
        t.receipt['display_baseline']={'collapsed':collapsed};t.persist()
        if collapsed:
            require(click_case(t,'spell.expand','Expand the stock character sidebar.',lambda c:c['name']=='CharacterFrameExpandButton',
                lambda b,a,s:{'status':'character_expand_pass' if s and a.get('character_expanded') else 'client_or_protocol_failure'},
                await_state=lambda a:a.get('character_expanded') is True),'character_expand_pass')
        require(click_case(t,'spell.stats','Select stock character stats.',lambda c:c['name']=='PaperDollSidebarTab1',
            lambda b,a,s:{'status':'character_stats_sidebar_pass' if s and detail(t,'selected_stats')['stats']['sheet'] else
                'client_or_protocol_failure'}),'character_stats_sidebar_pass')
        probe=detail(t,'layout_baseline')['stats'];layout={row['category']:row['collapsed'] for row in probe['categories']}
        settings=probe['category_settings'];t.receipt['category_baseline']={'layout':layout,'settings':settings};t.persist()
        for category,want in [('GENERAL',True),('ATTRIBUTES',True),('MELEE',True),('RANGED',True),('SPELL',False),('DEFENSE',False)]:
            if layout[category]!=want:changed.append(category);toggle(t,category,want,'setup_'+category)
        equipped=verify(t,oracle,'equipped_before')
        if roundtrip:
            item=oracle.equipment(6);empty=[s for s in range(1,17) if not oracle.slot(0,s)['guid']]
            if item['id']!=78416 or not empty:raise RuntimeError('requires the catalog-attributed haste belt and an empty backpack slot')
            destination=(0,empty[-1]);t.receipt['belt_fixture']={'item':item,'destination':destination};t.persist()
            if not t.observe('before_bag')[0].get('bags'):t.execute({'kind':'key','value':'b'})
            started=time.time()
            require(change(t,oracle,item,destination,equipment_slot=6,equipment_control='CharacterWaistSlot',case_suffix='.waist'),'equipment_change_pass')
            removed=verify(t,oracle,'waist_unequipped')
            if close(removed['spell_haste'],equipped['spell_haste']):raise RuntimeError('belt did not change native spell haste')
            require(change(t,oracle,item,destination,True,equipment_slot=6,equipment_control='CharacterWaistSlot',case_suffix='.waist'),'equipment_change_pass')
            if verify(t,oracle,'waist_equipped_after')!=equipped:raise RuntimeError('native spell/defense stats did not restore')
            updates=[]
            for row in Cursor(lab.ROOT/'evidence/world_packets.jsonl').poll():
                if row.get('time',0)<started or row.get('session')!=session or row.get('direction')!='from_native' or row.get('name')!='SMSG_UPDATE_OBJECT':continue
                for record in records(bytes.fromhex(row['body'])):
                    if record.get('update_type')!=0 or record.get('guid')!=1:continue
                    fields={str(i):v for i,v in record['fields'].items() if i in [INDEX['UNIT_MOD_CAST_SPEED'],INDEX['UNIT_MOD_CAST_HASTE']]}
                    if fields:updates.append({'time':row['time'],'body_sha256':hashlib.sha256(bytes.fromhex(row['body'])).hexdigest(),'fields':fields})
            if len(updates)<2:raise RuntimeError('both native sparse cast-multiplier changes are not attributable')
            t.receipt['native_sparse_cast_updates']=updates;t.persist()
    finally:
        try:
            if item and destination and not oracle.poll().equipment(6)['guid'] and oracle.slot(*destination)==item:
                require(change(t,oracle,item,destination,True,equipment_slot=6,equipment_control='CharacterWaistSlot',case_suffix='.waist'),'equipment_change_pass')
        finally:
            try:
                for category in reversed(changed):toggle(t,category,layout[category],'restore_'+category)
                if layout is not None:
                    after=detail(t,'layout_restored')['stats'];t.receipt['category_restoration']={'layout':{row['category']:row['collapsed'] for row in after['categories']},'settings':after['category_settings']}
                    if t.receipt['category_restoration']!=t.receipt['category_baseline']:raise RuntimeError('original category layout/settings did not restore')
            finally:
                try:restore_display(t,collapsed)
                finally:
                    t.receipt['native_after']=stable(baseline());t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
                    if not t.receipt['native_resources_preserved']:raise RuntimeError('spell/defense trial did not restore every native resource')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--belt-roundtrip',action='store_true')
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.belt_roundtrip);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
