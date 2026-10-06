"""Accept one normal owned synthetic Hunter Rename and retain its native change."""
import argparse,json,struct,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import reviewed,saved,pets,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import protected
from .interaction_hunter_rename_capture import baseline,request,NAME
from .interaction_hunter_pet_recon import saved_pet_unchanged,pet_frame_menu
from .interaction_pet_target import PetOracle
from .interaction_pet_command_probe import expected_guid
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import detail
from .interaction_operations import controls,point,click_case
from .interaction_macros import require
from .observation.journal import entries
from .world.objects import INDEX
from .world.gameobjects import modern_guid
from .world.buffer import Reader


def renamed_pet_unchanged(before,after,now):
    expected=[{**p,'name':NAME,'renamed':1} for p in before]
    return saved_pet_unchanged(expected,after,now)


def native_name(packet):
    r=Reader(bytes.fromhex(packet['body']));number,=r.unpack('I');name=bytearray()
    for _ in range(256):
        b=r.raw(1)
        if b==b'\0':break
        name.extend(b)
    else:raise ValueError('native pet name exceeds bound')
    timestamp,declined=r.unpack('IB');r.end()
    if declined:raise ValueError('unexpected native declined pet name')
    return {'pet_number':number,'name':name.decode('ascii'),'timestamp':timestamp}


def modern_name(packet):
    r=Reader(bytes.fromhex(packet['body']));guid=r.guid()
    if not r.bits(1):raise ValueError('modern pet name absent')
    length=r.bits(8);declined=r.bits(1);lengths=[r.bits(7) for _ in range(5)]
    if declined or any(lengths):raise ValueError('unexpected modern declined pet name')
    timestamp,=r.unpack('q');name=r.raw(length).decode('ascii');r.end()
    return {'guid':list(guid),'name':name,'timestamp':timestamp}


def suite(t,preparation,source,review_path):
    old,session,e,o,retained,inv,state,frame,rows=baseline(t,preparation,source,'hunter_rename_confirmation_open')
    d=reviewed(t,review_path,'StaticPopup2Button1')
    if d['frame']['sha256']!=e['frame']['sha256']:raise RuntimeError('reviewed final Rename image differs')
    selected=[c for c in rows if c.get('name')=='StaticPopup2Button1']
    if len(selected)!=1 or point(selected[0])!=d['point']:raise RuntimeError('reviewed final Yes point changed')
    path=lab.ROOT/'run/owned_pet_rename_probe.json'
    if path.exists():raise RuntimeError('another owned Rename capture is armed')
    guid=o.pet['guid'];identity=expected_guid(o.pet);before_timestamp=o.pet['fields'][INDEX['UNIT_FIELD_PET_NAME_TIMESTAMP']]
    started=time.time();config={'schema':'client442_owned_pet_rename_probe_v1','session':session,'owner':6,'pet_number':4,
        'synthetic_name':NAME,'native_pet_guid':guid,'modern_pet_guid':list(modern_guid(guid,0)),
        'created_at':started,'expires_at':started+60}
    lab.private_write(path,json.dumps(config,indent=2)+'\n');digest=lab.sha256(path)
    t.receipt.update(rename_started_at=started,capture_config=config,capture_config_sha256=digest,
        before_pet_name_timestamp=before_timestamp,qualification_added=False);t.persist()
    try:
        def outcome(b,a,s):
            t.receipt['rename_confirmation_sent']=s=='yes'
            return {'status':'owned_hunter_name_visible' if s=='yes' and a.get('target',{}).get('name')==NAME and
                a['target'].get('guid')==identity and not a.get('panels') and
                not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure'}
        require(t.step('pets.rename','Confirm the reviewed one-time synthetic name of this owned Hunter pet.',
            {'yes':{'kind':'click','value':d['point'],'hold':.4,'description':'Click the observed stock Yes once.'}},
            outcome,diagnostic_action='yes',await_state=lambda a:a.get('target',{}).get('name')==NAME),
            'owned_hunter_name_visible')
        o.poll();after=pets(6)
        packets=[p for p in entries(lab.ROOT/'evidence/owned_pet_rename_packets.jsonl') if p.get('session')==session and
            p.get('time',0)>=started and p.get('name')=='CMSG_PET_RENAME']
        client=[p for p in packets if p['direction']=='from_client'];native=[p for p in packets if p['direction']=='to_native']
        reads=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('session')==session and
            p.get('time',0)>=started and p.get('name') in ('SMSG_PET_NAME_QUERY_RESPONSE','SMSG_QUERY_PET_NAME_RESPONSE')]
        n=[{'packet':p,'decoded':native_name(p)} for p in reads if p['direction']=='from_native']
        m=[{'packet':p,'decoded':modern_name(p)} for p in reads if p['direction']=='to_client']
        state,frame=t.observe('hunter_renamed');timestamp=o.pet['fields'].get(INDEX['UNIT_FIELD_PET_NAME_TIMESTAMP'])
        checks={'one_modern_request':len(client)==1 and request(client[0],o.pet)['name']==NAME,
            'one_native_rename':len(native)==1 and native[0]['body']==(struct.pack('<Q',guid)+NAME.encode()+b'\0\0').hex(),
            'owned_pet_present':o.present() and o.pet['guid']==guid,
            'native_permission_removed':o.pet['fields'].get(INDEX['UNIT_FIELD_BYTES_2'],0)>>16&255==2,
            'native_timestamp_advanced':timestamp>before_timestamp and int(started)<=timestamp<=time.time(),
            'native_name_reply':bool(n) and all(x['decoded']=={'pet_number':4,'name':NAME,'timestamp':timestamp} for x in n),
            'modern_name_reply':bool(m) and all(x['decoded']=={'guid':list(modern_guid(guid,0)),'name':NAME,'timestamp':timestamp} for x in m),
            'public_target':state.get('target',{}).get('guid')==identity and state['target'].get('name')==NAME,
            'saved_one_time_name':renamed_pet_unchanged(retained,after,time.time()),
            'resources':resources(inv.poll())==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],
            'position':state['world_position']==t.receipt['baseline_world_position'],
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
        t.receipt.update(rename_checks=checks,rename_packets=packets,name_replies={'native':n,'modern':m},
            after_native_pet=o.pet,renamed_pet_rows=after,renamed_frame=frame,protected_checks=protected(old));t.persist()
        if not all(checks.values()):raise RuntimeError('native/public one-time owned Hunter Rename differs')
        oracle=PetOracle(session,6,0).poll();pet_frame_menu(t,oracle,identity,name=NAME,rename_allowed=False);t.clean_panels()
        require(click_case(t,'fixture.hunter_rename.public_book','Read the renamed owned pet through the stock book.',
            lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'hunter_pet_book_pass' if s and
                'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'}),'hunter_pet_book_pass')
        public=detail(t,'hunter_renamed_public')['pet'];t.receipt['public_pet']=public
        if not (public.get('exists') and public.get('guid')==identity and public.get('name')==NAME):
            raise RuntimeError('public owned Hunter pet name differs')
    finally:
        if lab.sha256(path)!=digest:raise RuntimeError('armed Rename capture changed; refusing to remove it')
        path.unlink();t.receipt['capture_disarmed']=True;t.clean_panels();target=e['initial_target']
        if not target.get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        elif target.get('name')=='Benjamin Foxworthy':t.execute({'kind':'chat','value':'/targetexact Benjamin Foxworthy'})
        else:raise RuntimeError('owned Rename initial selection cannot be restored normally')
        state,frame=t.observe('hunter_rename_restored');o.poll();after=pets(6)
        checks={'resources':resources(inv.poll())==e['baseline_resources'],'saved_rows':saved(6)==e['baseline_saved'],
            'one_time_name_retained':renamed_pet_unchanged(retained,after,time.time()),'owned_pet_present':o.present(),
            'selection':state.get('target',{}).get('guid')==target.get('guid'),
            'position':state['world_position']==t.receipt['baseline_world_position'],'panels_closed':not state.get('panels'),
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
        t.receipt.update(restoration_checks=checks,restored_frame=frame,restored_pets=after);t.persist()
        if not all(checks.values()):raise RuntimeError('owned Hunter Rename preservation differs')
    t.receipt.update(completed=True,phase='hunter_renamed',qualified_scope='One normal owned Hunter Rename to Harnesswolf; '
        'native persistence, one-time permission removal and public name verified. Synthetic retained pet name is intentional.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('preparation','source','review','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.source,a.review)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase')}),flush=True)
