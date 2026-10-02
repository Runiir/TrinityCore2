"""Search, select and craft a known recipe with native reagent/product accounting."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,controls,point
from .interaction_macros import require,edit_case
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.buffer import Reader
from .world.native_objects import guid as native_guid
from .interaction_fixture_permissions import item_fixture_permission

NAME='Potion of Deepholm';SPELL=80725;PRODUCT=58487;REAGENTS={52986:5,3371:1}


def counts(oracle):
    oracle.poll();return {str(i):oracle.count(i) for i in [PRODUCT,*REAGENTS]}


def fixture_command(trial,text,reason):
    trial.receipt.setdefault('fixture_inputs',[]).append({'time':time.time(),'source':'code_fixture','input':text,'reason':reason});trial.persist()
    trial.execute({'kind':'chat','value':text})


def completions(trial,session,since):
    result=[]
    for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if row.get('session')!=session or row.get('time',0)<since or row.get('direction')!='from_native' or row['name']!='SMSG_SPELL_GO':continue
        r=Reader(bytes.fromhex(row['body']));caster=native_guid(r);native_guid(r);counter,spell=r.unpack('Bi')
        if caster==trial.fixture['guid'] and spell==SPELL:result.append({'time':row['time'],'caster':caster,'spell':spell,'counter':counter})
    return result


def learned_recipe(session):
    known=None
    for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if row.get('session')!=session or row.get('direction')!='from_native' or row['name']!='SMSG_SEND_KNOWN_SPELLS':continue
        r=Reader(bytes.fromhex(row['body']));initial,n=r.unpack('BH')
        if initial>1 or n>16000:raise RuntimeError('invalid native learned-spell fixture')
        spells=[r.unpack('Ih')[0] for _ in range(n)];cooldowns,=r.unpack('H');r.raw(cooldowns*18);r.end()
        known={'learned':SPELL in spells,'native_spell_count':n,'source_time':row['time']}
    return known


def craft(trial,oracle,session,quantity,label):
    baseline=counts(oracle);since=time.time()
    expected={str(i):n for i,n in [(PRODUCT,baseline[str(PRODUCT)]+quantity),*[(i,baseline[str(i)]-n*quantity) for i,n in REAGENTS.items()]]}
    def outcome(b,a,selected):
        deadline=time.monotonic()+quantity*4+8
        actual=counts(oracle)
        while actual!=expected and time.monotonic()<deadline and selected:
            time.sleep(.2);actual=counts(oracle)
        state,frame=trial.observe('craft_'+label+'_settled')
        visible=state.get('crafting_probe',{}).get('counts',{})
        matches=all(visible.get(k)==v for k,v in expected.items())
        casts=completions(trial,session,since)
        passed=actual==expected and matches and len(casts)==quantity
        return {'status':'craft_result_pass' if passed else ('controller_failure' if not selected else 'client_or_protocol_failure'),
            'oracle':{'before':baseline,'expected':expected,'native':actual,'visible':visible,'native_cast_completions':casts,'settled_frame':frame,'lua_errors':state.get('lua_errors')}}
    return click_case(trial,'professions.'+label,'Create '+str(quantity)+' '+NAME+('.' if quantity==1 else ' potions.'),
        lambda c:c['name']=='TradeSkillCreateButton',outcome)


def suite(trial):
    session=actors.session_entry(trial.fixture)['session'];oracle=Inventory(lab.ROOT,session,trial.fixture['guid']).poll()
    trial.clean_panels();state,_=trial.observe('fixture');baseline=counts(oracle)
    known=learned_recipe(session);trial.receipt['native_recipe_fixture']=known;trial.persist()
    if not known or not known['learned']:raise RuntimeError('known native Deepholm recipe required')
    if any(baseline.values()):raise RuntimeError('disposable crafting fixture requires zero reagent/product baseline')
    trial.receipt['crafting_baseline']=baseline;trial.persist()
    try:
        fixture_command(trial,'/cleartarget','GM fixture commands must target the owned actor')
        for item,need in REAGENTS.items():fixture_command(trial,f'.additem {item} {need*3}','reagents for one craft and a two-craft batch')
        state,frame=trial.observe('reagents_prepared');native=counts(oracle)
        trial.receipt['reagent_fixture']={'native':native,'visible':state.get('crafting_probe'),'frame':frame};trial.persist()
        if any(native[str(i)]!=need*3 or state.get('crafting_probe',{}).get('counts',{}).get(str(i))!=need*3 for i,need in REAGENTS.items()):raise RuntimeError('native and visible reagent fixture disagree')
        require(trial.step('professions.open','Open professions and skills.',{
            'skills':{'kind':'key','value':'k','description':'Press K to open professions and skills.'},
            'map':{'kind':'key','value':'m','description':'Open the map.'},
            'character':{'kind':'key','value':'c','description':'Open equipment.'}},
            lambda b,a,s:{'status':'panel_open_pass' if 'SpellBookFrame' in a['panels'] else 'controller_failure'},diagnostic_action='skills'),'panel_open_pass')
        require(click_case(trial,'professions.alchemy','Open Alchemy recipes.',lambda c:c['text']=='Alchemy',
            lambda b,a,s:{'status':'recipe_list_pass' if a.get('trade_skill',[None])[0]=='Alchemy' and a.get('recipe_count',0)>0 else ('controller_failure' if not s else 'client_or_protocol_failure')}),'recipe_list_pass')
        require(edit_case(trial,'professions.recipe_search','Type '+NAME+' into the visible recipe search text field.',lambda c:c['name']=='TradeSkillFrameEditBox',NAME),'ui_edit_pass')
        require(click_case(trial,'professions.recipe_select','Select the '+NAME+' recipe.',lambda c:c['name'].startswith('TradeSkillSkill') and c['text'].strip()==NAME,
            lambda b,a,s:{'status':'recipe_select_pass' if a.get('selected_recipe',{}).get('name')==NAME and ':80725|' in a['selected_recipe'].get('recipe_link','') and 'item:58487:' in a['selected_recipe'].get('link','') else ('controller_failure' if not s else 'client_or_protocol_failure')}),'recipe_select_pass')
        require(craft(trial,oracle,session,1,'craft_one'),'craft_result_pass')
        require(edit_case(trial,'professions.craft_quantity','Set the craft quantity to two.',lambda c:c['name']=='TradeSkillInputBox','2'),'ui_edit_pass')
        require(craft(trial,oracle,session,2,'craft_multiple'),'craft_result_pass')
    finally:
        trial.clean_panels();fixture_command(trial,'/cleartarget','restore only the owned crafting fixture')
        for item in [PRODUCT,*REAGENTS]:
            excess=counts(oracle)[str(item)]-baseline[str(item)]
            if excess<0:raise RuntimeError('crafting consumed pre-existing inventory')
            if excess:fixture_command(trial,f'.additem {item} {-excess}','remove only the disposable crafting fixture')
        state,_=trial.observe('crafting_restored')
        if counts(oracle)!=baseline or any(state.get('crafting_probe',{}).get('counts',{}).get(k)!=v for k,v in baseline.items()):raise RuntimeError('crafting baseline restoration failed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();trial=Trial(a.output)
    try:
        with item_fixture_permission(trial):suite(trial)
        trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:trial.receipt['finished_at']=time.time();trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
