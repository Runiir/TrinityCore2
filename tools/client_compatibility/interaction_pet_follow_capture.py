"""Capture one ordinary Follow request while the owned Imp already follows."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,origin_checks,saved,pets,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_target import pair,source,retained_imp
from .interaction_pet_dismiss import Presence,vitals,public_pet
from .interaction_pet_summon import public_pet_matches
from .interaction_pet_control_training import protected
from .interaction_spellbook_recon import resources
from .interaction_macros import require
from .observation.inventory import Inventory
from .world.buffer import Reader
from .world.gameobjects import modern_guid
from .world.objects import INDEX


class FollowPresence(Presence):
    def __init__(self,session,owner,started):
        super().__init__(session,owner,started);self.catalogs=[]

    def inspect_packet(self,p):
        if p.get('name')=='SMSG_PET_SPELLS' and p.get('direction')=='from_native':
            r=Reader(bytes.fromhex(p['body']));guid=r.unpack('Q')[0]
            if guid:
                family,duration,react,command,flags=r.unpack('HIBBH')
                self.catalogs.append({'packet':p,'guid':guid,'family':family,'duration':duration,
                    'react':react,'command':command,'flags':flags})


def follow_request(packet):
    r=Reader(bytes.fromhex(packet['body']));guid=r.guid();word=r.unpack('I')[0]
    target=r.guid();position=r.unpack('fff');r.end()
    return {'guid':list(guid),'word':word,'action_type':word>>23,'action_value':word&0x7fffff,
        'target':list(target),'position':list(position)}


def suite(t,preparation,entry,probe):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);p=source(t,probe,session,entry)
    if (t.fixture['guid']!=5 or t.receipt['runtime']['modern_world']['build']['binary_sha256']!=
        '08b77db9799b749ead65906e91d78fdcc72887bf8fec9bfd77d728b891de6e55'):
        raise RuntimeError('capture requires the actual closed narrow Dismiss build and trained owned Imp')
    o=FollowPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    retained=pets(5);identity=retained_imp(t.fixture,retained)
    if (not o.present() or pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')!=5 or
        o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=identity['id'] or
        pair(o.player,'UNIT_FIELD_TARGET')!=0 or resources(inventory)!=e['resources'] or
        saved(5)!=e['entered_saved'] or not p.get('native_control_demon_known') or
        [80388,1,0] not in e['entered_saved']['spells'] or not all(protected(old).values())):
        raise RuntimeError('closed owned Follow capture eligibility differs')
    guid=o.pet['guid'];catalogs=[c for c in o.catalogs if c['guid']==guid]
    if not catalogs or catalogs[-1]['command']!=1:
        raise RuntimeError('native baseline is not already Follow; no command input sent')
    catalog=catalogs[-1];baseline_vitals=vitals(o);before,frame=t.observe('follow_capture_baseline')
    if before['target'].get('exists'):raise RuntimeError('original public selection is not empty')
    t.receipt.update(sources=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (entry,probe)],
        native_session=session,native_pet_before=o.pet,native_player_before=dict(o.player),
        native_catalog=catalog,native_vitals_before=baseline_vitals,retained_pet_before=retained,before_frame=frame,
        qualification_added=False,
        qualified_scope='Diagnostic stock Follow request capture only while native command mode is already Follow. '
            'No native Follow outcome, movement or pets.command_follow qualification.')
    t.persist()
    try:
        since=time.time();t.receipt['follow_started_at']=since;t.persist()
        def outcome(b,a,selected):
            o.poll();requests=[r for r in o.requests if r['time']>=since]
            modern=[r for r in requests if r['name']=='CMSG_PET_ACTION' and r['direction']=='from_client']
            native=[r for r in requests if r['direction']=='to_native']
            decoded=follow_request(modern[0]) if len(modern)==1 else None
            checks={'ordinary_follow':selected=='follow','one_modern_request':len(modern)==1,
                'submitted_owned_guid':bool(decoded and decoded['guid']==list(modern_guid(guid,o.pet['map']))),
                'follow_action':bool(decoded and (decoded['action_type'],decoded['action_value'])==(7,1)),
                'unmapped_native_outcome':not native,'no_abandon':not any(r['name']=='CMSG_PET_ABANDON' for r in requests),
                'native_pet_present':o.present() and o.pet['guid']==guid,
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'owned_follow_request_captured_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'decoded':decoded,'qualification_added':False}}
        require(t.step('diagnostic.pet_follow.request','Capture one ordinary Follow request for the already-following owned Imp.',
            {'follow':{'kind':'chat','value':'/petfollow','description':'Use the stock secure pet Follow command once.'}},
            outcome,diagnostic_action='follow'),'owned_follow_request_captured_pass')
    finally:
        t.clean_panels();public=public_pet(t,'follow_capture_restored_pet');state,frame=t.observe('follow_capture_complete');o.poll()
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
            limits='The unchanged native Follow baseline and ordinary request are captured. Public pet-command selection '
                'and actual following movement remain unqualified; no Stay input is sent in this probe.');t.persist()
        if not all(checks.values()) or not all(t.receipt['protected_checks'].values()):
            raise RuntimeError('owned Follow capture restoration differs')
    t.receipt.update(completed=True,phase='owned_follow_request_capture_complete')


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
