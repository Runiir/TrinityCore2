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
from .interaction_observation import read_page
from .interaction_actionbar_pages import detail


def native_catalog(body):
    r=Reader(bytes.fromhex(body));guid,count,last=r.unpack('QBB');rows=[]
    if not 5<=last<=20 or count>last+1:raise RuntimeError('native stable capacity differs')
    for _ in range(count):
        slot,number,entry,level=r.unpack('iIII');name=bytearray()
        while True:
            value=r.raw(1)[0]
            if not value:break
            name.append(value)
            if len(name)>255:raise RuntimeError('native stable name is unbounded')
        flags,=r.unpack('B');rows.append({'slot':slot,'number':number,'entry':entry,'level':level,
            'name':name.decode(),'flags':flags})
    r.end();return {'master':guid,'last_slot':last,'stable_capacity':last-4,'pets':rows}


def restore(t,old,e,o,inv,retained):
    # Stables is explicitly selected, so return to the ordinary state page
    # before cleanup's state observations. Diagnostic commands never open it.
    read_page(t,'stable_restore_state','state','/tcui')
    t.clean_panels();t.execute({'kind':'chat','value':'/targetexact Erma'})
    state,frame=t.observe('stable_request_restored');o.poll()
    checks={'resources':resources(inv.poll())==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],
        'retained_named_pet':saved_pet_unchanged(retained,pets(6),time.time()),'owned_pet_present':o.pet is not None,
        'position':state['world_position']==e['state']['world_position'],
        'selection':state.get('target',{}).get('guid')==e['state']['target']['guid'],
        'panels_closed':not state.get('panels'),'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),
        **protected(old)}
    t.receipt.update(restoration_checks=checks,restored_frame=frame);t.persist()
    if not all(checks.values()):raise RuntimeError('stable capture preservation differs')


def recover(t,preparation,source,old,session,o,inv,retained):
    path=source.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():
        raise RuntimeError('requires a private failed stable episode')
    failed=json.loads(path.read_text())
    if (failed.get('completed') is not False or not failed.get('failure') or not failed.get('finished_at') or
        failed.get('actor')!=t.fixture or failed.get('runtime')!=t.receipt['runtime'] or
        failed.get('native_session')!=session or failed.get('capture_disarmed') is not True or
        failed.get('fixture_source',{}).get('sha256')!=lab.sha256(preparation) or
        (lab.ROOT/'run/owned_stable_request_probe.json').exists()):
        raise RuntimeError('failed stable recovery identity or disarm differs')
    bound=Path(failed.get('source',{}).get('path','')).resolve();e=closed(bound)
    if (lab.sha256(bound)!=failed['source']['sha256'] or e.get('native_session')!=session or
        e.get('runtime')!=t.receipt['runtime'] or e.get('actor')!=t.fixture or
        e.get('phase')!='hunter_stable_request_staged' or
        resources(inv)!=e['baseline_resources'] or saved(6)!=e['baseline_saved'] or
        not saved_pet_unchanged(e['baseline_pets'],retained,time.time())):
        raise RuntimeError('failed stable recovery baseline differs')
    t.receipt.update(failed_source={'path':str(path),'sha256':lab.sha256(path)},stable_choice_replayed=False)
    restore(t,old,e,o,inv,retained)
    t.receipt.update(completed=True,phase='hunter_stable_recovery_verified',
        qualified_scope='Normal diagnostic-page and panel restoration only; the failed opening remains excluded.')


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
    if action=='recover':
        recover(t,preparation,source,old,session,o,inv,retained);return
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
    if action=='inspect':
        probe=detail(t,'stable_mouse_inspection')
        t.receipt.update(mouse_inspection=probe,completed=True,phase='hunter_stable_mouse_inspected',input_sent=False)
        return
    d=reviewed(t,review_path,'Erma')
    if d['frame']['sha256']!=e['frame']['sha256']:raise RuntimeError('reviewed Erma source image differs')
    if state.get('framerate',0)<8:
        raise RuntimeError('owned world click requires a normally rendering scout; no button input sent')
    t.execute({'kind':'hover','value':d['point']})
    t.receipt['mouse_before']=detail(t,'stable_settled_mouseover',
        lambda p:p.get('mouse',{}).get('mouseover_guid')==e['state']['target']['guid'])
    t.persist()
    path=lab.ROOT/'run/owned_stable_request_probe.json'
    if path.exists():raise RuntimeError('another owned stable capture is armed')
    started=time.time();config={'schema':'client442_owned_stable_request_probe_v1','session':session,'owner':6,
        'native_master_guid':guid,'modern_master_guid':e['modern_master_guid'],'created_at':started,'expires_at':started+60}
    lab.private_write(path,json.dumps(config,indent=2)+'\n');digest=lab.sha256(path)
    t.receipt.update(capture_config=config,capture_config_sha256=digest,input_sent=False);t.persist()
    opened_ok=False
    try:
        t.receipt['input_sent']=True;t.persist()
        t.execute({'kind':'click','value':d['point'],'button':3,'hold':.4})
        state,frame=t.observe('stable_request_after')
        t.receipt.update(response_state=state,response_frame=frame);t.persist()
        if not state.get('panels'):
            t.receipt['mouse_after']=detail(t,'stable_mouse_after_click')
        else:
            # Open panels suppress the automatic action-bar diagnostic page.
            # The actual gossip response now supplies stronger input evidence.
            t.receipt['mouse_after_skipped']={'reason':'Stock panel is open; passive action-bar cycle is suspended.',
                'panels':state['panels'],'extra_input_sent':False}
        t.persist()
        if 'GossipFrame' in state.get('panels',[]):
            require(click_case(t,'diagnostic.hunter.stable_service','Select the observed native stable service.',
                lambda c:c.get('text','').lower()=="i'd like to stable my pet here.",
                lambda b,a,s:{'status':'stable_service_selected' if s and not a.get('lua_errors') and
                    not a.get('blocked_actions') else 'client_or_protocol_failure'},hold=1.2),'stable_service_selected')
        journal=lab.ROOT/'evidence/owned_stable_request_packets.jsonl'
        packets=[p for p in entries(journal) if p.get('session')==session and p.get('time',0)>=started] if journal.is_file() else []
        t.receipt.update(capture_packets=packets,response_frame=frame);t.persist()
        native=[p for p in packets if p.get('direction')=='from_native' and p.get('name')=='MSG_LIST_STABLED_PETS']
        if not native or len({p['body'] for p in native})!=1:raise RuntimeError('consistent ordinary native stable catalog absent')
        catalog=native_catalog(native[0]['body']);t.receipt['native_stable_catalog']=catalog
        if catalog['master']!=guid:raise RuntimeError('native stable catalog master differs')
        for p in packets:
            if p.get('direction')!='from_client':continue
            r=Reader(bytes.fromhex(p['body']));submitted=r.guid();r.end()
            if p['name']!='CMSG_REQUEST_STABLED_PETS' or list(submitted)!=e['modern_master_guid']:
                raise RuntimeError('captured public stable master identity differs')
            t.receipt.setdefault('decoded_requests',[]).append({'stable_master_guid':list(submitted)})
        public,pixels=read_page(t,'stable_cache','stables','/tcui stables')
        probe=public['stable_probe'];expected=[{'slot':p['slot']+1,'name':p['name'],'level':p['level'],
            'display_id':retained[0]['modelid']} for p in catalog['pets']]
        observed=[{k:p.get(k) for k in ('slot','name','level','display_id')} for p in probe.get('pets',[])]
        checks={'native_named_pet':len(catalog['pets'])==1 and catalog['pets'][0]=={'slot':0,'number':4,
            'entry':42717,'level':10,'name':'Harnesswolf','flags':1},'same_visible_native_master':catalog['master']==guid,
            'stock_stable_open':probe['visible'] is True,'native_public_pet_cache':observed==expected,
            'selected_named_pet':probe.get('selected')==1 and probe.get('name')=='Harnesswolf',
            'public_show_event':probe.get('events',{}).get('PET_STABLE_SHOW',{}).get('count',0)>0,
            'native_actual_capacity':catalog['stable_capacity']==16,'passive_stable_observer':public.get('observer_version') in (140,141,142,143),
            'ui_clean':not public.get('lua_errors') and not public.get('blocked_actions')}
        t.receipt.update(public_stable=probe,public_stable_frame=pixels,outcome_checks=checks);t.persist()
        t.receipt['cases'].append({'id':'diagnostic.hunter.stable_slot_open' if action=='slot-open' else 'pets.stable_open',
            'time':time.time(),'input_sent':True,
            'status':('owned_stable_slot_staged' if action=='slot-open' else 'native_owned_stable_open_pass')
                if all(checks.values()) else 'client_or_protocol_failure',
            'after_frame':pixels,'oracle':{'checks':checks}});t.persist()
        if not all(checks.values()):raise RuntimeError('native and public stable opening differ')
        opened_ok=True
    finally:
        journal=lab.ROOT/'evidence/owned_stable_request_packets.jsonl'
        t.receipt['capture_packets']=[p for p in entries(journal) if p.get('session')==session and
            p.get('time',0)>=started] if journal.is_file() else []
        if lab.sha256(path)!=digest:raise RuntimeError('armed stable probe changed; refusing disarm')
        path.unlink();t.receipt['capture_disarmed']=True
        if action!='slot-open' or not opened_ok:restore(t,old,e,o,inv,retained)
    if action=='slot-open':
        t.receipt.update(completed=True,phase='await_owned_stable_slot_review',
            qualified_scope='Native owned stable opened and retained for a separately reviewed ordinary slot move; no qualification.')
        return
    t.receipt.update(completed=True,phase='hunter_stable_native_open_verified',
        qualified_scope='Ordinary Erma gossip opens the native owned Hunter stable catalog. Named pet cache, level, model and '
            'selection match native records; resources, saved pet and all protected actors restore. Slot mutation and capacity remain open.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','refresh','inspect','capture','recover','slot-open'])
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--review',type=Path);a=p.parse_args()
    if a.action!='stage' and not a.source:p.error('requires a closed staging source')
    if a.action in ('capture','slot-open') and not a.review:p.error('requires a separate fresh Erma image review')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.action,a.source,a.review)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
