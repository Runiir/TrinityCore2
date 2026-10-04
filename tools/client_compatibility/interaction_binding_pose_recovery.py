"""Restore the exact pose mismatch left by a closed owned binding trial."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial,binding_key
from .interaction_sit_stand import pose,afk
from .interaction_actionbar_pages import detail
from .interaction_ground_movement import position
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .observation.inventory import Inventory


def recover(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json' or source.parent.name!='primary_bindings01':
        raise ValueError('require the exact owned binding pose failure')
    old=json.loads(source.read_text());checks=old.get('native_restoration',{}).get('checks',{})
    if (not old.get('finished_at') or old.get('completed') or old['failure']!='RuntimeError: native binding fixture restoration differs' or
            [k for k,v in checks.items() if not v]!=['pose'] or not old.get('settings_restored') or
            not any(c.get('binding_restored') for c in old['cleanup']) or
            old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime']):
        raise RuntimeError('failure or owned fixture identity differs')
    base=old['native_baseline'];original_position=position(t.fixture['guid'])
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    state,frame=t.observe('source_pose_mismatch');bar=detail(t,'source_pose_binding')
    current=pose(oracle)
    if current!={'stand':0,'sheath':0} or base['pose']!={'stand':1,'sheath':0} or afk(oracle)!=base['afk']:
        raise RuntimeError('exact original sitting/AFK mismatch differs')
    if (resources(oracle)!=base['resources'] or not restored_native_state(base['stats'],native_state(oracle)) or
            known(t.fixture['guid'])!=base['spells'] or saved_actions(t.fixture['guid'])!=base['actions'] or
            any(state.get(k)!=v for k,v in old['binding_baseline'].items()) or state.get('panels')):
        raise RuntimeError('source resources, bindings or closed UI differ')
    action={'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':.4}
    t.receipt['source']={'file':str(source),'sha256':lab.sha256(source),'qualification':False}
    t.receipt['pose_recovery']={'before_frame':frame,'before_native':current,'input':action};t.persist()
    t.execute(action);time.sleep(12);after,frame=t.observe('restored')
    checks={'resources':resources(oracle)==base['resources'],'stats':restored_native_state(base['stats'],native_state(oracle)),
        'spells':known(t.fixture['guid'])==base['spells'],'actions':saved_actions(t.fixture['guid'])==base['actions'],
        'pose':pose(oracle)==base['pose'],'afk':afk(oracle)==base['afk'],
        'bindings':all(after.get(k)==v for k,v in old['binding_baseline'].items()),
        'position':position(t.fixture['guid'])==original_position,'closed_ui':not after.get('panels'),
        'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
    t.receipt['source_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('source binding pose restoration differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:recover(t,a.source);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
