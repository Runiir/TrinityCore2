"""Inspect and swap only named pet4 and the normally tamed test Wolf6."""
import argparse,json,struct,time
from contextlib import contextmanager
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_capture import StablePetOracle,staged,native_catalog
from .interaction_hunter_stable_recon import master
from .interaction_hunter_stable_slots import bound,call_pet_recon,call_pet_packets
from .interaction_actionbar_pages import detail
from .interaction_pet_dismiss import public_pet
from .interaction_pet_target import pair
from .interaction_observation import read_page,read_current_page
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.buffer import Reader
from .world.objects import INDEX
from .world.gameobjects import modern_guid
from .hunter_pair_identity import identities,public_rows,expected_rows


@contextmanager
def capture(t,session,guid):
    path=lab.ROOT/'run/owned_stable_request_probe.json'
    if path.exists():raise RuntimeError('another owned stable capture is armed')
    started=time.time();config={'schema':'client442_owned_stable_request_probe_v1','session':session,'owner':6,
        'native_master_guid':guid,'modern_master_guid':list(modern_guid(guid,0)),
        'created_at':started,'expires_at':started+90,'slot_swap':{'pet_numbers':[4,6],'slots':[0,5]}}
    lab.private_write(path,json.dumps(config,indent=2)+'\n');digest=lab.sha256(path)
    t.receipt.update(capture_config=config,capture_config_sha256=digest,capture_disarmed=False);t.persist()
    try:yield
    finally:
        journal=lab.ROOT/'evidence/owned_stable_request_packets.jsonl';until=time.time()
        t.receipt['capture_packets']=[p for p in entries(journal) if p.get('session')==session and
            started<=p.get('time',0)<=until] if journal.is_file() else []
        if not path.is_file() or lab.sha256(path)!=digest:raise RuntimeError('owned pair capture changed; refusing disarm')
        path.unlink();t.receipt['capture_disarmed']=True;t.persist()


def run(t,preparation,entry,action,source=None,review_path=None,number=4,destination=0):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    if (t.fixture['guid'],t.fixture['class'],t.fixture['account_id'])!=(6,3,2):
        raise RuntimeError('requires the exact owned Hunter pair fixture')
    entered=entry_source(t,entry,session,preparation);o=StablePetOracle(session,6,entered['started_at']).poll()
    inv=Inventory(lab.ROOT,session,6).poll();current=pets(6)
    if (set(r['id'] for r in current)!={4,6} or not all(r['owner']==6 for r in current) or
        tuple(next(r for r in current if r['id']==4)[k] for k in ('entry','name','renamed'))!=(42717,'Harnesswolf',1) or
        tuple(next(r for r in current if r['id']==6)[k] for k in ('entry','name','renamed'))!=(299,'Wolf',0) or
        resources(inv)!=entered['resources'] or saved(6)!=entered['entered_saved'] or not all(protected(old).values())):
        raise RuntimeError('exact retained pair or owned entry baseline differs')
    t.receipt.update(entry_source=bound(entry),native_session=session,baseline_resources=resources(inv),
        baseline_saved=saved(6),retained_pet_before=current,input_sent=False,qualification_added=False);t.persist()
    if action=='stage':
        expected=old['retained_class_pets']
        if source:
            prior=closed(source)
            if (prior.get('phase')!='owned_pair_active_pet_restored' or prior.get('actor')!=t.fixture or
                prior.get('runtime')!=t.receipt['runtime'] or prior.get('native_session')!=session or
                prior.get('fixture_source')!=bound(preparation) or prior.get('entry_source')!=bound(entry) or
                len(prior.get('call_checks',{}))!=7 or not all(prior['call_checks'].values())):
                raise RuntimeError('pair restaging requires exact completed ordinary active-pet recovery')
            expected=prior['retained_pet_after'];t.receipt['restaging_source']=bound(source)
        if not identities(expected,current) or not o.present():raise RuntimeError('retained pair differs before staging')
        t.clean_panels();read_page(t,'pair_core','state','/tcui')
        t.execute({'kind':'chat','value':'/targetexact Erma'})
        state,frame,guid=staged(t,master(),o,'pair_erma_staged')
        t.receipt.update(state=state,frame=frame,native_master_guid=guid,retained_pet_after=pets(6),
            phase='await_owned_pair_open_review',completed=True);return
    e=closed(source)
    if (e.get('actor')!=t.fixture or e.get('runtime')!=t.receipt['runtime'] or e.get('native_session')!=session or
        e.get('fixture_source')!=bound(preparation) or e.get('entry_source')!=bound(entry) or
        not identities(e['retained_pet_after'],current)):
        raise RuntimeError('source-bound exact current pair differs')
    t.receipt.update(source=bound(source),native_master_guid=e['native_master_guid']);t.persist()
    guid=e['native_master_guid']
    if action=='open':
        if e.get('phase')!='await_owned_pair_open_review':raise RuntimeError('requires current reviewed Erma stage')
        d=reviewed(t,review_path,'Erma')
        if d.get('source')!=bound(source) or d.get('frame')!=e['frame']:raise RuntimeError('pair Erma review differs')
        state,_,current_guid=staged(t,master(),o,'pair_open_before')
        if current_guid!=guid or state.get('framerate',0)<8:raise RuntimeError('selected Erma or rendering differs')
        t.execute({'kind':'hover','value':d['point']})
        detail(t,'pair_settled_mouseover',lambda p:p.get('mouse',{}).get('mouseover_guid')==state['target']['guid'])
        with capture(t,session,guid):
            t.receipt['input_sent']=True;t.persist();t.execute({'kind':'click','value':d['point'],'button':3,'hold':.4})
            state,_=t.observe('pair_after_world_click')
            if 'GossipFrame' in state.get('panels',[]):
                require(click_case(t,'diagnostic.pair.stable_service','Select the observed native stable service.',
                    lambda c:c.get('text','').lower()=="i'd like to stable my pet here.",
                    lambda b,a,s:{'status':'pair_service_selected' if s and not a.get('lua_errors') and
                        not a.get('blocked_actions') else 'client_or_protocol_failure'},hold=1.2),'pair_service_selected')
            state,frame=read_page(t,'pair_catalog','stables','/tcui stables')
        catalog=[p for p in t.receipt['capture_packets'] if p['name']=='MSG_LIST_STABLED_PETS' and p['direction']=='from_native']
        parsed=[native_catalog(p['body']) for p in catalog]
        expected=[{'slot':r['slot'],'number':r['id'],'entry':r['entry'],'level':r['level'],
            'name':r['name'],'flags':3 if r['slot']>4 else 1} for r in current]
        probe=state['stable_probe'];checks={'native_owned_pair':bool(parsed) and all(c['master']==guid and
            sorted(c['pets'],key=lambda r:r['number'])==sorted(expected,key=lambda r:r['number']) for c in parsed),
            'native_capacity16':bool(parsed) and all(c['stable_capacity']==16 for c in parsed),
            'stock_stable_open':probe.get('visible') is True,'public_pair':public_rows(probe)==expected_rows(current),
            'saved_pair_preserved':identities(current,pets(6)),'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),
            'protected_actors':all(protected(old).values()),'capture_disarmed':t.receipt['capture_disarmed']}
        t.receipt.update(open_checks=checks,state=state,frame=frame,retained_pet_after=pets(6),phase='await_owned_pair_slot_review')
        if not all(checks.values()):raise RuntimeError('owned pair native/public opening differs')
        t.receipt['completed']=True;return
    if action in ('call-recon','call'):
        if o.present():raise RuntimeError('normal Call Pet requires the native slot swap to remove its runtime pet')
        if action=='call-recon':
            call_pet_recon(t,session);state,frame=t.observe('pair_call_caption')
            t.receipt.update(state=state,frame=frame,retained_pet_after=pets(6));return
        if e.get('phase')!='owned_call_pet_caption_observed' or e.get('call_pet_spell',{}).get('id')!=883:
            raise RuntimeError('requires exact observed Call Pet1 caption')
        spell=e['call_pet_spell'];d=reviewed(t,review_path,spell['name'])
        if d.get('source')!=bound(source) or d.get('frame')!=e['frame']:raise RuntimeError('Call Pet review differs')
        active=next(r['id'] for r in current if r['slot']==0);t.clean_panels();started=time.time()
        t.receipt.update(call_pet_started_at=started,input_sent=True,active_pet_number=active);t.persist()
        t.execute({'kind':'chat','value':'/cast '+spell['name']})
        deadline=time.monotonic()+20
        while time.monotonic()<deadline and not o.poll().present():time.sleep(.25)
        if not o.present():raise RuntimeError('ordinary Call Pet did not restore active pair pet')
        t.receipt['call_pet_packets']=call_pet_packets(session,started,time.time())
        t.receipt['native_save_command']={'command':'saveall','started_at':time.time()}
        lab.server_command('saveall');time.sleep(.5);after=pets(6);public=public_pet(t,'pair_call_pet')
        read_page(t,'pair_called_core','state','/tcui');state,frame=t.observe('pair_called_pet')
        slots={r['id']:r['slot'] for r in current};actives={n:int(n==active) for n in slots}
        fields=o.pet['fields'];checks={'native_active_pet':o.present() and fields.get(INDEX['UNIT_FIELD_PETNUMBER'])==active,
            'native_saved_pair':identities(current,after,slots,actives,active),
            'public_active_pet':public.get('exists') is True and public.get('name')==next(r['name'] for r in current if r['id']==active),
            'resources':resources(inv.poll())==entered['resources'],'saved_rows':saved(6)==entered['entered_saved'],
            'protected_actors':all(protected(old).values()),'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt.update(call_checks=checks,state=state,frame=frame,retained_pet_after=after,public_pet=public,
            phase='owned_pair_active_pet_restored',completed=all(checks.values()))
        if not all(checks.values()):raise RuntimeError('ordinary pair Call Pet preservation differs')
        return
    rendering,_=read_page(t,'pair_rendering','state','/tcui')
    state,frame=read_page(t,'pair_slot_before','stables','/tcui stables');probe=state['stable_probe']
    if probe.get('visible') is not True or public_rows(probe)!=expected_rows(current):raise RuntimeError('current stock pair slots differ')
    t.receipt.update(state=state,frame=frame,retained_pet_after=current,phase='await_owned_pair_slot_review')
    if action=='refresh':t.receipt['completed']=True;return
    d=reviewed(t,review_path,'Swap Harnesswolf')
    source_slot=next(r['slot'] for r in current if r['id']==number);other=next(r['id'] for r in current if r['slot']==destination)
    if (number not in (4,6) or {source_slot,destination}!={0,5} or other==number or
        e.get('phase')!='await_owned_pair_slot_review' or d.get('source')!=bound(source) or
        d.get('frame')!=e['frame'] or d.get('destination')!=destination):raise RuntimeError('exact occupied slot review differs')
    def point(slot):
        rows=[r for r in probe['buttons'] if r.get('slot')==slot+1 and r.get('visible') and r.get('enabled')]
        if len(rows)!=1:raise RuntimeError('stock pair button unavailable')
        return [round(rows[0]['x']/65535*1280),round(rows[0]['y']/65535*720)]
    start,end=point(source_slot),point(destination)
    if d.get('point')!=start or d.get('end')!=end or rendering.get('framerate',0)<8 or rendering.get('cursor_info'):
        raise RuntimeError('reviewed drag geometry or idle cursor differs')
    slots={number:destination,other:source_slot};actives={4:0,6:0}
    with capture(t,session,guid):
        t.receipt.update(input_sent=True,number=number,destination=destination,source_slot=source_slot,swap_number=other,
            ordinary_input={'kind':'drag','start':start,'end':end,'duration':.8});t.persist()
        t.execute({'kind':'drag','start':start,'end':end,'duration':.8})
        state,frame=read_current_page(t,'pair_slot_after','stables',lambda s:
            public_rows(s.get('stable_probe',{}))==expected_rows([{**r,'slot':slots[r['id']]} for r in current]))
        lab.server_command('saveall');time.sleep(.5);o.poll()
    rows=t.receipt['capture_packets'];requests=[p for p in rows if p['name']=='CMSG_SET_PET_SLOT' and p['direction']=='from_client']
    decoded=[]
    for p in requests:
        r=Reader(bytes.fromhex(p['body']));n,slot=r.unpack('IB');g=list(r.guid());r.end();decoded.append((n,slot,g))
    native=[p for p in rows if p['name']=='CMSG_SET_PET_SLOT' and p['direction']=='to_native'];legacy=[]
    for p in native:
        r=Reader(bytes.fromhex(p['body']));n,slot=r.unpack('IB');octets=[0]*8
        for i in (3,2,0,7,5,6,1,4):octets[i]=r.bits(1)
        for i in (5,3,1,7,4,0,6,2):
            if octets[i]:octets[i]=r.unpack('B')[0]^1
        r.end();legacy.append((n,slot,int.from_bytes(bytes(octets),'little')))
    updates=[p for p in rows if p['name']=='SMSG_PET_SLOT_UPDATED' and p['direction']=='from_native']
    results=[p for p in rows if p['name']=='SMSG_STABLE_RESULT' and p['direction']=='from_native']
    delivered=[p for p in rows if p['name']=='SMSG_PET_STABLE_RESULT' and p['direction']=='to_client']
    after=pets(6);expected_update=struct.pack('<4I',number,destination,other,source_slot).hex()
    checks={'one_owned_client_request':decoded==[(number,destination,list(modern_guid(guid,0)))],
        'one_native_request':legacy==[(number,destination,guid)],
        'exact_native_occupied_update':len(updates)==1 and updates[0]['body']==expected_update,
        'native_success':len(results)==1 and results[0]['body']=='08',
        'delivered_success':len(delivered)==1 and delivered[0]['body']=='08',
        'ordered_native_outcome':len(native)==len(updates)==len(results)==1 and native[0]['time']<=updates[0]['time']<=results[0]['time'],
        'native_pair_slots':identities(current,after,slots,actives),'runtime_pet_removed':not o.present() and pair(o.player,'UNIT_FIELD_SUMMON')==0,
        'public_pair_slots':public_rows(state['stable_probe'])==expected_rows(after),
        'protected_actors':all(protected(old).values()),'capture_disarmed':t.receipt['capture_disarmed'],
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(move_checks=checks,state=state,frame=frame,retained_pet_after=after,
        phase='owned_pair_slot_swap_verified',completed=all(checks.values()))
    if not all(checks.values()):raise RuntimeError('ordinary occupied pair slot swap differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','open','refresh','move','call-recon','call'])
    for key in ('preparation','entry','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--number',type=int,choices=[4,6],default=4);p.add_argument('--destination',type=int,choices=[0,5],default=0)
    a=p.parse_args()
    if a.action!='stage' and not a.source:p.error('requires closed current pair source')
    if a.action in ('open','move','call') and not a.review:p.error('requires separately inspected fresh review')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.action,a.source,a.review,a.number,a.destination)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','open_checks','move_checks','call_checks')}),flush=True)
