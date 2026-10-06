"""Read owned command rows and pet positions through the passive addon page."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_owned_class_fixture import prepared,origin_checks,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_follow_capture import FollowPresence


def read(t,label):
    t.submit_chat('/tcui petcommands',any_mode=True)
    try:
        state,frame=t.observe(label,mode='petcommands')
        if state.get('observer_version')!=133 or 'pet_commands' not in state:
            raise RuntimeError('requires the installed passive pet-command observer133')
        value={'time':time.time(),'probe':state['pet_commands'],'frame':frame,
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        t.receipt.setdefault('pet_command_observations',[]).append(value);t.persist();return value
    finally:t.submit_chat('/tcui state',any_mode=True)


def expected_guid(pet):
    guid=pet['guid'];return f"Pet-0-1-{pet['map']}-0-{guid>>32&0xfffff}-{guid&0xffffffff:010X}"


def follow_row(probe):
    rows=[r for r in probe.get('actions',[]) if r.get('available') and r.get('is_token')
        and r.get('name')=='PET_ACTION_FOLLOW']
    return rows[0] if len(rows)==1 else None


def suite(t,preparation,entry):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);o=FollowPresence(session,t.fixture['guid'],e['started_at']).poll()
    if t.fixture['guid']!=5 or not o.present():raise RuntimeError('requires the trained owned Imp entry')
    sample=read(t,'pet_commands');p=sample['probe'];row=follow_row(p)
    checks={'owner':p.get('owner_guid')==t.guid,'owned_pet':p.get('pet_guid')==expected_guid(o.pet),
        'ten_readable_actions':len(p.get('actions',[]))==10 and all(r['available'] for r in p['actions']),
        'active_follow':bool(row and row['active']),'player_position_available':p['player_position'].get('available'),
        'pet_speed_available':isinstance(p.get('pet_speed'),(int,float)),
        'public_range_available':all(any(r['index']==i and r['available'] for r in p.get('interaction_ranges',[])) for i in (2,3)),
        'ui_clean':sample['ui_clean'],**origin_checks(old)}
    t.receipt.update(native_session=session,native_pet=o.pet,checks=checks,completed=all(checks.values()),
        sources=[{'path':str(v.resolve()),'sha256':lab.sha256(v)} for v in [preparation,entry]],
        qualified_scope='Passive owned pet command and position diagnostics only; no command or movement qualification.')
    t.receipt['position_limits']='UnitPosition pet coordinates are unavailable in the observed client. Raw player height is retained without interpreting it as native Z. Range/speed observations remain separate.'
    if not all(checks.values()):raise RuntimeError('public pet command diagnostics differ')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['preparation','entry','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure','checks']}),flush=True)
