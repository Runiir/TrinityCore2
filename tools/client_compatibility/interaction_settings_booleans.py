"""Toggle stock boolean settings through observed checkboxes and restore them."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_settings_search import open_search
from .interaction_operations import controls,point,click_case
from .interaction_macros import edit_case,require
from .interaction_observation import read_current_page
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .observation.inventory import Inventory

SPECS={
    'autoLootDefault':('Auto Loot','settings.auto_loot'),
    'lockActionBars':('Lock Action Bars','actionbars.lock_toggle'),
    'Sound_EnableAllSound':('Enable Sound','settings.mute'),
    'cameraTerrainTilt':('Follow Terrain','settings.camera'),
    'showTutorials':('Tutorials','settings.tutorials'),
    'nameplateShowEnemies':('Enemy Units','settings.nameplates'),
    'enableFloatingCombatText':('Floating Combat Text','settings.floating_combat_text'),
}


def detail(t,label,ready=None):
    state,frame=read_current_page(t,label,'settings',lambda s:s.get('settings_probe') and
        (ready is None or ready(s['settings_probe'])))
    t.receipt.setdefault('settings_details',{})[label]={'state':state,'frame':frame};t.persist()
    return state['settings_probe']


def search(t,term,label):
    field=t.settings_search
    require(edit_case(t,label,'Find the stock setting through ordinary search-field input.',
        lambda c:c['kind']=='EditBox' and point(c)==point(field),term),'ui_edit_pass')


def toggle(t,variable,wanted,label):
    rows=[c for c in controls(t) if c['kind']=='CheckButton' and c.get('setting_variable')==variable and c['enabled']]
    if len(rows)!=1:raise RuntimeError('one observed enabled checkbox is required for '+variable)
    control=rows[0]
    def outcome(b,a,s):
        probe=detail(t,label+'_value',lambda p:p['cvars'].get(variable)==wanted and
            p['values'].get(variable)==(wanted=='1'))
        checks={'ordinary_checkbox':bool(s),'observed_variable':control['setting_variable']==variable,
            'public_cvar':probe['cvars'].get(variable)==wanted,
            'public_setting':probe['values'].get(variable)==(wanted=='1'),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_boolean_setting_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'variable':variable,'expected':wanted,'public':probe}}
    require(click_case(t,label,'Toggle the observed stock setting checkbox.',
        lambda c:c['kind']=='CheckButton' and c.get('setting_variable')==variable and point(c)==point(control),
        outcome),'stock_boolean_setting_pass')


def suite(t,variables):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();state,_=t.observe('settings_fixture')
    if state.get('observer_version',0)<70:raise RuntimeError('requires read-only settings observer70')
    native=resources(oracle);spells=known(t.fixture['guid']);layout=None;original={};attempted=[]
    t.receipt.update(baseline=native,native_persisted_spells=spells,requested_settings=variables,
        qualified_scope='Requested stock boolean settings changed once through their observed search-result checkbox and reversed. Public Settings values, CVars, original search/category, native resources and saved spells restore. Other settings, defaults, Apply/Cancel and reconnect persistence remain open.');t.persist()
    try:
        t.settings_search=open_search(t);layout=detail(t,'settings_layout');t.receipt['layout_baseline']=layout;t.persist()
        for variable in variables:
            original[variable]=layout['cvars'].get(variable)
            if original[variable] not in ['0','1']:raise RuntimeError('requires an installed boolean CVar: '+variable)
        for variable in variables:
            term,operation=SPECS[variable];search(t,term,operation+'.search')
            attempted.append(variable);toggle(t,variable,'0' if original[variable]=='1' else '1',operation+'.change')
            toggle(t,variable,original[variable],operation+'.restore')
    finally:
        try:
            if layout is not None:
                current=detail(t,'settings_restore_before')
                for variable in attempted:
                    if current['cvars'].get(variable)==original[variable]:continue
                    term,operation=SPECS[variable];search(t,term,operation+'.cleanup_search')
                    toggle(t,variable,original[variable],operation+'.cleanup_restore')
                    current=detail(t,'settings_cleanup_'+variable)
                search(t,layout.get('search') or '','settings.restore_search')
                after=detail(t,'settings_restored');t.receipt['layout_restored']=all(after.get(k)==layout.get(k)
                    for k in ['search','category','cvars','values']);t.persist()
                if not t.receipt['layout_restored']:raise RuntimeError('original settings search/category/values did not restore')
                require(click_case(t,'settings.trial_close','Close the stock settings panel.',
                    lambda c:c['kind']=='Button' and c['text']=='Close',
                    lambda b,a,s:{'status':'stock_settings_close_pass' if s and 'SettingsPanel' not in a['panels'] else
                        'client_or_protocol_failure'},await_state=lambda s:'SettingsPanel' not in s['panels']),
                    'stock_settings_close_pass')
            t.clean_panels()
        finally:
            t.receipt.update(native_after=resources(oracle),native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=(t.receipt['native_after']==native and t.receipt['native_persisted_spells_after']==spells);t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('settings trial changed native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--setting',choices=list(SPECS),action='append',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if len(set(a.setting))!=len(a.setting):p.error('each setting may be requested once')
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t,a.setting);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
