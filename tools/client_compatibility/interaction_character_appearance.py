"""Toggle stock Show Helm/Show Cloak settings and verify native visibility flags."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,click_case,point
from .interaction_macros import edit_case,require
from .interaction_settings_search import open_search,resources
from .interaction_tooltips import baseline
from .interaction_equipment_set_roundtrip import stable
from .observation.inventory import Inventory
from .world.objects import INDEX

BITS={'helm':0x400,'cloak':0x800}


def flags(t,oracle):
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT characterFlags FROM client442_characters.characters WHERE guid=%s',(t.fixture['guid'],))
        row=q.fetchone()
    if row is None:raise RuntimeError('owned character flags are absent')
    return {'saved_character_flags':row[0],
        'native_player_flags':oracle.poll().objects.get(t.fixture['guid'],{}).get(INDEX['PLAYER_FLAGS'],0)}


def toggle(t,oracle,kind,shown,case_id):
    label='Show '+kind.title();bit=BITS[kind]
    def outcome(b,a,s):
        native=flags(t,oracle);rows=[c for c in controls(t) if c['kind']=='CheckButton' and c.get('context')==label]
        checks={'selected':s,'native_saved_visibility':bool(native['saved_character_flags']&bit)==(not shown),
            'native_runtime_visibility':bool(native['native_player_flags']&bit)==(not shown),
            'public_visibility':a.get('appearance',{}).get(kind)==shown,
            'stock_checkbox':len(rows)==1 and rows[0].get('checked')==shown,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'character_appearance_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native':native,'expected_shown':shown,'stock_controls':rows}}
    return click_case(t,case_id,'Set '+label+' to '+str(shown)+'.',
        lambda c:c['kind']=='CheckButton' and c.get('context')==label,outcome,
        await_state=lambda a:a.get('appearance',{}).get(kind)==shown)


def suite(t,scout_diagnostic=False):
    expected=2 if scout_diagnostic else 1
    if t.fixture['guid']!=expected:raise RuntimeError('appearance trial actor does not match its declared scope')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    if scout_diagnostic and (t.fixture['level']!=1 or oracle.equipment(1)['guid'] or oracle.equipment(15)['guid']):
        raise RuntimeError('scout diagnostic requires its unchanged level-one fixture without helm/cloak')
    snapshot=(lambda:resources(oracle)) if scout_diagnostic else baseline
    t.clean_panels();state,frame=t.observe('appearance_before')
    if state.get('observer_version',0)<54:raise RuntimeError('require committed read-only appearance observer v54')
    original=stable(snapshot());initial=flags(t,oracle);visibility=state['appearance'];search=None;active=None
    t.receipt.update(baseline=original,appearance_baseline={'state':visibility,'native':initial,'frame':frame},native_session=session,
        qualified_scope='scout request/flag diagnostic only; geared rendering unqualified' if scout_diagnostic else 'geared primary stock visibility toggles');t.persist()
    try:
        field=open_search(t);search=field['text'];predicate=lambda c:c['kind']=='EditBox' and point(c)==point(field)
        for kind in ['helm','cloak']:
            active=kind
            require(edit_case(t,'appearance.search.'+kind,'Find the stock '+kind+' setting.',predicate,kind),'ui_edit_pass')
            require(toggle(t,oracle,kind,not visibility[kind],'character.display_'+kind),'character_appearance_pass')
            require(toggle(t,oracle,kind,visibility[kind],'appearance.restore.'+kind),'character_appearance_pass')
            active=None
    finally:
        try:
            if active:
                buttons=[c for c in controls(t) if c['kind']=='CheckButton' and c.get('context')=='Show '+active.title()]
                if len(buttons)==1 and buttons[0].get('checked')!=visibility[active]:
                    require(toggle(t,oracle,active,visibility[active],'appearance.cleanup.'+active),'character_appearance_pass')
            if search is not None:
                require(edit_case(t,'appearance.search_restore','Restore the original settings search.',predicate,search),'ui_edit_pass')
                require(click_case(t,'appearance.close','Close stock settings.',lambda c:c['text']=='Close',
                    lambda b,a,s:{'status':'panel_closed_pass' if s and 'SettingsPanel' not in a['panels'] else 'client_or_protocol_failure'},
                    await_state=lambda a:'SettingsPanel' not in a['panels']),'panel_closed_pass')
            t.clean_panels();state,frame=t.observe('appearance_restored')
            t.receipt['appearance_restored']={'state':state['appearance'],'native':flags(t,oracle),'frame':frame}
        finally:
            t.receipt['native_after']=stable(snapshot());t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
    restored=t.receipt.get('appearance_restored',{})
    if not t.receipt['native_resources_preserved'] or restored.get('state')!=visibility or restored.get('native')!=initial:
        raise RuntimeError('original character visibility or native resources remain unrestored')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scout-diagnostic',action='store_true',help='Owned unarmored scout request/flag probe; does not qualify geared rendering')
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.scout_diagnostic);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
