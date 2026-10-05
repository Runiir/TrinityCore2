"""Cancel the exact blocked fixture-script prompt and preserve script permission."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,click_control
from .interaction_control_target import target
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .interaction_ground_movement import position
from .observation.inventory import Inventory


def cancel(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a private closed script-prompt cleanup failure')
    old=json.loads(path.read_text());source=Path(old.get('source',{}).get('path',''))
    if (old.get('completed') or not old.get('finished_at') or old.get('failure')!=
        'RuntimeError: panel cleanup did not settle' or old.get('actor')!=t.fixture or
        old.get('runtime')!=t.receipt['runtime'] or
        old.get('unrestored_cvars')!={'softTargetInteract':{'original':'0','after':'1'}} or
        len(old.get('source_preflight',{}).get('native',{}))!=10 or
        not all(old['source_preflight']['native'].values()) or
        not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json' or
        lab.sha256(source)!=old['source']['sha256']):
        raise RuntimeError('exact closed script-prompt source or owned runtime differs')
    original=json.loads(source.read_text());base=original['native_baseline'];before=original['cases'][0]['before']
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},
        original_source=old['source'],unrestored_cvars=old['unrestored_cvars'],qualified_scope=
        'Cleanup only. Decline the visible custom-script warning, close the menu, and preserve the original native fixture. Script permission stays blocked; original softTargetInteract=0 remains unrestored at stock-disabled1. No gameplay qualification.');t.persist()
    def checks(state):
        return {'resources':resources(oracle)==base['resources'],
            'stats':restored_native_state(base['stats'],native_state(oracle)),
            'spells':known(t.fixture['guid'])==base['spells'],'actions':saved_actions(t.fixture['guid'])==base['actions'],
            'pose':pose(oracle)==base['pose'],'afk':afk(oracle)==base['afk'],
            'position':position(t.fixture['guid'])==base['position'] and state['world_position']==before['world_position'],
            'group':state['group']==before['group'],'no_lua_errors':not state.get('lua_errors'),
            'no_blocked_actions':not state.get('blocked_actions')}
    state,frame=t.observe('blocked_script_fixture');pre=checks(state)
    t.receipt['source_preflight']={'checks':pre,'frame':frame};t.persist()
    if not all(pre.values()) or 'StaticPopup1' not in state.get('panels',[]):
        raise RuntimeError('blocked-script native fixture or visible popup differs')
    button=target(t,'custom_script_no',lambda c:c['kind']=='Button' and
        c.get('name')=='StaticPopup1Button2' and c.get('text')=='No' and c.get('enabled') and
        'custom script' in c.get('context','').lower())
    click_control(t,'fixture.decline_custom_script',button,
        lambda a:'StaticPopup1' not in a.get('panels',[]),'script_prompt_declined')
    t.clean_panels()
    if afk(oracle)!=base['afk']:t.execute({'kind':'chat','value':'/afk'})
    state,frame=t.observe('script_prompt_cancelled');post=checks(state);post['closed_ui']=not state.get('panels')
    t.receipt['source_restoration']={'checks':post,'frame':frame};t.persist()
    if not all(post.values()):raise RuntimeError('native fixture after script rejection differs')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:cancel(t,a.source);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
