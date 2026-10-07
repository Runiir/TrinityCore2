"""Source-bound normal empty-slot moves repair the excluded native swap's rows."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,pets,saved,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_stable_slots import bound
from .interaction_hunter_stable_pair import identities,public_rows,expected_rows
from .interaction_hunter_stable_capture import StablePetOracle
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_pet_target import pair
from .interaction_observation import read_page,read_current_page
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import entries


def failed_source(t,path,preparation,entry,session):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():
        raise RuntimeError('requires private excluded native pair swap')
    f=json.loads(path.read_text());checks=f.get('move_checks',{})
    if (f.get('completed') is not False or not f.get('finished_at') or
        f.get('failure')!='RuntimeError: ordinary occupied pair slot swap differs' or
        f.get('actor')!=t.fixture or f.get('runtime')!=t.receipt['runtime'] or f.get('native_session')!=session or
        f.get('fixture_source')!=bound(preparation) or f.get('entry_source')!=bound(entry) or
        (f.get('number'),f.get('destination'),f.get('source_slot'),f.get('swap_number'))!=(4,5,0,6) or
        f.get('capture_disarmed') is not True or len(checks)!=12 or
        any(checks.get(k) is not False for k in ('native_pair_slots','public_pair_slots')) or
        not all(v for k,v in checks.items() if k not in ('native_pair_slots','public_pair_slots'))):
        raise RuntimeError('requires exact saved-slot-only failed native occupied return')
    return f


def run(t,preparation,entry,failed,action,source=None,review_path=None,destination=6):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    entered=entry_source(t,entry,session,preparation);f=failed_source(t,failed,preparation,entry,session)
    current=pets(6);o=StablePetOracle(session,6,entered['started_at']).poll()
    if source:
        e=closed(source)
        if (e.get('runtime')!=t.receipt['runtime'] or e.get('actor')!=t.fixture or
            e.get('failed_source')!=bound(failed) or e.get('native_session')!=session):
            raise RuntimeError('source-bound pair recovery differs')
        expected=e['retained_pet_after']
    else:expected=f['retained_pet_after']
    if (not identities(expected,current) or o.present() or pair(o.player,'UNIT_FIELD_SUMMON') or
        saved(6)!=entered['entered_saved'] or resources(Inventory(lab.ROOT,session,6).poll())!=entered['resources'] or
        not all(protected(old).values()) or (lab.ROOT/'run/owned_stable_request_probe.json').exists()):
        raise RuntimeError('excluded pair recovery owner/pets/preservation baseline differs')
    t.receipt.update(failed_source=bound(failed),entry_source=bound(entry),native_session=session,
        retained_pet_before=current,qualification_added=False,input_sent=False,packet_bodies_retained=False,
        qualified_scope='Normal source-bound fixture cleanup only. Failed whole occupied swap remains excluded; '
            'no native SQL correction, pet deletion or gameplay qualification.');t.persist()
    rendering,_=read_page(t,'pair_recovery_core','state','/tcui')
    state,frame=read_page(t,'pair_recovery_staged','stables','/tcui stables');probe=state['stable_probe']
    logical=5 if current[0]['slot']==0 else current[0]['slot']
    expected_public=[{**r,'slot':logical if r['id']==4 else 0} for r in current]
    if (probe.get('visible') is not True or public_rows(probe)!=expected_rows(expected_public) or
        not ((logical==5 and destination==6) or (logical==6 and destination==5)) or
        next(r for r in current if r['id']==6)['slot']!=0 or
        any(r['active'] for r in current)):
        raise RuntimeError('exact no-runtime empty stable recovery cells differ')
    t.receipt.update(state=state,frame=frame,logical_source=logical,destination=destination,
        retained_pet_after=current,phase='await_owned_pair_recovery_review');t.persist()
    if action=='stage':t.receipt['completed']=True;return
    if not source or e.get('phase')!='await_owned_pair_recovery_review' or e.get('destination')!=destination:
        raise RuntimeError('requires current source-bound staged recovery')
    d=reviewed(t,review_path,'Recover Harnesswolf')
    if d.get('source')!=bound(source) or d.get('frame')!=e['frame'] or d.get('destination')!=destination:
        raise RuntimeError('pair cleanup review differs')
    def point(slot):
        buttons=[b for b in probe['buttons'] if b.get('slot')==slot+1 and b.get('visible') and b.get('enabled')]
        if len(buttons)!=1:raise RuntimeError('reviewed empty-slot recovery button unavailable')
        return [round(buttons[0]['x']/65535*1280),round(buttons[0]['y']/65535*720)]
    start,end=point(logical),point(destination)
    if d.get('point')!=start or d.get('end')!=end or rendering.get('framerate',0)<8 or rendering.get('cursor_info'):
        raise RuntimeError('fresh reviewed recovery geometry/cursor differs')
    started=time.time();t.receipt.update(input_sent=True,source=bound(source),recovery_started_at=started);t.persist()
    t.execute({'kind':'drag','start':start,'end':end,'duration':.8})
    target=[{**r,'slot':destination if r['id']==4 else 0} for r in current]
    after,frame=read_current_page(t,'pair_recovery_after','stables',lambda s:
        public_rows(s.get('stable_probe',{}))==expected_rows(target))
    lab.server_command('saveall');time.sleep(.5);retained=pets(6);o.poll()
    t.receipt['packet_metadata']=[p for p in entries(lab.ROOT/'logs/modern_world.jsonl') if
        p.get('session')==session and started<=p.get('time',0)<=time.time() and p.get('name') in
        ('CMSG_SET_PET_SLOT','SMSG_PET_SLOT_UPDATED','SMSG_STABLE_RESULT','SMSG_PET_STABLE_RESULT')]
    checks={'native_pair_slots':identities(current,retained,{4:destination,6:0},{4:0,6:0}),
        'public_pair_slots':public_rows(after['stable_probe'])==expected_rows(retained),
        'no_runtime_pet':not o.present() and pair(o.player,'UNIT_FIELD_SUMMON')==0,
        'protected_actors':all(protected(old).values()),'saved_rows':saved(6)==entered['entered_saved'],
        'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
    t.receipt.update(recovery_checks=checks,state=after,frame=frame,retained_pet_after=retained,
        phase='owned_pair_slot_recovery_verified',completed=all(checks.values()))
    if not all(checks.values()):raise RuntimeError('normal empty-slot pair recovery preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','move'])
    for k in ('preparation','entry','failed','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--destination',type=int,choices=[5,6],default=6);a=p.parse_args()
    if a.action=='move' and (not a.source or not a.review):p.error('requires separate fresh staged review')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.failed,a.action,a.source,a.review,a.destination)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','recovery_checks')}),flush=True)
