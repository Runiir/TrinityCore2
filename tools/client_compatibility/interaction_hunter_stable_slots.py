"""Reviewed ordinary owned pet4 slot round trip; native server owns all mutations."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source,wire_known
from .interaction_hunter_fixture import protected
from .interaction_hunter_pet_recon import saved_pet_unchanged
from .interaction_pet_dismiss import Presence,public_pet
from .interaction_pet_target import pair
from .interaction_spellbook_recon import resources
from .interaction_observation import read_page,read_current_page
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.buffer import Reader,Writer
from .world.objects import INDEX


def bound(path):return {'path':str(path.resolve()),'sha256':lab.sha256(path)}


def pet_identity(before,after,slot):
    if len(before)!=1 or len(after)!=1 or set(before[0])!=set(after[0]):return False
    b,a=before[0],after[0]
    return (a['slot']==slot and b['id']==a['id']==4 and b['owner']==a['owner']==6 and
        0<b['savetime']<=a['savetime']<=time.time() and
        {k:v for k,v in b.items() if k not in ('slot','savetime')}==
        {k:v for k,v in a.items() if k not in ('slot','savetime')})


def baseline(t,preparation,entry,opening):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    entered=entry_source(t,entry,session,preparation);e=closed(opening)
    if (e.get('phase')!='await_owned_stable_slot_review' or e.get('actor')!=t.fixture or
        e.get('runtime')!=t.receipt['runtime'] or e.get('native_session')!=session or
        e.get('fixture_source')!=bound(preparation) or e.get('entry_source')!=bound(entry) or
        e.get('capture_disarmed') is not True or len(e.get('outcome_checks',{}))!=9 or
        not all(e['outcome_checks'].values()) or len(e.get('protected_checks',{}))!=5 or
        not all(e['protected_checks'].values()) or e['baseline_pets'][0]['slot']!=0 or
        e['baseline_resources']!=resources(Inventory(lab.ROOT,session,6).poll()) or
        saved(6)!=e['baseline_saved']):
        raise RuntimeError('owned same-entry stable opening or baseline differs')
    known=wire_known(t,session)
    if 883 not in known:raise RuntimeError('normal Call Pet883 recovery is not native known')
    o=Presence(session,6,min(p['time'] for p in entered['login_packets'])).poll()
    t.receipt.update(opening_source=bound(opening),entry_source=bound(entry),native_session=session,
        baseline_pets=e['baseline_pets'],baseline_saved=e['baseline_saved'],baseline_resources=e['baseline_resources'],
        native_master_guid=e['capture_config']['native_master_guid'],
        modern_master_guid=e['capture_config']['modern_master_guid'],baseline_position=e['response_state']['world_position'],
        protected_checks=protected(old),normal_call_pet_known=True,qualification_added=False);t.persist()
    return old,e,session,o


def panel(t,label,slot):
    state,frame=read_page(t,label,'stables','/tcui stables')
    probe=state['stable_probe'];rows=probe.get('pets',[])
    if (probe.get('visible') is not True or probe.get('stable_slots')!=16 or len(rows)!=1 or
        (rows[0].get('slot'),rows[0].get('name'),rows[0].get('level'),rows[0].get('display_id'))!=(slot+1,'Harnesswolf',10,903) or
        state.get('lua_errors') or state.get('blocked_actions')):
        raise RuntimeError('stock stable panel or exact retained pet slot differs')
    return state,frame,probe


def verify_packets(rows,source,destination,master):
    requests=[p for p in rows if p['name']=='CMSG_SET_PET_SLOT' and p['direction']=='from_client']
    native=[p for p in rows if p['name']=='CMSG_SET_PET_SLOT' and p['direction']=='to_native']
    updates=[p for p in rows if p['name']=='SMSG_PET_SLOT_UPDATED' and p['direction']=='from_native']
    results=[p for p in rows if p['name']=='SMSG_STABLE_RESULT' and p['direction']=='from_native']
    delivered=[p for p in rows if p['name']=='SMSG_PET_STABLE_RESULT' and p['direction']=='to_client']
    decoded=[]
    for p in requests:
        r=Reader(bytes.fromhex(p['body']));number,slot=r.unpack('IB');guid=list(r.guid());r.end()
        decoded.append({'number':number,'destination':slot,'master':guid})
    legacy=[]
    for p in native:
        r=Reader(bytes.fromhex(p['body']));number,slot=r.unpack('IB');octets=[0]*8
        for i in (3,2,0,7,5,6,1,4):octets[i]=r.bits(1)
        for i in (5,3,1,7,4,0,6,2):
            if octets[i]:octets[i]=r.unpack('B')[0]^1
        r.end();legacy.append((number,slot,int.from_bytes(bytes(octets),'little')))
    from .world.gameobjects import modern_guid
    expected=Writer().pack('4I',4,destination,0,source).finish().hex()
    return {'one_exact_client_request':decoded==[{'number':4,'destination':destination,'master':list(modern_guid(master,0))}],
        'one_exact_native_request':legacy==[(4,destination,master)],
        'one_exact_native_slot_update':len(updates)==1 and updates[0]['body']==expected,
        'native_success':len(results)==1 and results[0]['body']=='08',
        'delivered_success':len(delivered)==1 and delivered[0]['body']=='08',
        'ordered_native_outcome':len(native)==len(updates)==len(results)==1 and native[0]['time']<=updates[0]['time']<=results[0]['time']}


def run(t,preparation,entry,opening,action,source=None,review_path=None,slot=0,destination=None):
    old,e,session,o=baseline(t,preparation,entry,opening)
    if action=='finish':
        moved=closed(source)
        if (moved.get('phase')!='owned_stable_slot_move_verified' or moved.get('opening_source')!=bound(opening) or
            moved.get('runtime')!=t.receipt['runtime'] or moved.get('destination')!=0 or
            not all(moved.get('move_checks',{}).values()) or not pet_identity(e['baseline_pets'],pets(6),0)):
            raise RuntimeError('normal recovery requires an exact successful return to native active slot0')
        t.receipt['return_source']=bound(source);t.clean_panels()
        if o.present():raise RuntimeError('expected native slot roundtrip to dismiss the runtime pet')
        t.receipt['call_pet_started_at']=time.time();t.persist();t.execute({'kind':'chat','value':'/cast Call Pet'})
        inv=Inventory(lab.ROOT,session,6);deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            o.poll();inv.poll()
            if o.present() and resources(inv)==e['baseline_resources']:break
            time.sleep(.5)
        if not o.present():raise RuntimeError('normal Call Pet did not restore native owned pet')
        public=public_pet(t,'slot_roundtrip_restored_pet')
        read_page(t,'slot_restore_state','state','/tcui');t.clean_panels();t.execute({'kind':'chat','value':'/targetexact Erma'})
        state,frame=t.observe('slot_roundtrip_restored');o.poll();current=pets(6)
        fields=o.pet['fields'];guid=o.pet['guid']
        public_guid=f"Pet-0-1-{o.pet['map']}-0-{guid>>32&0xfffff}-{guid&0xffffffff:010X}"
        checks={'resources':resources(inv.poll())==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],
            'retained_named_pet':saved_pet_unchanged(e['baseline_pets'],current,time.time()),
            'owned_pet_present':o.present() and pair(fields,'UNIT_FIELD_SUMMONEDBY')==6 and
                fields.get(INDEX['UNIT_FIELD_PETNUMBER'])==4 and public.get('exists') is True and
                public.get('guid')==public_guid and public.get('name')=='Harnesswolf',
            'position':state['world_position']==e['response_state']['world_position'],
            'selection':state.get('target',{}).get('guid')==e['response_state']['target']['guid'],
            'panels_closed':not state.get('panels'),'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),
            **protected(old)}
        t.receipt.update(restoration_checks=checks,restored_frame=frame,restored_public_pet=public,
            retained_pet_after=current,native_pet_after=o.pet);t.persist()
        if len(checks)!=13 or not all(checks.values()):raise RuntimeError('owned slot roundtrip whole restoration differs')
        t.receipt.update(completed=True,phase='owned_stable_slot_roundtrip_restored',
            qualified_scope='Native pet4 moved to stable5, returned to active0 and recovered by ordinary known Call Pet; separate remote closure required.')
        return
    current=pets(6)
    if slot not in (0,5) or not pet_identity(e['baseline_pets'],current,slot):raise RuntimeError('owned stored pet slot or identity differs')
    rendering,_=read_page(t,'stable_slot_rendering','state','/tcui')
    state,frame,probe=panel(t,'stable_slot_before',slot)
    t.receipt.update(slot=slot,state=state,frame=frame,public_stable=probe,retained_pet_before=current,
        observed_framerate=rendering.get('framerate'),completed=False,input_sent=False);t.persist()
    if action=='refresh':
        t.receipt.update(completed=True,phase='await_owned_stable_slot_review');return
    staged=closed(source)
    if (staged.get('phase')!='await_owned_stable_slot_review' or staged.get('opening_source')!=bound(opening) or
        staged.get('actor')!=t.fixture or staged.get('runtime')!=t.receipt['runtime'] or staged.get('slot')!=slot or
        staged.get('retained_pet_before')!=current or destination!=5-slot):
        raise RuntimeError('reviewed native slot staging differs')
    d=reviewed(t,review_path,'Move Harnesswolf')
    if d.get('frame')!=staged.get('frame') or d.get('source')!=bound(source) or d.get('destination')!=destination:
        raise RuntimeError('slot screen review is not bound to its exact staged source')
    def point(api_slot):
        rows=[b for b in probe['buttons'] if b.get('slot')==api_slot and b.get('visible') is True and b.get('enabled') is True]
        if len(rows)!=1:raise RuntimeError('stock slot button is unavailable')
        b=rows[0];return [round(b['x']/65535*1280),round(b['y']/65535*720)]
    start,end=point(slot+1),point(destination+1)
    if d.get('point')!=start or d.get('end')!=end:raise RuntimeError('reviewed slot button points differ from current public controls')
    if rendering.get('framerate',0)<8 or rendering.get('cursor_info'):
        raise RuntimeError('slot move requires normally rendering scout and an empty cursor')
    path=lab.ROOT/'run/owned_stable_request_probe.json'
    if path.exists():raise RuntimeError('another owned capture is armed')
    started=time.time();config={'schema':'client442_owned_stable_request_probe_v1','session':session,'owner':6,
        'native_master_guid':e['capture_config']['native_master_guid'],'modern_master_guid':e['capture_config']['modern_master_guid'],
        'created_at':started,'expires_at':started+90,'slot_roundtrip':{'pet_number':4,'slots':[0,5]}}
    lab.private_write(path,json.dumps(config,indent=2)+'\n');digest=lab.sha256(path)
    t.receipt.update(capture_config=config,capture_config_sha256=digest,move_source=bound(source),
        destination=destination,ordinary_input={'kind':'drag','start':start,'end':end,'duration':.8});t.persist()
    try:
        t.receipt['input_sent']=True;t.persist();t.execute(t.receipt['ordinary_input'])
        after,after_frame=read_current_page(t,'stable_slot_after','stables',
            lambda s:len(s.get('stable_probe',{}).get('pets',[]))==1 and
                s['stable_probe']['pets'][0].get('slot')==destination+1)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline and not pet_identity(e['baseline_pets'],pets(6),destination):time.sleep(.2)
        rows=[p for p in entries(lab.ROOT/'evidence/owned_stable_request_packets.jsonl') if
            p.get('session')==session and p.get('time',0)>=started]
        o.poll();checks=verify_packets(rows,slot,destination,config['native_master_guid'])
        checks.update(native_persisted_slot=pet_identity(e['baseline_pets'],pets(6),destination),
            native_runtime_pet_removed=not o.present(),stock_stable_open=after['stable_probe'].get('visible') is True,
            public_slot=after['stable_probe']['pets'][0].get('slot')==destination+1,
            ui_clean=not after.get('lua_errors') and not after.get('blocked_actions'),protected_actors=all(protected(old).values()))
        t.receipt.update(capture_packets=rows,move_checks=checks,after_state=after,after_frame=after_frame,
            retained_pet_after=pets(6));t.persist()
        if not all(checks.values()):raise RuntimeError('ordinary native slot move or public outcome differs')
        t.receipt.update(completed=True,phase='owned_stable_slot_move_verified')
    finally:
        t.receipt['capture_packets']=[p for p in entries(lab.ROOT/'evidence/owned_stable_request_packets.jsonl') if
            p.get('session')==session and p.get('time',0)>=started]
        if lab.sha256(path)!=digest:raise RuntimeError('owned slot probe changed; refusing disarm')
        path.unlink();t.receipt['capture_disarmed']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['refresh','move','finish'])
    for k in ('preparation','entry','opening','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--slot',type=int,choices=[0,5],default=0);p.add_argument('--destination',type=int,choices=[0,5]);a=p.parse_args()
    if a.action in ('move','finish') and not a.source:p.error('requires a closed source')
    if a.action=='move' and (not a.review or a.destination is None):p.error('requires a separately reviewed destination')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.opening,a.action,a.source,a.review,a.slot,a.destination)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
