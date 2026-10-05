"""Recover the exact closed Interact proxy restoration failure with ordinary inputs."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,restore_layout
from .interaction_settings_controls import interact_fixture_restorable,restore_interact_fixture
from .interaction_settings_booleans import detail
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .interaction_ground_movement import position
from .observation.inventory import Inventory


def source_layout(old,fixture,runtime):
    expected={k:'stock_control_setting_pass' for k in ('settings.interface.change','settings.interface.restore',
        'settings.keyboard_controls.change','settings.keyboard_controls.restore')}
    passed={c['id']:c['status'] for c in old.get('cases',[])}
    layout=old.get('control_layout_baseline',{})
    last=old.get('settings_details',{}).get('fixture.restore_stock_controls_restored',{}).get('state',{}).get('settings_probe',{})
    if (old.get('completed') or not old.get('finished_at') or old.get('failure')!=
        'RuntimeError: panel cleanup did not change state; refusing to replay Escape' or
        old.get('actor')!=fixture or old.get('runtime')!=runtime or old.get('code_commit')!=
        '5806289004811953b1c0fe829a03c06237c5cd1c' or
        any(passed.get(k)!=v for k,v in expected.items()) or
        old.get('volume_layout_restoration',{}).get('checks')!=
        {'search':True,'category':True,'values':True,'unapplied':True,'cvars':False} or
        not interact_fixture_restorable(last,layout)):
        raise RuntimeError('exact closed Interact proxy failure or owned runtime differs')
    return layout


def recover(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a private closed Interact proxy failure')
    old=json.loads(path.read_text());layout=source_layout(old,t.fixture,t.receipt['runtime'])
    base=old['native_baseline'];before=old['cases'][0]['before']
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},qualified_scope=
        'Source-bound cleanup only. Verify the exact stock proxy 0-to-1 difference and native fixture, restore None=0 through ordinary console input, then verify and close the stock Settings panel. No gameplay qualification.');t.persist()
    def native_checks(state):
        return {'resources':resources(oracle)==base['resources'],
            'stats':restored_native_state(base['stats'],native_state(oracle)),
            'spells':known(t.fixture['guid'])==base['spells'],'actions':saved_actions(t.fixture['guid'])==base['actions'],
            'pose':pose(oracle)==base['pose'],'afk':afk(oracle)==base['afk'],
            'position':position(t.fixture['guid'])==base['position'] and state['world_position']==before['world_position'],
            'group':state['group']==before['group'],'no_lua_errors':not state.get('lua_errors'),
            'no_blocked_actions':not state.get('blocked_actions')}
    state,frame=t.observe('source_control_panel');checks=native_checks(state)
    current=detail(t,'source_control_settings')
    settings=interact_fixture_restorable(current,layout) and all(current.get(k)==layout.get(k) for k in ('search','category'))
    t.receipt['source_preflight']={'native':checks,'exact_proxy_difference':settings,'frame':frame};t.persist()
    if not all(checks.values()) or not settings or not current.get('visible') or current.get('unapplied'):
        raise RuntimeError('source native fixture or exact stock proxy difference no longer matches')
    restore_interact_fixture(t,layout,current,'fixture.recover_interact_none')
    restore_layout(t,layout,'fixture.recover_control_layout')
    if afk(oracle)!=base['afk']:t.execute({'kind':'chat','value':'/afk'})
    state,frame=t.observe('source_controls_restored');checks=native_checks(state)
    checks['closed_ui']=not state.get('panels')
    t.receipt['source_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('source control fixture restoration differs')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:recover(t,a.source);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
