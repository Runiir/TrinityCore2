"""Review and reversibly track stock achievements against native catalog/state."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .interaction_observation import read_current_page
from .interaction_archaeology_projects import dbc
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .observation.inventory import Inventory


def saved(guid):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT achievement,date FROM client442_characters.character_achievement WHERE guid=%s ORDER BY achievement',(guid,))
        earned=[list(r) for r in q.fetchall()]
        q.execute('SELECT criteria,counter,date FROM client442_characters.character_achievement_progress WHERE guid=%s ORDER BY criteria',(guid,))
        progress=[list(r) for r in q.fetchall()]
    return {'earned':earned,'progress':progress}


def detail(t,label,ready=None):
    state,frame=read_current_page(t,label,'achievements',lambda s:s.get('achievement_probe',{}).get('visible') and
        (ready is None or ready(s['achievement_probe'])))
    t.receipt.setdefault('achievement_details',{})[label]={'state':state,'frame':frame};t.persist()
    return state['achievement_probe']


def category(t,id,label):
    before=detail(t,label+'_before');matches=[r for r in before['categories'] if r['id']==id]
    if len(matches)!=1:raise RuntimeError('required stock category is not uniquely visible')
    def outcome(b,a,s):
        after=detail(t,label+'_selected',lambda p:p.get('category')==id)
        return {'status':'stock_achievement_category_pass' if s and after['category']==id and
            not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure',
            'oracle':{'category':id,'public':after}}
    require(click_case(t,label,'Select the observed stock achievement category.',
        lambda c:c['name']==matches[0]['button'],outcome),'stock_achievement_category_pass')


def tracking(t,id,wanted,label):
    probe=detail(t,label+'_before');row=next(r for r in probe['rows'] if r['id']==id)
    if not row.get('tracking_visible') or not row.get('tracking_button'):raise RuntimeError('stock tracking checkbox is not visible')
    def outcome(b,a,s):
        after=detail(t,label+'_changed',lambda p:(id in p['tracked'])==wanted)
        visible=next((r for r in after['rows'] if r['id']==id),{})
        checks={'ordinary_checkbox':s,'public_tracking':(id in after['tracked'])==wanted,
            'rendered_checkbox':bool(visible.get('tracking_checked'))==wanted,
            'native_achievements_preserved':saved(t.fixture['guid'])==t.achievement_baseline,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_achievement_tracking_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':after}}
    require(click_case(t,label,'Set the selected unearned achievement tracking checkbox.',
        lambda c:c['name']==row['tracking_button'],outcome),'stock_achievement_tracking_pass')


def suite(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();state,_=t.observe('achievement_fixture')
    if state.get('observer_version',0)<67:raise RuntimeError('requires passive achievement observer67')
    original=resources(oracle);spells=known(t.fixture['guid']);t.achievement_baseline=saved(t.fixture['guid'])
    rows,text=dbc('Achievement',14);catalog={r[0]:{'id':r[0],'name':text(r[4]),'category':r[6],'points':r[7]} for r in rows}
    t.receipt.update(baseline=original,native_persisted_spells=spells,native_achievements=t.achievement_baseline,
        catalog_sha256=lab.sha256(lab.ROOT/'data/dbc/enUS/Achievement.dbc'),
        qualified_scope='Stock General category, native-backed achievement row selection and reversible checkbox tracking. Search, comparison, criteria mutation, earned notification and persistence remain open.');t.persist()
    layout=None;selected=None
    try:
        require(click_case(t,'achievements.trial_open','Open stock achievements through the observed microbutton.',
            lambda c:c['name']=='AchievementMicroButton',
            lambda b,a,s:{'status':'achievement_open_pass' if s and 'AchievementFrame' in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda a:'AchievementFrame' in a['panels']),'achievement_open_pass')
        layout=detail(t,'achievement_layout');t.receipt['layout_baseline']=layout;t.persist()
        category(t,92,'achievements.category');probe=detail(t,'general_catalog',lambda p:bool(p['rows']))
        earned={r[0] for r in t.achievement_baseline['earned']};checks=[]
        for row in probe['rows']:
            expected=catalog.get(row['id'])
            checks.append(bool(expected and row['name']==expected['name'] and row['shown_name']==expected['name'] and
                row['points']==expected['points'] and row['completed']==(row['id'] in earned)))
        t.receipt['native_catalog_checks']=checks;t.persist()
        if not checks or not all(checks):raise RuntimeError('visible achievement rows disagree with native catalog/earned state')
        candidates=[r for r in probe['rows'] if not r['completed'] and r['id'] not in layout['tracked']]
        if not candidates:raise RuntimeError('requires an unearned untracked visible native achievement')
        selected=candidates[0];t.receipt['selected_contract']=catalog[selected['id']];t.persist()
        def select_outcome(b,a,s):
            after=detail(t,'achievement_selected',lambda p:p.get('selection')==selected['id'])
            return {'status':'stock_achievement_selection_pass' if s and any(r['id']==selected['id'] and
                r['selected'] for r in after['rows']) and not a.get('lua_errors') and not a.get('blocked_actions') else
                'client_or_protocol_failure','oracle':{'public':after,'native_contract':catalog[selected['id']]}}
        require(click_case(t,'achievements.achievement','Expand the observed native achievement row.',
            lambda c:c['name']==selected['button'],select_outcome),'stock_achievement_selection_pass')
        tracking(t,selected['id'],True,'achievements.track');tracking(t,selected['id'],False,'achievements.untrack')
    finally:
        try:
            if layout:
                current=detail(t,'achievement_restore_before')
                if selected and selected['id'] in current['tracked'] and selected['id'] not in layout['tracked']:
                    tracking(t,selected['id'],False,'achievements.cleanup_untrack')
                if current.get('category')!=layout.get('category'):category(t,layout['category'],'achievements.restore_category')
                after=detail(t,'achievement_restored');t.receipt['layout_restored']=all(after.get(k)==layout.get(k)
                    for k in ['tab','category','selection','tracked']);t.persist()
                if not t.receipt['layout_restored']:raise RuntimeError('achievement layout/tracking did not restore')
            t.clean_panels()
        finally:
            t.receipt.update(native_after=resources(oracle),native_achievements_after=saved(t.fixture['guid']),
                native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=(t.receipt['native_after']==original and
                t.receipt['native_achievements_after']==t.achievement_baseline and t.receipt['native_persisted_spells_after']==spells)
            t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('stock achievement trial changed native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
