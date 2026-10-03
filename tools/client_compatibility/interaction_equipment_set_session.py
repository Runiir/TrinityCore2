"""Full-session persistence of one normally created owned equipment set."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_lifecycle import Packets,request_logout
from .interaction_session_persist import public,close
from .interaction_tooltips import baseline
from .interaction_equipment_sets import sets,NAME
from .interaction_equipment_set_roundtrip import stable,public_named,open_manager
from .interaction_operations import click_case,controls
from .interaction_macros import require


def native():return {'native':stable(baseline()),'sets':stable(sets())}


def owned_source(path):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence') or path.name!='episode.json':raise ValueError('require an owned episode')
    saved=json.loads(path.read_text())
    if not saved.get('completed') or not saved.get('finished_at') or saved.get('failure'):raise RuntimeError('source did not pass')
    return path,saved


def logout(t,source):
    source,saved=owned_source(source);current=native()
    if (saved['actor']!=t.fixture or saved['runtime']!=t.receipt['runtime'] or
        not saved.get('native_resources_preserved') or saved['native_after']!=current):
        raise RuntimeError('set session trial requires unchanged successful creation source')
    t.clean_panels();state,frame=t.observe('before_set_logout');probe,valid=public_named(t,'set_catalog_before_logout',NAME)
    if not valid:raise RuntimeError('public owned set differs before logout')
    session=actors.session_entry(t.fixture)['session']
    t.receipt.update(phase='set_logout',source={'file':str(source),'sha256':lab.sha256(source)},
        baseline={'native':current,'public':public(state),'frame':frame,'set':probe,'session':session},
        bridge=identity('modern_world'),native_server=identity('worldserver'));t.persist()
    packets=Packets(session);started=request_logout(t,packets,'equipment_set_complete',False)
    deadline=time.monotonic()+32
    while not (packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native') and
               packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','from_native')):
        if time.monotonic()>deadline:raise RuntimeError('equipment-set logout/enumeration deadline exceeded')
        time.sleep(.2)
    # Give the normal asynchronous character model time to appear before the
    # separate visual review. No input is submitted during this wait.
    time.sleep(3);frame=shot(t.out/'character_selection.png')
    t.receipt['cases'].append({'id':'sets.session_logout','status':'logout_complete_pass',
        'time':started,'frame':frame,'oracle':{'native_complete':True,'native_enumeration':True}})
    t.receipt['character_selection']=frame;t.persist()


def reenter(t,source):
    source,saved=owned_source(source)
    if (saved.get('phase')!='set_logout' or saved['actor']!=t.fixture or saved['runtime']!=t.receipt['runtime'] or
        saved['native_server']!=identity('worldserver') or saved['bridge']!=identity('modern_world')):
        raise RuntimeError('set session reentry requires exact actor/client/server source')
    t.receipt.update(phase='set_reenter',source={'file':str(source),'sha256':lab.sha256(source)},
        baseline=saved['baseline'],reviewed_character_selection=saved['character_selection']);t.persist()
    before=shot(t.out/'reviewed_selection_before.png');started=time.time()
    t.execute({'kind':'key','value':'Return','hold':.4});time.sleep(8)
    state,frame=t.observe('after_set_reentry');probe,valid=public_named(t,'set_catalog_after_reentry',NAME)
    current=native();packets=Packets(saved['baseline']['session'])
    checks={'public_baseline':public(state)==saved['baseline']['public'],
        'native_baseline':current==saved['baseline']['native'],'public_set':valid,
        'ordinary_login':packets.has(started,'CMSG_PLAYER_LOGIN','from_client'),
        'native_login':packets.has(started,'SMSG_LOGIN_VERIFY_WORLD','from_native'),
        'native_set_list':packets.has(started,'SMSG_EQUIPMENT_SET_LIST','from_native'),
        'modern_set_list':packets.has(started,'SMSG_LOAD_EQUIPMENT_SET','to_client'),
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt['cases'].append({'id':'character.equipment_set_session_persist','time':started,
        'status':'equipment_set_session_pass' if all(checks.values()) else 'client_or_protocol_failure',
        'before_frame':before,'after_frame':frame,'oracle':{'checks':checks,'native':current,'public':probe}});t.persist()
    if not all(checks.values()):raise RuntimeError('equipment-set full-session persistence differs')
    collapsed=open_manager(t,'sets.session')
    probe,valid=public_named(t,'rendered_set_after_reentry',NAME)
    if not valid or not probe['manager_visible']:raise RuntimeError('preserved set is absent from stock manager')
    state,frame=t.observe('preserved_set_manager')
    t.receipt['rendered_manager']={'state':state,'frame':frame,'public':probe};t.persist()
    if collapsed:
        require(click_case(t,'sets.session.display_restore','Restore the collapsed character sidebar.',
            lambda c:c['name']=='CharacterFrameExpandButton',
            lambda b,a,s:{'status':'character_display_restore_pass' if s and not
                any(c['name']=='PaperDollSidebarTab3' for c in controls(t)) else 'client_or_protocol_failure'}),
            'character_display_restore_pass')
    t.clean_panels();t.receipt['native_after']=native();t.receipt['native_resources_preserved']=t.receipt['native_after']==saved['baseline']['native'];t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('read-only set manager changed native state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['logout','reenter'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--reviewed-character-selection',action='store_true');a=p.parse_args()
    if a.action=='reenter' and not a.reviewed_character_selection:p.error('reentry requires a completed separate lobby visual review')
    t=Trial(a.output,controller='code')
    try:
        (logout if a.action=='logout' else reenter)(t,a.source);close(t,True)
    except Exception as e:close(t,False,f'{type(e).__name__}: {e}')
