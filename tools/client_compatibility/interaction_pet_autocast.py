"""Validate actual stock autocast off/on through native requests, catalogs and persistence."""
import argparse,copy,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import pets,character,SCRIPT_BOUNDARY
from .interaction_pet_command_probe import read,expected_guid
from .interaction_pet_target import retained_imp,pair
from .interaction_pet_commands import PET_KEYS
from .interaction_pet_react_modes import suite as restored_suite,public_bar
from .interaction_ground_movement import position
from .interaction_macros import require
from .observation.journal import entries
from .world.objects import INDEX
from .pet_react_evidence import info_pairs
from .pet_autocast_capture_evidence import SPELLS,button
from .pet_autocast_evidence import request_checks,saved_buttons,native_catalog,catalog_delivery


def switch(t,o,spell,wanted,label):
    baseline=t.receipt['baseline'];original=saved_buttons(baseline['pet'])
    if not all(original[slot-1]=={'slot':slot,'spell_id':spell,'action_type':0xc1}
        for spell,slot in SPELLS.items()):raise RuntimeError('requires both captured native autocast spells enabled')
    control=read(t,label+'_control');row,point=button(control['probe'],o.pet,spell,not wanted)
    expected_native=copy.deepcopy(original);expected_native[SPELLS[spell]-1]['action_type']=0xc1 if wanted else 0x81
    expected_public=public_bar(control['probe'])
    for value in expected_public:
        if value.get('spell_id')==spell:value['autocast_enabled']=wanted
    since=time.time();t.receipt[label+'_started_at']=since;t.persist()
    def outcome(b,a,s):
        reload_since=time.time();t.execute({'kind':'chat','value':'/reload'});o.poll()
        sample=read(t,label+'_native_refreshed');o.poll();accepted=position(5)
        catalogs=[c for c in o.catalogs if c['guid']==o.pet['guid'] and c['packet']['time']>=reload_since]
        catalog=catalogs[-1] if catalogs else None
        checks,requests=request_checks(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,
            since,time.time(),o.pet,spell,wanted)
        queries=info_pairs(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,reload_since,time.time())
        delivery=catalog_delivery(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,catalog,o.pet) if catalog else []
        deadline=time.monotonic()+5;settling=[]
        while True:
            persisted=retained_imp(t.fixture,pets(5));saved=saved_buttons(persisted)
            settling.append({'time':time.time(),'id':persisted['id'],'bar':saved,'input_replayed':False})
            if saved==expected_native or time.monotonic()>deadline:break
            time.sleep(.2)
        data=native_catalog(catalog) if catalog else None
        desired=((0xc1 if wanted else 0x81)<<24)|spell
        other_keys=[k for k in PET_KEYS if k!='abdata']
        checks.update(ordinary_native_info_query=bool(queries) and all(q['native'] is not None for q in queries),
            actual_native_catalog=bool(data and data['guid']==o.pet['guid'] and data['react']==3 and data['command']==1
                and data['buttons']==expected_native and [v for v in data['actions'] if v&0xffffff==spell]==[desired]),
            exact_modern_catalog_delivery=len(delivery)==1,
            persisted_owned_bar=persisted['id']==2 and persisted['owner']==5 and persisted['Reactstate']==3
                and saved==expected_native and {k:persisted[k] for k in other_keys}=={k:baseline['pet'][k] for k in other_keys},
            public_exact_bar=public_bar(sample['probe'])==expected_public,
            public_owned_pet=sample['probe'].get('pet_guid')==expected_guid(o.pet)
                and sample['probe'].get('owner_guid')==t.guid,
            public_idle=sample['probe'].get('pet_speed')==sample['probe'].get('player_speed')==0,
            ui_clean=sample['ui_clean'],owned_native_pet=o.present()
                and pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')==5
                and o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])==2,
            owner_position=accepted==baseline['position'],money=character(5,2)['money']==baseline['money'])
        return {'status':'owned_native_autocast_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'requests':requests,'reload_started_at':reload_since,'native_catalogs':catalogs,
                'modern_catalog_delivery':delivery,'native_info_queries':queries,'public':sample,
                'persisted_abdata':persisted['abdata'],'persistence_settling':settling,'observed_button':row,
                'owner_position':accepted}}
    require(t.step(label,'Switch stock autocast and require owned native command, real reload catalog, saved state and public agreement.',
        {'toggle':{'kind':'click','value':point,'button':3,'hold':.4,
            'description':f'Right-click observed {row["name"]} button{row["slot"]} once.'}},
        outcome,diagnostic_action='toggle'),'owned_native_autocast_pass')


def restore_switches(t,o):
    # One source-bound restoration attempt after a failure. A fresh real
    # native catalog and matching public bar decide whether any input is needed.
    t.clean_panels();since=time.time();t.execute({'kind':'chat','value':'/reload'});o.poll()
    sample=read(t,'autocast_failure_restore_control');o.poll()
    catalogs=[c for c in o.catalogs if c['guid']==o.pet['guid'] and c['packet']['time']>=since]
    catalog=catalogs[-1] if catalogs else None
    queries=info_pairs(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,since,time.time())
    delivery=catalog_delivery(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,catalog,o.pet) if catalog else []
    if (not catalog or not queries or not all(q['native'] is not None for q in queries) or len(delivery)!=1
        or not o.present() or not sample['ui_clean'] or sample['probe'].get('pet_guid')!=expected_guid(o.pet)
        or sample['probe'].get('owner_guid')!=t.guid):raise RuntimeError('autocast restoration lacks fresh owned native/public authority')
    data=native_catalog(catalog);original=saved_buttons(t.receipt['baseline']['pet'])
    disabled=[];expected_public=copy.deepcopy(t.receipt['baseline']['public_bar'])
    if data['react']!=3 or data['command']!=1:raise RuntimeError('autocast restoration native command mode differs')
    for current,before in zip(data['buttons'],original):
        if current==before:continue
        spell=before['spell_id']
        if (spell not in SPELLS or before!={'slot':SPELLS[spell],'spell_id':spell,'action_type':0xc1}
            or current!={'slot':SPELLS[spell],'spell_id':spell,'action_type':0x81}):
            raise RuntimeError('autocast restoration found an uncaptured native bar change')
        disabled.append(spell)
        for row in expected_public:
            if row.get('spell_id')==spell:row['autocast_enabled']=False
    if len(disabled)>1 or public_bar(sample['probe'])!=expected_public:
        raise RuntimeError('autocast restoration differs from the one-switch lifecycle')
    t.receipt['autocast_failure_restore']={'catalog':catalog,'public':sample,'disabled':disabled,
        'native_info_queries':queries,'modern_catalog_delivery':delivery,'cleanup_only':True};t.persist()
    for spell in disabled:switch(t,o,spell,True,'fixture.autocast_restore_'+str(spell))


def switches(t,o):
    try:
        for spell in SPELLS:
            for wanted in (False,True):
                switch(t,o,spell,wanted,f'pets.autocast_{spell}_'+('on' if wanted else 'off'))
    except Exception as error:
        t.receipt['autocast_execution_failure']=f'{type(error).__name__}: {error}';t.persist()
        restore_switches(t,o)
        raise


def suite(t,preparation,entry):
    restored_suite(t,preparation,entry,sequence=((3,'fixture.pet_assist_restore'),),capture=switches)
    t.receipt.update(phase='owned_native_autocast_complete',qualified_scope=
        'One idle trained owned Imp: stock Firebolt/Blood Pact autocast off/on, exact owned native commands, '
        'real requested native and delivered modern catalogs on ordinary reload, native saved flags and public bar, '
        'followed by full original-state restoration. Combat autocast behavior and other pets/classes remain open.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
