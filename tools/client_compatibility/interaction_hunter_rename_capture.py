"""Capture one stock synthetic Rename request while native translation is absent."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,saved,pets,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import protected
from .interaction_hunter_training import prior
from .interaction_hunter_pet_recon import starting_wolf,saved_pet_unchanged
from .interaction_pet_dismiss import Presence
from .interaction_pet_command_probe import expected_guid
from .interaction_spellbook_recon import resources
from .interaction_operations import point,controls
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX
from .world.gameobjects import modern_guid
from .world.buffer import Reader

NAME='Harnesswolf'
PROMPT='Enter desired name of pet:'
CONFIRM="Name your pet 'Harnesswolf'?"


def dialog_matches(state,rows,phase,pet):
    confirmation=phase=='hunter_rename_confirmation_open'
    panel='StaticPopup2' if confirmation else 'StaticPopup1'
    text=CONFIRM if confirmation else PROMPT
    labels=('Yes','No') if confirmation else ('Accept','Cancel')
    fields=state.get('edit_fields',[])
    expected='' if phase=='hunter_rename_dialog_open' else NAME
    field_ok=(not fields if confirmation else len(fields)==1 and
        fields[0].get('name')=='StaticPopup1EditBox' and fields[0].get('text')==expected)
    return (state.get('panels')==[panel] and state.get('target',{}).get('guid')==expected_guid(pet) and
        field_ok and not state.get('lua_errors') and not state.get('blocked_actions') and
        all(sum(c.get('name')==panel+'Button'+str(i) and c.get('text')==label and
            c.get('context')==text and c.get('enabled') is True for c in rows)==1
            for i,label in enumerate(labels,1)))


def request(packet,pet):
    r=Reader(bytes.fromhex(packet['body']));guid=r.guid();number,=r.unpack('i')
    size=r.bits(8);declined=r.bits(1);padding=r.bits(7);name=r.raw(size).decode('ascii');r.end()
    if (tuple(guid)!=tuple(modern_guid(pet['guid'],pet['map'])) or number!=4 or
        name!=NAME or size!=11 or declined or padding):raise RuntimeError('captured synthetic Rename shape differs')
    return {'guid':list(guid),'pet_number':number,'name':name,'declined_names':False}


def baseline(t,preparation,source,phase):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session'];e=prior(t,source,session,phase)
    if tuple(t.fixture.get(k) for k in ('guid','class','level','character_name'))!=(6,3,10,'Harnesshunt'):
        raise RuntimeError('requires the exact normally controlled Hunter')
    o=Presence(session,6,0).poll();retained=pets(6);inv=Inventory(lab.ROOT,session,6).poll()
    if (not starting_wolf(retained,6) or not o.present() or o.pet['map']!=0 or o.pet['guid']!=e['native_pet']['guid'] or
        o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=4 or
        o.pet['fields'].get(INDEX['UNIT_FIELD_BYTES_2'],0)>>16&255!=3 or
        resources(inv)!=e['baseline_resources'] or saved(6)!=e['baseline_saved'] or
        not saved_pet_unchanged(e['retained_pet'],retained,time.time())):
        raise RuntimeError('owned Wolf Rename authority or baseline changed')
    state,frame=t.observe('hunter_rename_current');rows=controls(t)
    position=e.get('baseline_world_position',e['state']['world_position'])
    if not dialog_matches(state,rows,phase,o.pet) or state.get('world_position')!=position:
        raise RuntimeError('current stock owned Rename dialog differs')
    t.receipt.update(native_session=session,native_pet=o.pet,retained_pet=retained,
        baseline_resources=e['baseline_resources'],baseline_saved=e['baseline_saved'],initial_target=e['initial_target'],
        baseline_world_position=position,
        protected_checks=protected(old),rename_confirmation_sent=False,qualification_added=False)
    return old,session,e,o,retained,inv,state,frame,rows


def suite(t,preparation,source,action,review_path=None,filled=False,confirmed=False):
    phase=('hunter_rename_confirmation_open' if action=='submit' or confirmed else
        'hunter_rename_filled' if action=='accept' or filled else 'hunter_rename_dialog_open')
    old,session,e,o,retained,inv,state,frame,rows=baseline(t,preparation,source,phase)
    if action=='refresh':
        t.receipt.update(state=state,frame=frame,dialog_controls=rows,phase=phase,completed=True,input_sent=False)
        return
    control={'fill':'StaticPopup1EditBox','accept':'StaticPopup1Button1','submit':'StaticPopup2Button1'}[action]
    review=reviewed(t,review_path,control)
    if review['frame']['sha256']!=e['frame']['sha256']:raise RuntimeError('reviewed Rename source image differs')
    selected=[c for c in rows if c.get('name')==control]
    if len(selected)!=1 or point(selected[0])!=review['point']:raise RuntimeError('reviewed Rename control point changed')
    if action=='fill':
        t.execute({'kind':'edit','point':review['point'],'value':NAME})
        state,frame=t.observe('hunter_rename_filled');after=pets(6)
        fields=state.get('edit_fields',[])
        checks={'literal_synthetic_name':len(fields)==1 and fields[0].get('name')==control and fields[0].get('text')==NAME,
            'resources':resources(inv.poll())==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],
            'pet_rows':saved_pet_unchanged(retained,after,time.time()),'dialog_open':state.get('panels')==['StaticPopup1'],
            'position':state.get('world_position')==t.receipt['baseline_world_position'],
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
        t.receipt.update(state=state,frame=frame,dialog_controls=controls(t),dialog_checks=checks)
        if not all(checks.values()):raise RuntimeError('literal owned synthetic Rename field differs')
        t.receipt.update(phase='hunter_rename_filled',completed=True);return
    if action=='accept':
        t.execute({'kind':'click','value':review['point'],'hold':.4})
        state,frame=t.observe('hunter_rename_confirmation');after=pets(6);rows=controls(t)
        checks={'exact_confirmation':dialog_matches(state,rows,'hunter_rename_confirmation_open',o.pet),
            'resources':resources(inv.poll())==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],
            'pet_rows':saved_pet_unchanged(retained,after,time.time()),
            'position':state.get('world_position')==t.receipt['baseline_world_position'],**protected(old)}
        t.receipt.update(state=state,frame=frame,dialog_controls=rows,dialog_checks=checks)
        if not all(checks.values()):raise RuntimeError('stock synthetic Rename confirmation differs')
        t.receipt.update(phase='hunter_rename_confirmation_open',completed=True);return
    path=lab.ROOT/'run/owned_pet_rename_probe.json'
    if path.exists():raise RuntimeError('another owned Rename capture is already armed')
    started=time.time();config={'schema':'client442_owned_pet_rename_probe_v1','session':session,'owner':6,'pet_number':4,
        'synthetic_name':NAME,'native_pet_guid':o.pet['guid'],'modern_pet_guid':list(modern_guid(o.pet['guid'],o.pet['map'])),
        'created_at':started,'expires_at':started+60}
    lab.private_write(path,json.dumps(config,indent=2)+'\n');digest=lab.sha256(path)
    t.receipt.update(capture_started_at=started,capture_config=config,capture_config_sha256=digest);t.persist()
    try:
        def submitted(b,a,s):
            t.receipt['rename_confirmation_sent']=s=='accept'
            return {'status':'synthetic_rename_submitted' if s=='accept' and not a.get('panels') and
                not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure'}
        require(t.step('diagnostic.hunter_rename.capture','Submit exactly the reviewed synthetic owned pet name once.',
            {'accept':{'kind':'click','value':review['point'],'hold':.4,'description':'Click the observed Accept once.'}},
            submitted,diagnostic_action='accept'),'synthetic_rename_submitted')
        packets=[p for p in entries(lab.ROOT/'evidence/owned_pet_rename_packets.jsonl') if p.get('session')==session and
            p.get('time',0)>=started and p.get('name')=='CMSG_PET_RENAME']
        if len(packets)!=1 or packets[0].get('direction')!='from_client':
            raise RuntimeError('requires one captured synthetic client request and no forwarded native rename')
        t.receipt.update(capture_packets=packets,decoded_request=request(packets[0],o.pet),
            qualified_scope='One actual synthetic stock Rename request captured; translation absent, no rename qualification.')
    finally:
        if lab.sha256(path)!=digest:raise RuntimeError('armed Rename capture changed; refusing to remove it')
        path.unlink();t.receipt['capture_disarmed']=True
        t.clean_panels();target=e['initial_target']
        if target.get('name')=='Benjamin Foxworthy':t.execute({'kind':'chat','value':'/targetexact Benjamin Foxworthy'})
        elif not target.get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        else:raise RuntimeError('Rename source selection cannot be restored normally')
        state,frame=t.observe('hunter_rename_capture_restored');after=pets(6);o.poll()
        checks={'resources':resources(inv.poll())==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],
            'retained_pet':saved_pet_unchanged(retained,after,time.time()),'pet_still_present':o.present(),
            'selection':state.get('target',{}).get('guid')==target.get('guid'),'panels_closed':not state.get('panels'),
            'position':state.get('world_position')==t.receipt['baseline_world_position'],
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
        t.receipt.update(restoration_checks=checks,restored_frame=frame,restored_pets=after);t.persist()
        if not all(checks.values()):raise RuntimeError('unmapped Rename capture restoration differs')
    t.receipt.update(completed=True,phase='hunter_rename_shape_captured',native_rename_forwarded=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('refresh','fill','accept','submit'))
    for name in ('preparation','source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--review',type=Path);p.add_argument('--filled',action='store_true')
    p.add_argument('--confirmed',action='store_true');a=p.parse_args()
    if a.action in ('fill','accept','submit') and not a.review:p.error('requires the fresh separately viewed stock dialog review')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.source,a.action,a.review,a.filled,a.confirmed)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase')}),flush=True)
