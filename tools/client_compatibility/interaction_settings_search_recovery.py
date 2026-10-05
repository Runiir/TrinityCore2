"""Restore the saved baseline of the closed voice-binding search cleanup failure."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_settings_booleans import detail
from .interaction_operations import click_case,point
from .interaction_macros import edit_case,require
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .interaction_ground_movement import position
from .observation.inventory import Inventory


def source(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a private closed search failure')
    old=json.loads(path.read_text())
    expected={'fixture.voice_binding_search_voice','fixture.voice_binding_search_mute'}
    passed={c['id'] for c in old.get('cases',[]) if c['status']=='ui_edit_pass'}
    if (old.get('completed') or not old.get('finished_at') or old.get('failure')!=
        'RuntimeError: panel cleanup did not change state; refusing to replay Escape' or
        old.get('actor')!=t.fixture or old.get('runtime')!=t.receipt['runtime'] or
        not expected.issubset(passed) or old.get('binding_baseline')):
        raise RuntimeError('closed search failure or owned runtime differs')
    layout=old['settings_details']['original_settings']['state']['settings_probe']
    if layout.get('unapplied'):raise RuntimeError('original search settings had unapplied changes')
    return old,layout


def recover(t,path):
    old,layout=source(t,path);base=old['native_baseline']
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    t.receipt['source']={'path':str(path.resolve()),'sha256':lab.sha256(path),'qualification':False};t.persist()
    checks={'resources':resources(oracle)==base['resources'],
        'stats':restored_native_state(base['stats'],native_state(oracle)),
        'spells':known(t.fixture['guid'])==base['spells'],'actions':saved_actions(t.fixture['guid'])==base['actions'],
        'pose':pose(oracle)==base['pose'],'position':position(t.fixture['guid'])==base['position']}
    current=detail(t,'source_settings_before')
    checks['settings_values']=all(current.get(k)==layout.get(k) for k in ['cvars','values','unapplied'])
    t.receipt['source_preflight']=checks;t.persist()
    if not all(checks.values()) or not current['visible'] or current['category']['name']!='Keybindings':
        raise RuntimeError('source resources or current search panel differs')
    require(click_case(t,'fixture.search_recover_category','Restore the saved settings category.',
        lambda c:c['text']==layout['category']['name'][:64],
        lambda b,a,s:{'status':'settings_category_restored' if s and
            detail(t,'source_category')['category']==layout['category'] else 'client_or_protocol_failure'}),
        'settings_category_restored')
    require(edit_case(t,'fixture.search_recover_text','Restore the saved settings search.',
        lambda c:c['kind']=='EditBox',layout['search']),'ui_edit_pass')
    after=detail(t,'source_settings_restored')
    restored=all(after.get(k)==layout.get(k) for k in ['category','search','cvars','values','unapplied'])
    t.receipt['settings_restored']=restored;t.persist()
    if not restored:raise RuntimeError('saved settings were not restored')
    require(click_case(t,'fixture.search_recover_close','Close the observed stock settings panel.',
        lambda c:c['text']=='Close',lambda b,a,s:{'status':'panel_closed_pass' if s and
            'SettingsPanel' not in a['panels'] else 'client_or_protocol_failure'}),'panel_closed_pass')
    t.clean_panels()
    if afk(oracle)!=base['afk']:t.execute({'kind':'chat','value':'/afk'})
    state,frame=t.observe('source_search_restored')
    checks.update(pose=pose(oracle)==base['pose'],afk=afk(oracle)==base['afk'],
        resources=resources(oracle)==base['resources'],stats=restored_native_state(base['stats'],native_state(oracle)),
        spells=known(t.fixture['guid'])==base['spells'],actions=saved_actions(t.fixture['guid'])==base['actions'],
        position=position(t.fixture['guid'])==base['position'],settings=restored,
        closed_ui=not state.get('panels'),no_lua_errors=not state.get('lua_errors'),
        no_blocked_actions=not state.get('blocked_actions'))
    t.receipt['source_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('source search recovery differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:recover(t,a.source);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure']}),flush=True)
