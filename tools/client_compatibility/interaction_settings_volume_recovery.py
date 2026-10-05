"""Close the exact failed volume panel after source-bound state verification."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,click_control,layout_checks
from .interaction_settings_booleans import detail
from .interaction_control_target import target
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .interaction_ground_movement import position
from .observation.inventory import Inventory


def recover(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a private closed Master Volume failure')
    old=json.loads(path.read_text())
    expected={'settings.sound_volume.decrease':'stock_numeric_setting_pass',
        'settings.sound_volume.restore.1':'stock_numeric_setting_pass','fixture.restore_volume_search':'ui_edit_pass'}
    passed={c['id']:c['status'] for c in old.get('cases',[])}
    if (old.get('completed') or not old.get('finished_at') or old.get('failure')!=
        'RuntimeError: panel cleanup did not change state; refusing to replay Escape' or
        old.get('actor')!=t.fixture or old.get('runtime')!=t.receipt['runtime'] or
        not old.get('volume_exercise_attempted') or any(passed.get(k)!=v for k,v in expected.items()) or
        old.get('volume_layout_restoration',{}).get('checks')!=
            {'search':True,'category':True,'cvars':False,'values':True,'unapplied':True}):
        raise RuntimeError('exact closed volume failure or owned runtime differs')
    layout=old['volume_layout_baseline'];base=old['native_baseline'];before=old['cases'][0]['before']
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},qualified_scope=
        'Source-bound cleanup only. Verify the original numeric volume, settings layout and native fixture, then close the existing stock panel. No gameplay qualification.');t.persist()
    def native_checks(state):
        return {'resources':resources(oracle)==base['resources'],
            'stats':restored_native_state(base['stats'],native_state(oracle)),
            'spells':known(t.fixture['guid'])==base['spells'],'actions':saved_actions(t.fixture['guid'])==base['actions'],
            'pose':pose(oracle)==base['pose'],'afk':afk(oracle)==base['afk'],
            'position':position(t.fixture['guid'])==base['position'] and state['world_position']==before['world_position'],
            'group':state['group']==before['group'],'no_lua_errors':not state.get('lua_errors'),
            'no_blocked_actions':not state.get('blocked_actions')}
    state,frame=t.observe('source_volume_panel');checks=native_checks(state)
    current=detail(t,'source_volume_settings');settings=layout_checks(current,layout)
    t.receipt['source_preflight']={'native':checks,'settings':settings,'frame':frame};t.persist()
    if not all(checks.values()) or not all(settings.values()) or not current['visible'] or current.get('unapplied'):
        raise RuntimeError('source native fixture or restored stock settings differ')
    close=target(t,'source_volume_close',lambda c:c['kind']=='Button' and c['text']=='Close')
    click_control(t,'fixture.close_failed_volume',close,lambda a:'SettingsPanel' not in a['panels'],'settings_panel_closed')
    t.clean_panels();state,frame=t.observe('source_volume_restored');checks=native_checks(state)
    checks['closed_ui']=not state.get('panels')
    t.receipt['source_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('source volume fixture restoration differs')


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
