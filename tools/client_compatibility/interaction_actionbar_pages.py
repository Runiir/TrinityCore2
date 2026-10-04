"""Cycle and directly select stock action-bar pages, then restore their baseline."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial,binding_key
from .interaction_social import actor
from .interaction_observation import read_current_page
from .interaction_macros import require
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .observation.inventory import Inventory


def detail(t,label,ready=None):
    state,frame=read_current_page(t,label,'actionbars',lambda s:s.get('actionbar_probe') and
        (ready is None or ready(s['actionbar_probe'])))
    t.receipt.setdefault('bar_details',{})[label]={'state':state,'frame':frame};t.persist()
    return state['actionbar_probe']


def select(t,key,page,label):
    def outcome(b,a,s):
        probe=detail(t,label+'_page',lambda p:p.get('page')==page)
        spec=probe['active_spec']-1
        native={r[1]:(r[2],r[3]) for r in t.actions_baseline if r[0]==spec}
        expected_page=t.bar_layout['effective_page'] if page==t.bar_layout['page'] else page
        matches=[]
        for index,button in enumerate(probe['actions'],1):
            entry=native.get(button['slot']-1)
            matches.append(button['slot']==index+(expected_page-1)*12 and
                ((not button.get('kind') and entry is None) or
                 (entry is not None and button.get('id')==entry[0] and
                  {'spell':0,'item':128,'macro':64}.get(button.get('kind'))==entry[1])))
        checks={'ordinary_binding':s=='binding','requested_page':probe['page']==page,
            'visible_main_bar':probe['frames'].get('MainMenuBar') is True,
            'requested_effective_page':probe['effective_page']==expected_page,
            'twelve_native_slot_assignments':len(matches)==12 and all(matches),
            'native_action_rows_unchanged':saved_actions(t.fixture['guid'])==t.actions_baseline,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_actionbar_page_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':probe}}
    require(t.step(label,'Select the requested stock action-bar page through the observed binding.',
        {'binding':{'kind':'key','value':key,'description':'Press the observed stock page binding '+key+'.'}},
        outcome,diagnostic_action='binding'),'stock_actionbar_page_pass')


def suite(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();state,_=t.observe('bar_fixture')
    if state.get('observer_version',0)<69:raise RuntimeError('requires passive action-bar observer69')
    original=resources(oracle);spells=known(t.fixture['guid']);t.actions_baseline=saved_actions(t.fixture['guid'])
    layout=detail(t,'bar_layout');page=layout['page']
    if not isinstance(page,int) or not 1<=page<=6:raise RuntimeError('requires an ordinary numbered action-bar page')
    viewable=layout['viewable_pages'];next_page=next((p for p in viewable if p>page),1)
    if next_page==page:raise RuntimeError('requires two viewable numbered pages')
    names=['NEXTACTIONPAGE','PREVIOUSACTIONPAGE','ACTIONPAGE'+str(page),'ACTIONPAGE'+str(next_page)]
    if any(not layout['keys'].get(name) for name in names):raise RuntimeError('required installed page binding is absent')
    keys={name:binding_key(layout['keys'][name][0]) for name in names}
    t.bar_layout=layout
    t.receipt.update(baseline=original,native_persisted_spells=spells,native_actions=t.actions_baseline,
        layout_baseline=layout,qualified_scope='Stock next/previous and direct numbered page bindings on one idle owned fixture. Native saved action rows/resources stay unchanged; the original page and visible slot assignment are restored. Other bar types and settings remain open.');t.persist()
    try:
        select(t,keys['NEXTACTIONPAGE'],next_page,'actionbars.page_next')
        select(t,keys['PREVIOUSACTIONPAGE'],page,'actionbars.page_previous')
        select(t,keys['ACTIONPAGE'+str(next_page)],next_page,'actionbars.direct_page')
        select(t,keys['ACTIONPAGE'+str(page)],page,'actionbars.restore_page')
    finally:
        try:
            current=detail(t,'bar_restore_before')
            if current['page']!=page:select(t,keys['ACTIONPAGE'+str(page)],page,'actionbars.cleanup_page')
            after=detail(t,'bar_restored');t.receipt['layout_restored']=(after['page']==page and
                [(r['button'],r['slot'],r.get('kind'),r.get('id')) for r in after['actions']]==
                [(r['button'],r['slot'],r.get('kind'),r.get('id')) for r in layout['actions']]);t.persist()
            if not t.receipt['layout_restored']:raise RuntimeError('original page/visible action assignments did not restore')
            t.clean_panels()
        finally:
            t.receipt.update(native_after=resources(oracle),native_actions_after=saved_actions(t.fixture['guid']),
                native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=(t.receipt['native_after']==original and
                t.receipt['native_actions_after']==t.actions_baseline and t.receipt['native_persisted_spells_after']==spells);t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('action-bar pages changed native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
