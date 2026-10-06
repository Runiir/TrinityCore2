"""Capture stock Stay without admitting it, then restore through captured Follow."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,origin_checks,saved,pets,character,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_target import pair,source,retained_imp
from .interaction_pet_dismiss import vitals,public_pet
from .interaction_pet_summon import public_pet_matches
from .interaction_pet_follow_capture import FollowPresence,follow_request
from .interaction_pet_control_training import protected
from .interaction_spellbook_recon import resources
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import latest
from .world.gameobjects import modern_guid
from .world.objects import INDEX


def suite(t,preparation,entry,probe):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);p=source(t,probe,session,entry)
    if (t.fixture['guid']!=5 or t.receipt['runtime']['modern_world']['build']['binary_sha256']!=
        'e6ef1a8aa6c713e9bd4d55fb005566e8a2b488915526a0b79b713ccab3791024'):
        raise RuntimeError('requires the captured Follow and nonfatal rejection build')
    o=FollowPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    retained=pets(5);identity=retained_imp(t.fixture,retained)
    if (not o.present() or pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')!=5 or
        o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=identity['id'] or
        pair(o.player,'UNIT_FIELD_TARGET')!=0 or resources(inventory)!=e['resources'] or
        saved(5)!=e['entered_saved'] or not p.get('native_control_demon_known') or
        [80388,1,0] not in e['entered_saved']['spells'] or not all(protected(old).values())):
        raise RuntimeError('owned trained Stay capture eligibility differs')
    guid=o.pet['guid'];catalogs=[c for c in o.catalogs if c['guid']==guid]
    if not catalogs or catalogs[-1]['command']!=1:
        raise RuntimeError('baseline is not native Follow; no Stay input sent')
    baseline_vitals=vitals(o);before,frame=t.observe('stay_capture_baseline')
    if before['target'].get('exists'):raise RuntimeError('public baseline selection is not empty')
    t.receipt.update(sources=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (entry,probe)],
        native_session=session,native_pet_before=o.pet,native_catalog=catalogs[-1],
        native_vitals_before=baseline_vitals,retained_pet_before=retained,before_frame=frame,
        qualification_added=False,qualified_scope='Diagnostic ordinary Stay request and healthy rejection only. '
            'Normal Follow restores the fixture; no Stay/Follow mode or movement qualification.')
    t.persist();since=time.time();t.receipt['stay_started_at']=since;t.persist()
    try:
        def outcome(b,a,selected):
            o.poll();requests=[r for r in o.requests if r['time']>=since]
            modern=[r for r in requests if r['name']=='CMSG_PET_ACTION' and r['direction']=='from_client']
            native=[r for r in requests if r['direction']=='to_native']
            decoded=follow_request(modern[0]) if len(modern)==1 else None
            rejected=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
                r.get('time',0)>=since and r.get('event')=='pet_action_translation_rejected')
            checks={'ordinary_stay':selected=='stay','one_modern_request':len(modern)==1,
                'submitted_owned_guid':bool(decoded and decoded['guid']==list(modern_guid(guid,o.pet['map']))),
                'captured_stay_shape':bool(decoded and decoded['word']==0x03800000 and
                    decoded['target']==[0,0] and decoded['position']==[0.,0.,0.]),
                'no_native_command':not native,'no_abandon':not any(r['name']=='CMSG_PET_ABANDON' for r in requests),
                'attributed_rejection':bool(rejected and rejected.get('error')=='unsupported pet action shape'),
                'native_pet_present':o.present() and o.pet['guid']==guid,
                'owned_session_online':character(5,2)['online']==1 and a.get('guid')==t.guid,
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'owned_stay_request_captured_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'decoded':decoded,'rejection':rejected,
                    'qualification_added':False}}
        require(t.step('diagnostic.pet_stay.request','Capture one stock Stay request and the healthy rejection.',
            {'stay':{'kind':'chat','value':'/petstay','description':'Use the stock secure pet Stay command once.'}},
            outcome,diagnostic_action='stay'),'owned_stay_request_captured_pass')
    finally:
        t.clean_panels();o.poll()
        submitted=[r for r in o.requests if r['time']>=since and r['direction']=='from_client' and
            r['name']=='CMSG_PET_ACTION']
        if len(submitted)==1:
            follow_since=time.time();t.receipt['follow_cleanup_started_at']=follow_since;t.persist()
            def follow_outcome(b,a,selected):
                o.poll();requests=[r for r in o.requests if r['time']>=follow_since]
                modern=[r for r in requests if r['name']=='CMSG_PET_ACTION' and r['direction']=='from_client']
                native=[r for r in requests if r['name']=='CMSG_PET_ACTION' and r['direction']=='to_native']
                decoded=follow_request(modern[0]) if len(modern)==1 else None
                expected=struct.pack('<QIQfff',guid,0x07000001,0,0,0,0).hex()
                checks={'ordinary_follow':selected=='follow','one_modern_follow':bool(decoded and
                    decoded['guid']==list(modern_guid(guid,o.pet['map'])) and decoded['word']==0x03800001 and
                    decoded['target']==[0,0] and decoded['position']==[0.,0.,0.]),
                    'exact_native_follow':len(native)==1 and native[0]['body']==expected,
                    'no_abandon':not any(r['name']=='CMSG_PET_ABANDON' for r in requests),
                    'native_pet_present':o.present() and o.pet['guid']==guid,
                    'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
                return {'status':'owned_follow_cleanup_forwarded_pass' if all(checks.values()) else 'client_or_protocol_failure',
                    'oracle':{'checks':checks,'requests':requests,'qualification_added':False}}
            require(t.step('fixture.pet_follow.restore','Restore the original Follow command through its captured mapping.',
                {'follow':{'kind':'chat','value':'/petfollow','description':'Use the stock secure Follow command once for cleanup.'}},
                follow_outcome,diagnostic_action='follow'),'owned_follow_cleanup_forwarded_pass')
        public=public_pet(t,'stay_capture_restored_pet');state,frame=t.observe('stay_capture_complete');o.poll()
        current=pets(5);keys=('id','entry','owner','name','CreatedBySpell','PetType')
        checks=origin_checks(old);checks.update(empty_selection=pair(o.player,'UNIT_FIELD_TARGET')==0 and
            state['target'].get('exists') is False,resources=resources(inventory)==e['resources'],
            saved_rows=saved(5)==e['entered_saved'],position=state['world_position']==before['world_position'],
            panels_closed=not state.get('panels') and not state.get('bags'),
            ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'),
            owned_pet=o.present() and o.pet['guid']==guid and pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')==5 and
                o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])==identity['id'],
            native_vitals=vitals(o)==baseline_vitals,public_pet=public_pet_matches(o,public,identity),
            retained_pet=len(current)==1 and all(current[0].get(k)==identity[k] for k in keys))
        t.receipt.update(restoration_checks=checks,protected_checks=protected(old),restored_frame=frame,
            restored_public_pet=public,native_pet_after=o.pet,retained_pet_after=current,
            limits='No native Stay command. Follow cleanup is exactly forwarded; actual movement and public active-command '
                'selection are unqualified. Original player/pet resources, identity, selection and panels restore.');t.persist()
        if not all(checks.values()) or not all(t.receipt['protected_checks'].values()):
            raise RuntimeError('owned Stay capture restoration differs')
    t.receipt.update(completed=True,phase='owned_stay_request_capture_complete')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','probe','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry,a.probe)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
