"""Stock equipment-manager controls with read-only native persistence checks."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,click_case,command
from .interaction_macros import require,edit_case
from .interaction_observation import read_page
from .interaction_tooltips import baseline

NAME='HarnessUI36'


def sets():
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT * FROM client442_characters.character_equipmentsets WHERE guid=1 ORDER BY setindex,setguid')
        return {'columns':[r[0] for r in q.description],'rows':q.fetchall()}


def detail(t,label):
    try:
        state,frame=read_page(t,label,'equipment','/tcui equipment')
        t.receipt.setdefault('equipment_details',{})[label]={'state':state,'frame':frame};t.persist()
        return state['equipment_probe']
    finally:command(t,'/tcui state')


def suite(t,phase):
    actors.session_entry(t.fixture);t.clean_panels();original=baseline();saved=sets()
    if saved['rows']:raise RuntimeError('requires an owned primary actor with no equipment sets')
    t.receipt['baseline']={'native':original,'sets':saved};t.persist()
    try:
        require(t.step('character.set_open','Open character equipment.',
            {'open':{'kind':'key','value':'c','description':'Press C for character equipment.'}},
            lambda b,a,s:{'status':'character_open_pass' if 'CharacterFrame' in a['panels'] else
                'client_or_protocol_failure'},diagnostic_action='open'),'character_open_pass')
        require(click_case(t,'character.set_manager','Open the stock equipment manager.',
            lambda c:c['name']=='PaperDollSidebarTab3',
            lambda b,a,s:{'status':'equipment_manager_pass' if s and detail(t,'manager_open')['manager_visible'] else
                'client_or_protocol_failure'}),'equipment_manager_pass')
        t.receipt['manager_controls']=controls(t);t.persist()
        require(click_case(t,'character.set_new','Open the new equipment-set dialog.',
            lambda c:c['text']=='New Set',
            lambda b,a,s:{'status':'equipment_set_dialog_pass' if s and 'GearManagerPopupFrame' in a['panels'] else
                'client_or_protocol_failure'}),'equipment_set_dialog_pass')
        t.receipt['popup_controls']=controls(t);t.receipt['popup_probe']=detail(t,'new_set_popup');t.persist()
        if phase=='create':
            require(edit_case(t,'character.set_name','Name the disposable equipment set.',
                lambda c:c['kind']=='EditBox',NAME),'ui_edit_pass')
            def outcome(b,a,s):
                now=sets();probe=detail(t,'created_set');rows=now['rows'];col=now['columns']
                named=[dict(zip(col,r)) for r in rows if r[col.index('name')]==NAME]
                expected={r[2]:r[3] for r in original['archaeology_inventory_money']['inventory']['items']
                    if r[0]==1 and r[1]==0 and r[2]<19}
                checks={'selected':s,'native_one_set':len(rows)==len(named)==1,
                    'public_one_set':probe['count']==1 and len(probe['sets'])==1 and probe['sets'][0]['name']==NAME,
                    'native_slots':len(named)==1 and all(named[0]['item'+str(i)]==expected.get(i,0) for i in range(19)),
                    'native_resources_preserved':baseline()==original,
                    'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
                return {'status':'equipment_set_create_pass' if all(checks.values()) else 'client_or_protocol_failure',
                    'oracle':{'checks':checks,'native':now,'public':probe}}
            require(click_case(t,'character.equipment_set_create','Save the new equipment set.',
                lambda c:c['text']=='Okay',outcome),'equipment_set_create_pass')
    finally:
        t.clean_panels();t.receipt['native_after']={'native':baseline(),'sets':sets()}
        t.receipt['native_resources_preserved']=t.receipt['native_after']['native']==original;t.persist()
        if not t.receipt['native_resources_preserved']:raise RuntimeError('equipment manager changed native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase',choices=['inspect','create'],default='inspect');a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.phase);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
