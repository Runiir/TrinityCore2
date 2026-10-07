"""Capture one ordinary owned Erma request without claiming stable acceptance."""
import argparse,copy,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_recon import master
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_pet_recon import saved_pet_unchanged
from .interaction_pet_target import PetOracle
from .interaction_spellbook_recon import resources
from .interaction_operations import click_case
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.buffer import Reader
from .world.gameobjects import modern_guid
from .world.objects import INDEX


def eligibility(t,preparation,entry):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    if tuple(t.fixture.get(k) for k in ('guid','account_id','character_name','class','level'))!=(6,2,'Harnesshunt',3,10):
        raise RuntimeError('requires the retained owned Hunter')
    entered=entry_source(t,entry,session,preparation);npc=master();retained=pets(6)
    if len(retained)!=1 or tuple(retained[0].get(k) for k in ('id','entry','owner','name','renamed'))!=(4,42717,6,'Harnesswolf',1):
        raise RuntimeError('retained one-time named Hunter pet differs')
    since=min(p['time'] for p in entered['login_packets']);o=PetOracle(session,6,since).poll()
    inv=Inventory(lab.ROOT,session,6).poll()
    if (o.pet is None or o.pet['fields'].get(INDEX['OBJECT_FIELD_ENTRY'])!=42717 or
        o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=4 or
        o.pet['fields'].get(INDEX['UNIT_FIELD_BYTES_2'],0)>>16&255!=2 or
        resources(inv)!=entered['resources'] or saved(6)!=entered['entered_saved']):
        raise RuntimeError('owned Hunter entry or retained named pet differs')
    t.receipt.update(native_session=session,entry_source={'path':str(entry.resolve()),'sha256':lab.sha256(entry)},
        baseline_resources=resources(inv),baseline_saved=saved(6),baseline_pets=retained,native_pet=copy.deepcopy(o.pet),
        protected_checks=protected(old),qualification_added=False);t.persist()
    return old,session,npc,o,inv,retained


def staged(t,npc,o,label):
    state,frame=t.observe(label);o.poll();guid=o.selected();target=state.get('target',{})
    if (target.get('name')!='Erma' or target.get('visible') is not True or guid>>52!=0xf13 or
        guid>>32&0xfffff!=6749 or math.dist(state['world_position'][:2],npc[4:6])>3 or
        state.get('panels') or state.get('lua_errors') or state.get('blocked_actions')):
        raise RuntimeError('visible native stable master staging differs')
    return state,frame,guid


def suite(t,preparation,entry,action,source=None,review_path=None):
    old,session,npc,o,inv,retained=eligibility(t,preparation,entry)
    if action=='stage':
        t.clean_panels();t.execute({'kind':'chat','value':'/targetexact Erma'})
        state,frame,guid=staged(t,npc,o,'stable_master_staged')
        t.receipt.update(state=state,frame=frame,native_master_guid=guid,modern_master_guid=list(modern_guid(guid,0)),
            completed=True,phase='hunter_stable_request_staged',input_sent=True);return
    e=closed(source)
    if (e.get('phase')!='hunter_stable_request_staged' or e.get('actor')!=t.fixture or
        e.get('runtime')!=t.receipt['runtime'] or e.get('native_session')!=session or
        e.get('fixture_source',{}).get('sha256')!=lab.sha256(preparation) or
        len(e.get('protected_checks',{}))!=5 or not all(e['protected_checks'].values()) or
        resources(inv)!=e['baseline_resources'] or saved(6)!=e['baseline_saved'] or
        not saved_pet_unchanged(e['baseline_pets'],retained,time.time())):
        raise RuntimeError('closed owned stable request source differs')
    state,frame,guid=staged(t,npc,o,'stable_request_before')
    if guid!=e['native_master_guid'] or state['world_position']!=e['state']['world_position']:
        raise RuntimeError('selected native stable master changed')
    t.receipt['source']={'path':str(source.resolve()),'sha256':lab.sha256(source)}
    if action=='refresh':
        t.receipt.update(state=state,frame=frame,native_master_guid=guid,modern_master_guid=e['modern_master_guid'],
            completed=True,phase='hunter_stable_request_staged',input_sent=False);return
    d=reviewed(t,review_path,'Erma')
    if d['frame']['sha256']!=e['frame']['sha256']:raise RuntimeError('reviewed Erma source image differs')
    path=lab.ROOT/'run/owned_stable_request_probe.json'
    if path.exists():raise RuntimeError('another owned stable capture is armed')
    started=time.time();config={'schema':'client442_owned_stable_request_probe_v1','session':session,'owner':6,
        'native_master_guid':guid,'modern_master_guid':e['modern_master_guid'],'created_at':started,'expires_at':started+60}
    lab.private_write(path,json.dumps(config,indent=2)+'\n');digest=lab.sha256(path)
    t.receipt.update(capture_config=config,capture_config_sha256=digest,input_sent=False);t.persist()
    try:
        t.receipt['input_sent']=True;t.persist()
        t.execute({'kind':'click','value':d['point'],'button':3,'hold':.4})
        state,frame=t.observe('stable_request_after')
        if 'GossipFrame' in state.get('panels',[]):
            require(click_case(t,'diagnostic.hunter.stable_service','Select the observed native stable service.',
                lambda c:c['name'].startswith('GossipTitleButton') and 'stable' in c.get('text','').lower(),
                lambda b,a,s:{'status':'stable_service_selected' if s and not a.get('lua_errors') and
                    not a.get('blocked_actions') else 'client_or_protocol_failure'}),'stable_service_selected')
        journal=lab.ROOT/'evidence/owned_stable_request_packets.jsonl'
        packets=[p for p in entries(journal) if p.get('session')==session and p.get('time',0)>=started] if journal.is_file() else []
        t.receipt.update(capture_packets=packets,response_frame=frame);t.persist()
        if len(packets)!=1:raise RuntimeError('one ordinary stable request was not captured')
        p=packets[0];r=Reader(bytes.fromhex(p['body']));submitted=r.guid();r.end()
        if p['direction']!='from_client' or p['name']!='CMSG_REQUEST_STABLED_PETS' or list(submitted)!=e['modern_master_guid']:
            raise RuntimeError('captured public stable master identity differs')
        t.receipt['decoded_request']={'stable_master_guid':list(submitted)}
    finally:
        if lab.sha256(path)!=digest:raise RuntimeError('armed stable probe changed; refusing disarm')
        path.unlink();t.receipt['capture_disarmed']=True;t.clean_panels()
        t.execute({'kind':'chat','value':'/targetexact Erma'});state,frame=t.observe('stable_request_restored');o.poll()
        checks={'resources':resources(inv.poll())==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],
            'retained_named_pet':saved_pet_unchanged(retained,pets(6),time.time()),'owned_pet_present':o.pet is not None,
            'position':state['world_position']==e['state']['world_position'],
            'selection':state.get('target',{}).get('guid')==e['state']['target']['guid'],
            'panels_closed':not state.get('panels'),'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),
            **protected(old)}
        t.receipt.update(restoration_checks=checks,restored_frame=frame);t.persist()
        if not all(checks.values()):raise RuntimeError('stable capture preservation differs')
    t.receipt.update(completed=True,phase='hunter_stable_request_captured',
        qualified_scope='One normally submitted public Erma stable request shape only; no native translation or stable qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','refresh','capture'])
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--review',type=Path);a=p.parse_args()
    if a.action!='stage' and not a.source:p.error('requires a closed staging source')
    if a.action=='capture' and not a.review:p.error('requires a separate fresh Erma image review')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.action,a.source,a.review)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
