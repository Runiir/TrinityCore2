"""Run the stock binding roundtrip with full native and settings restoration."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial,binding_key
from . import interaction_keybindings as bindings
from .interaction_operations import click_case,point
from .interaction_macros import edit_case,require
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .observation.inventory import Inventory
from .interaction_ground_movement import position
from .interaction_actionbar_pages import detail as bar_detail


def suite(t,operations=bindings.suite,preserve_settings=True):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();before,_=t.observe('native_binding_fixture')
    native={'resources':resources(oracle),'stats':native_state(oracle),'spells':known(t.fixture['guid']),
        'actions':saved_actions(t.fixture['guid']),'pose':pose(oracle),'afk':afk(oracle),
        'position':position(t.fixture['guid'])}
    layout=None;t.receipt['native_baseline']=native;t.persist()
    try:
        if preserve_settings:
            open_search(t);layout=detail(t,'original_settings')
            if layout.get('unapplied'):raise RuntimeError('original settings contain unapplied changes')
            require(click_case(t,'fixture.close_original_settings','Close original settings before the binding trial.',
                lambda c:c['text']=='Close',lambda b,a,s:{'status':'fixture_settings_closed' if s and
                    'SettingsPanel' not in a['panels'] else 'client_or_protocol_failure'}),'fixture_settings_closed')
        t.clean_panels();operations(t)
    finally:
        baseline=t.receipt.get('binding_baseline')
        if baseline:
            state,_=t.observe('binding_cleanup_check')
            if state.get('binding_probe')=='TOGGLEFPS':bindings.restore(t,baseline)
        if layout is not None and not layout.get('unapplied'):
            t.clean_panels();field=open_search(t);current=detail(t,'settings_restore_before')
            if current.get('category')!=layout.get('category'):
                category=layout['category']['name']
                require(click_case(t,'fixture.restore_settings_category','Restore the original settings category.',
                    lambda c:c['text']==category[:64],lambda b,a,s:{'status':'settings_category_restored' if s and
                        detail(t,'settings_category')['category']==layout['category'] else 'client_or_protocol_failure'}),
                    'settings_category_restored')
            require(edit_case(t,'fixture.restore_settings_search','Restore the original settings search.',
                lambda c:c['kind']=='EditBox' and point(c)==point(field),layout.get('search') or ''),'ui_edit_pass')
            after=detail(t,'settings_restored');t.receipt['settings_restored']=all(after.get(k)==layout.get(k)
                for k in ['category','search','cvars','values','unapplied']);t.persist()
            require(click_case(t,'fixture.close_restored_settings','Close restored settings.',lambda c:c['text']=='Close',
                lambda b,a,s:{'status':'fixture_settings_closed' if s and 'SettingsPanel' not in a['panels'] else
                    'client_or_protocol_failure'}),'fixture_settings_closed')
            if not t.receipt['settings_restored']:raise RuntimeError('original settings differ after binding trial')
        t.clean_panels()
        if afk(oracle)!=native['afk']:t.execute({'kind':'chat','value':'/afk'})
        if pose(oracle)['stand']!=native['pose']['stand']:
            if {pose(oracle)['stand'],native['pose']['stand']}!={0,1}:
                raise RuntimeError('unsupported original pose restoration')
            bar=bar_detail(t,'restore_pose_binding')
            t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':.4})
            time.sleep(12)
        after,frame=t.observe('native_bindings_restored')
        checks={'resources':resources(oracle)==native['resources'],'stats':restored_native_state(native['stats'],native_state(oracle)),
            'spells':known(t.fixture['guid'])==native['spells'],'actions':saved_actions(t.fixture['guid'])==native['actions'],
            'pose':pose(oracle)==native['pose'],'afk':afk(oracle)==native['afk'],
            'position':after['world_position']==before['world_position'] and position(t.fixture['guid'])==native['position'],
            'group':after['group']==before['group'],
            'no_lua_errors':not after.get('lua_errors'),'no_blocked_actions':not after.get('blocked_actions')}
        t.receipt['native_restoration']={'checks':checks,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('native binding fixture restoration differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
