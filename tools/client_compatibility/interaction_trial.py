"""Bounded Laya choices executed through owned physical client inputs.

This is candidate selection, not open-ended planning or screenshot vision.
Oracles and cleanup never enter the model request.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import subprocess
import time
import urllib.request
from contextlib import redirect_stdout
from io import StringIO
from . import actors,lab_runtime as lab,owned_input
from .archaeology_controller import MODEL,REVISION,ENDPOINT
from .observation.interactions import decode_image
from .observation.telemetry import decode_image as decode_movement

# Installed binding names are resolved at run time, not guessed shortcuts.
PANELS=[
 ('bags.backpack','Open the backpack.','TOGGLEBACKPACK',['bags']),
 ('bags.bag_one','Open equipped bag one.','TOGGLEBAG1',['bags']),
 ('bags.bag_two','Open equipped bag two.','TOGGLEBAG2',['bags']),
 ('bags.bag_three','Open equipped bag three.','TOGGLEBAG3',['bags']),
 ('bags.bag_four','Open equipped bag four.','TOGGLEBAG4',['bags']),
 ('bags.open_all','Open all equipped bags.','OPENALLBAGS',['bags']),
 ('character.open','Open the character equipment window.','TOGGLECHARACTER0',['CharacterFrame']),
 ('reputation.open','Open the reputation window.','TOGGLECHARACTER2',['ReputationFrame']),
 ('professions.open','Open the professions and skills window.','TOGGLECHARACTER1',['SpellBookFrame','SkillFrame']),
 ('spellbook.open','Open the spellbook.','TOGGLESPELLBOOK',['SpellBookFrame']),
 ('talents.open','Open the talents window.','TOGGLETALENTS',['PlayerTalentFrame']),
 ('quests.open_log','Open the quest log.','TOGGLEQUESTLOG',['QuestLogFrame','WorldMapFrame']),
 ('map.open','Open the world map.','TOGGLEWORLDMAP',['WorldMapFrame']),
 ('collections.open','Open the mount and companion collections.','TOGGLECOLLECTIONS',['CollectionsJournal','PetJournalParent']),
 ('journal.open','Open the dungeon encounter journal.','TOGGLEENCOUNTERJOURNAL',['EncounterJournal']),
 ('achievements.open','Open achievements.','TOGGLEACHIEVEMENT',['AchievementFrame']),
 ('achievements.statistics','Open statistics.','TOGGLESTATISTICS',['AchievementFrame']),
 ('friends.open','Open friends and social window.','TOGGLESOCIAL',['FriendsFrame']),
 ('guild.open','Open the guild window.','TOGGLEGUILDTAB',['GuildFrame','FriendsFrame']),
 ('pve_group_finder.open','Open the dungeon group finder.','TOGGLEGROUPFINDER',['PVEFrame']),
 ('pvp.open','Open the player versus player window.','TOGGLECHARACTER4',['PVPUIFrame','PVPFrame']),
 ('menu.open','Open the game menu.','TOGGLEGAMEMENU',['GameMenuFrame']),
 ('macros.open','Open the macro editor.',None,['MacroFrame']),
 ('calendar.open','Open the calendar.',None,['CalendarFrame']),
]


def binding_key(value):
    parts=value.split('-');name=parts[-1]
    specials={'ESCAPE':'Escape','SPACE':'space','ENTER':'Return','TAB':'Tab'}
    name=specials.get(name,name.lower() if len(name)==1 else name)
    return '+'.join([p.lower() for p in parts[:-1]]+[name])


def choose(goal,state,actions,seed):
    order=list(actions);random.Random(seed).shuffle(order)
    payload={'model':MODEL,'state':{'goal':goal,'visible_panels':state.get('panels',[]),
        'open_bags':state.get('bags',[]),'last_ui_errors':state.get('errors',[])},
        'questions':{'action':{'type':'choice','instructions':'Choose the ordinary input that advances the player goal.',
            'criteria':{key:actions[key]['description'] for key in order}}}}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    req=urllib.request.Request(ENDPOINT,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as response:result=json.load(response)
    answer=result.get('answers',{}).get('action',{})
    if result.get('model')!=MODEL or result.get('revision')!=REVISION or answer.get('choice') not in actions:
        raise RuntimeError('unexpected model identity or action')
    if answer.get('type')!='choice' or any(b.get('truncated_fields') for b in result.get('token_budget',{}).values()):
        raise RuntimeError('incomplete model request or answer')
    return payload,result,answer['choice']


class Trial:
    def __init__(self,out):
        self.out=out;out.mkdir(parents=True,exist_ok=False,mode=0o700)
        self.fixture=actors.load();self.guid=f"Player-1-{self.fixture['guid']:08X}"
        self.io=owned_input.Inputs();self.rng=random.Random(44260895)
        self.receipt={'schema':'client442_laya_interactions_v1','started_at':time.time(),'actor':self.fixture,
            'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
            'controller':'laya_candidate_selection','model':MODEL,'revision':REVISION,'fine_tuned':False,
            'model_observes':'normal addon-visible state; screenshots retained for human verification',
            'cases':[],'cleanup':[],'completed':False,'failure':None}
        self.persist()

    def persist(self):
        lab.private_write(self.out/'episode.json',json.dumps(self.receipt,indent=2)+'\n')

    def observe(self,label):
        from PIL import Image
        from tools.second_client import ctl
        ctl._launcher_env=lab.client_environment
        monitor=owned_input.focus();path=self.out/(label+'.png');deadline=time.monotonic()+22
        while True:
            with redirect_stdout(StringIO()):ctl.shot(str(path))
            with Image.open(path) as image:
                state=decode_image(image);movement=decode_movement(image,x=15,y=15,cell_size=3.75)
            if state['mode']=='state':break
            if time.monotonic()>deadline:raise RuntimeError('UI state observation deadline exceeded')
            time.sleep(.1)
        if state['guid']!=self.guid or state['build']!=60895 or not movement['in_world']:
            raise RuntimeError('observation is not the owned active character')
        if movement['dead'] or movement['in_combat'] or movement['on_taxi'] or movement['health_percent']<50:
            raise RuntimeError('interaction fixture is unsafe')
        return state,{'file':path.name,'sha256':lab.sha256(path),'monitor':monitor,'movement':movement}

    def execute(self,action):
        with owned_input.lease():
            if action['kind']=='key':self.io.key(action['value'])
            elif action['kind']=='chat':
                self.io.key('Return',hold=.4);time.sleep(.2)
                self.io.type(action['value']);time.sleep(.2);self.io.key('Return',hold=.4)
            elif action['kind']=='click':self.io.click(*action['value'])
            elif action['kind']=='edit':
                self.io.click(*action['point']);self.io.key('ctrl+a');self.io.type(action['value'])
            else:raise ValueError('unsupported physical action')
        time.sleep(4 if action['kind']=='chat' and action['value']=='/reload' else .8)

    def step(self,case_id,goal,actions,oracle):
        index=len(self.receipt['cases']);row={'id':case_id,'goal':goal,'time':time.time(),'status':'started'}
        self.receipt['cases'].append(row);self.persist()
        try:
            before,bframe=self.observe(f'{index:03}_before')
            request,response,selected=choose(goal,before,actions,index+442)
            row.update(before=before,before_frame=bframe,request=request,response=response,selected=selected,
                input=actions[selected]);self.persist()
            self.execute(actions[selected]);after,aframe=self.observe(f'{index:03}_after')
            row.update(after=after,after_frame=aframe)
            if actions[selected]['kind']=='chat' and after.get('chat_edit_open'):
                raise RuntimeError('selected chat command remained in the edit box')
            verdict=oracle(before,after,selected)
            row.update(after=after,after_frame=aframe,**verdict)
        except Exception as e:row.update(status='infrastructure_failure',error=f'{type(e).__name__}: {e}')
        self.persist();print(json.dumps({k:row.get(k) for k in ['id','selected','status','error']}),flush=True)
        if row['status']=='infrastructure_failure':raise RuntimeError(row.get('error'))
        return row

    def clean_panels(self):
        # Fixture cleanup uses code, never counts as a model action or pass.
        for i in range(6):
            state,frame=self.observe('cleanup_latest')
            if not state.get('panels') and not state.get('bags'):return
            self.io.key('Escape');time.sleep(.3)
            self.receipt['cleanup'].append({'time':time.time(),'input':'Escape','source':'code_fixture_cleanup',
                'before_panels':state.get('panels'),'before_bags':state.get('bags')})
        raise RuntimeError('panel cleanup did not settle')


def panel_suite(out,catalog):
    trial=Trial(out);rows={r['name']:r for r in json.loads(catalog.read_text())['rows']};registry={}
    for name,row in rows.items():
        keys=row.get('keys') or []
        if keys and name.startswith(('TOGGLECHARACTER','TOGGLESPELLBOOK','TOGGLETALENTS','TOGGLEQUESTLOG',
            'TOGGLEWORLDMAP','TOGGLECOLLECTIONS','TOGGLEENCOUNTERJOURNAL','TOGGLEACHIEVEMENT','TOGGLESTATISTICS',
            'TOGGLESOCIAL','TOGGLEGUILDTAB','TOGGLEGROUPFINDER','TOGGLEGAMEMENU','TOGGLEBAG','TOGGLEBACKPACK','OPENALLBAGS')):
            registry[name]={'kind':'key','value':binding_key(keys[0]),'description':f"Press {keys[0]}: {row.get('caption',name)}."}
    registry['TOGGLECHARACTER1']['description']='Press K: open or close the professions and skills spellbook.'
    registry['macro_command']={'kind':'chat','value':'/macro','description':'Type /macro in chat to open the macro editor.'}
    initial,_=trial.observe('initial_registry')
    calendar=next((c for c in initial['controls'] if c['name']=='GameTimeFrame'),None)
    if calendar:registry['calendar_button']={'kind':'click','value':[round(calendar['x']/65535*1280),round(calendar['y']/65535*720)],
        'description':'Click the minimap calendar button.'}
    def visible(state,names):return bool(state.get('bags')) if names==['bags'] else any(n in (state.get('panels') or []) for n in names)
    try:
        for case_id,goal,binding,names in PANELS:
            trial.clean_panels();target=binding or ('macro_command' if case_id=='macros.open' else 'calendar_button')
            if binding and binding.startswith('TOGGLEBAG'):
                bag=int(binding[-1]);state,_=trial.observe('bag_fixture_'+str(bag))
                if not state['bag_slots'][bag]:
                    trial.receipt['cases'].append({'id':case_id,'status':'fixture_unavailable','error':'bag slot is empty',
                        'bag_slots':state['bag_slots']});trial.persist();continue
            if target not in registry:
                trial.receipt['cases'].append({'id':case_id,'status':'fixture_unavailable','error':'no owned binding'});continue
            distractors=trial.rng.sample([n for n in registry if n!=target],4)
            actions={n:registry[n] for n in [target]+distractors}
            result=trial.step(case_id,goal,actions,lambda b,a,s:{
                'status':'panel_open_pass' if visible(a,names) else ('controller_failure' if s!=target else 'client_or_protocol_failure'),
                'oracle':{'panel_visible':visible(a,names),'expected_panels':names,'qualified_scope':'panel visibility only',
                    'data':{k:a.get(k) for k in ['reputations','currency_types','equipment','professions']}}})
            if result['status']=='panel_open_pass':
                close_actions={'escape':{'kind':'key','value':'Escape','description':'Press Escape to close open windows and return to the world.'},
                    **{n:registry[n] for n in trial.rng.sample([n for n in registry if n!=target and n!='TOGGLEGAMEMENU'],4)}}
                trial.step(case_id+'.close', 'Close every open panel and bag. Leave the world view visible with no new windows.',close_actions,
                    lambda b,a,s:{'status':'panel_close_pass' if not a.get('panels') and not a.get('bags') else ('controller_failure' if s!='escape' else 'client_or_protocol_failure'),
                        'oracle':{'all_panels_closed':not a.get('panels') and not a.get('bags'),'qualified_scope':'panel visibility only'}})
        trial.clean_panels();trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt.update(finished_at=time.time(),counts=dict(Counter(r['status'] for r in trial.receipt['cases'])))
        trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'counts':trial.receipt['counts'],'failure':trial.receipt['failure']}))
    return trial.receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--bindings',type=Path,required=True);args=p.parse_args();panel_suite(args.output,args.bindings)


if __name__=='__main__':main()
