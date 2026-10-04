"""Bounded choices executed through owned private client inputs.

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
from contextlib import contextmanager
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
        'open_bags':state.get('bags',[]),'last_ui_errors':state.get('errors',[]),
        'ground_targeting_cursor_active':state.get('spell_targeting',False)},
        'questions':{'action':{'type':'choice','instructions':'Choose the ordinary input that advances the player goal.',
            'criteria':{key:actions[key]['description'] for key in order}}}}
    if state.get('guild_ui'):
        guild=state['guild_ui']
        payload['state']['guild']={key:guild[key] for key in ['in_guild','name','rank','permissions'] if key in guild}
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
    def __init__(self,out,controller='code'):
        if controller not in ['laya','code']:raise ValueError('unknown interaction controller')
        self.controller=controller
        self.combat_observation_deadline=None
        self.out=out;out.mkdir(parents=True,exist_ok=False,mode=0o700)
        self.fixture=actors.load();self.guid=f"Player-1-{self.fixture['guid']:08X}"
        self.io=owned_input.Inputs();self.rng=random.Random(44260895)
        self.receipt={'schema':'client442_laya_interactions_v1','started_at':time.time(),'actor':self.fixture,
            'observer_file_sha256':lab.sha256(lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness/ClientInteractions.lua'),
            'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
            'controller':'laya_candidate_selection' if controller=='laya' else 'code_diagnostic_ordinary_inputs',
            'model':MODEL if controller=='laya' else None,'revision':REVISION if controller=='laya' else None,'fine_tuned':False,
            'model_observes':'normal addon-visible state; screenshots retained for human verification',
            'cases':[],'cleanup':[],'completed':False,'failure':None}
        # Runtime code can differ from orchestration HEAD during a bridge repair.
        # Process commands contain launcher tickets; retain only safe identity fields.
        for kind in ['worldserver','modern_world','client']:
            runtime=lab.owned_process(kind)
            if not runtime:raise RuntimeError('owned '+kind+' is not running')
            self.receipt.setdefault('runtime',{})[kind]={k:runtime[k] for k in
                ['pid','start_ticks','engine','build'] if k in runtime}
        self.persist()
        compatibility=lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/Client442Compatibility/GuildTabs.lua'
        self.receipt['compatibility_addon_sha256']=lab.sha256(compatibility) if compatibility.is_file() else None
        self.persist()

    def persist(self):
        if self.io.initialization is not None:
            self.receipt['input_initialization']=self.io.initialization
        lab.private_write(self.out/'episode.json',json.dumps(self.receipt,indent=2)+'\n')

    def observe(self,label,seconds=28):
        if not 1<=seconds<=180:raise ValueError('observation timeout exceeds its bounded duration')
        from PIL import Image
        from tools.second_client import ctl
        ctl._launcher_env=lab.client_environment
        monitor=owned_input.focus();path=self.out/(label+'.png');deadline=time.monotonic()+seconds
        # Multiple cleanup calls and settling samples may reuse a logical label.
        # A receipt's retained frame must never be overwritten by a later read.
        suffix=1
        while path.exists():
            path=self.out/(label+'_'+str(suffix)+'.png');suffix+=1
        while True:
            with redirect_stdout(StringIO()):ctl.shot(str(path))
            try:
                with Image.open(path) as image:
                    state=decode_image(image);movement=decode_movement(image,x=15,y=15,cell_size=3.75)
            except ValueError as error:
                # Normal reloads can expose a partially redrawn observation
                # strip. Retry the screenshot; never accept a missing identity.
                if time.monotonic()>deadline:raise RuntimeError('UI observation did not become decodable') from error
                time.sleep(.1);continue
            if state['mode']=='state':break
            if time.monotonic()>deadline:raise RuntimeError('UI state observation deadline exceeded')
            time.sleep(.1)
        if state['guid']!=self.guid or state['build']!=60895 or not movement['in_world']:
            raise RuntimeError('observation is not the owned active character')
        combat_allowed=(self.combat_observation_deadline is not None and
            time.monotonic()<self.combat_observation_deadline)
        if movement['dead'] or (movement['in_combat'] and not combat_allowed) or movement['on_taxi'] or movement['health_percent']<50:
            raise RuntimeError('interaction fixture is unsafe')
        return state,{'file':path.name,'sha256':lab.sha256(path),'monitor':monitor,'movement':movement}

    @contextmanager
    def bounded_combat_observation(self,seconds):
        """Permit combat observations only inside an explicit bounded fixture.

        Owned identity, monitor, life, health and taxi guards remain active.
        This changes observation permission, never character state or inputs.
        """
        if not 1<=seconds<=60 or self.combat_observation_deadline is not None:
            raise ValueError('combat observation requires one bounded 1-60 second window')
        self.combat_observation_deadline=time.monotonic()+seconds
        self.receipt.setdefault('combat_observation_windows',[]).append({'started_at':time.time(),'seconds':seconds})
        self.persist()
        try:yield
        finally:self.combat_observation_deadline=None

    def execute(self,action):
        with owned_input.lease():
            if action['kind']=='key':
                hold=action.get('hold',.15)
                if not .05<=hold<=2:raise ValueError('interaction key hold exceeds its bounded duration')
                self.io.key(action['value'],hold=hold)
            elif action['kind']=='chat':
                self.io.key('Return',hold=.4);time.sleep(.2)
                self.io.type(action['value']);time.sleep(.2);self.io.key('Return',hold=.4)
            elif action['kind']=='click':
                hold=action.get('hold',.15)
                if not .05<=hold<=2:raise ValueError('interaction click hold exceeds its bounded duration')
                self.io.click(*action['value'],button=action.get('button',1),modifiers=action.get('modifiers',()),hold=hold)
            elif action['kind']=='edit':
                self.io.click(*action['point'])
                deadline=time.monotonic()+12;samples=[]
                while True:
                    state,frame=self.observe(f'input_{len(self.receipt["cases"]):03}_edit_focus')
                    focused=any(field.get('focused') and
                        [round(field['x']/65535*1280),round(field['y']/65535*720)]==action['point']
                        for field in state.get('edit_fields') or [])
                    samples.append({'sequence':state['sequence'],'frame':frame,'focused':focused,
                        'input_replayed':False})
                    self.receipt.setdefault('edit_focus_checks',[]).append(samples[-1]);self.persist()
                    if focused:break
                    if time.monotonic()>deadline:
                        raise RuntimeError('selected edit field did not gain focus; refusing to send text')
                    time.sleep(.2)
                self.io.key('ctrl+a',hold=.4);time.sleep(.2)
                if action['value']:self.io.type(action['value'])
                else:self.io.key('BackSpace')
            elif action['kind']=='drag':self.io.drag(action['start'],action['end'])
            elif action['kind']=='hover':
                value=action['value']
                if len(value)!=2 or not 0<=value[0]<1280 or not 0<=value[1]<720:
                    raise ValueError('hover exceeds the owned client input bounds')
                self.io.move(*value)
            else:raise ValueError('unsupported physical action')
        time.sleep(4 if action['kind']=='chat' and action['value']=='/reload' else .8)
        transport=[]
        if action['kind']=='chat':
            # Background reloads can take more than the ordinary 28-second
            # state budget. Only extend the read wait; never resend /reload.
            seconds=60 if action['value']=='/reload' else 28
            state,frame=self.observe(f'input_{len(self.receipt["cases"]):03}_chat_check',seconds=seconds)
            deadline=time.monotonic()+12
            while state.get('chat_edit_open') and time.monotonic()<deadline:
                transport.append({'reason':'wait for selected command submission','frame':frame,
                    'observed_text':state.get('chat_edit_text'),'input_replayed':False})
                time.sleep(.2)
                state,frame=self.observe(f'input_{len(self.receipt["cases"]):03}_chat_settling')
            if state.get('chat_edit_open'):
                if state.get('chat_edit_text','').rstrip(' ')!=action['value']:
                    raise RuntimeError('chat input differs from the selected command; refusing to submit it')
                transport.append({'reason':'selected command remained after name completion','input':'Return',
                    'observed_text':state['chat_edit_text'],'normalization':'ignore trailing spaces only',
                    'hold':.4,'before_frame':frame})
                self.io.key('Return',hold=.4);time.sleep(.8)
                state,frame=self.observe(f'input_{len(self.receipt["cases"]):03}_chat_retry')
                transport[-1]['after_frame']=frame
                if state.get('chat_edit_open'):raise RuntimeError('bounded chat submission retry did not settle')
        return transport

    def step(self,case_id,goal,actions,oracle,diagnostic_action=None,await_state=None):
        index=len(self.receipt['cases']);row={'id':case_id,'goal':goal,'time':time.time(),'status':'started'}
        self.receipt['cases'].append(row);self.persist()
        try:
            before,bframe=self.observe(f'{index:03}_before')
            if self.controller=='laya':request,response,selected=choose(goal,before,actions,index+442)
            else:
                if diagnostic_action not in actions:raise RuntimeError('diagnostic input is not specified for '+case_id)
                request,response,selected=None,None,diagnostic_action
            row.update(before=before,before_frame=bframe,request=request,response=response,selected=selected,
                selection_source=self.controller,input=actions[selected]);self.persist()
            row['input_transport']=self.execute(actions[selected]);after,aframe=self.observe(f'{index:03}_after')
            if await_state is not None:
                deadline=time.monotonic()+12;samples=[]
                while not await_state(after) and time.monotonic()<deadline:
                    samples.append({'sequence':after['sequence'],'panels':after.get('panels'),
                        'bags':after.get('bags'),'frame':aframe})
                    time.sleep(.2);after,aframe=self.observe(f'{index:03}_settle_{len(samples):02}')
                row['settling_samples']=samples
                row['input_replayed_while_settling']=False
            row.update(after=after,after_frame=aframe)
            if actions[selected]['kind']=='chat' and after.get('chat_edit_open'):
                raise RuntimeError('selected chat command remained in the edit box')
            verdict=oracle(before,after,selected)
            row.update(after=after,after_frame=aframe,**verdict)
        except Exception as e:row.update(status='infrastructure_failure',error=f'{type(e).__name__}: {e}')
        except KeyboardInterrupt:
            row.update(status='interrupted',error='Trial interrupted before qualification')
            self.receipt['failure']='KeyboardInterrupt: trial interrupted'
            self.persist();raise
        self.persist();print(json.dumps({k:row.get(k) for k in ['id','selected','status','error']}),flush=True)
        if row['status']=='infrastructure_failure':raise RuntimeError(row.get('error'))
        return row

    def clean_panels(self):
        # Fixture cleanup uses code, never counts as a model action or pass.
        state,frame=self.observe('cleanup_latest')
        def signature(s):return (tuple(sorted(s.get('panels') or [])),tuple(sorted(s.get('bags') or [])),
            bool(s.get('chat_edit_open')),bool(s.get('spell_targeting')),bool(s.get('pending_glyph')),bool(s.get('cursor_info')))
        for i in range(6):
            previous=signature(state)
            if previous==((),(),False,False,False,False):
                if i==0:return
                # Confirm the empty observation through another update cycle.
                time.sleep(.2);state,frame=self.observe('cleanup_empty_confirm')
                if signature(state)==previous:return
                continue
            cursor=bool(state.get('cursor_info'))
            row={'time':time.time(),'input':'RightClick' if cursor else 'Escape','source':'code_fixture_cleanup',
                'before_panels':state.get('panels'),'before_bags':state.get('bags'),'settling':[]}
            self.receipt['cleanup'].append(row);self.persist()
            if cursor:
                row.update(point=[900,500],before_cursor=state['cursor_info'])
                self.io.click(900,500,button=3)
            else:self.io.key('Escape')
            deadline=time.monotonic()+12
            while True:
                time.sleep(.2);state,frame=self.observe('cleanup_settled_'+str(i))
                row['settling'].append({'sequence':state['sequence'],'panels':state.get('panels'),
                    'bags':state.get('bags'),'frame':frame});self.persist()
                if signature(state)!=previous:break
                if time.monotonic()>deadline:
                    raise RuntimeError('panel cleanup did not change state; refusing to replay Escape')
        raise RuntimeError('panel cleanup did not settle')


def panel_suite(out,catalog,controller='code'):
    trial=Trial(out,controller);rows={r['name']:r for r in json.loads(catalog.read_text())['rows']};registry={}
    for name,row in rows.items():
        keys=row.get('keys') or []
        if keys and name.startswith(('TOGGLECHARACTER','TOGGLESPELLBOOK','TOGGLETALENTS','TOGGLEQUESTLOG',
            'TOGGLEWORLDMAP','TOGGLECOLLECTIONS','TOGGLEENCOUNTERJOURNAL','TOGGLEACHIEVEMENT','TOGGLESTATISTICS',
            'TOGGLESOCIAL','TOGGLEGUILDTAB','TOGGLEGROUPFINDER','TOGGLEGAMEMENU','TOGGLEBAG','TOGGLEBACKPACK','OPENALLBAGS')):
            registry[name]={'kind':'key','value':binding_key(keys[0]),'description':f"Press {keys[0]}: {row.get('caption',name)}."}
    registry['TOGGLECHARACTER1']['description']='Press K: open or close the professions and skills spellbook.'
    registry['macro_command']={'kind':'chat','value':'/macro','description':'Type /macro in chat to open the macro editor.'}
    initial,_=trial.observe('initial_registry')
    calendar=initial.get('calendar_button') or next((c for c in initial['controls'] if c['name']=='GameTimeFrame'),None)
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
                    'data':{k:a.get(k) for k in ['reputations','currency_types','equipment','professions']}}},diagnostic_action=target)
            if result['status']=='panel_open_pass':
                close_actions={'escape':{'kind':'key','value':'Escape','description':'Press Escape to close open windows and return to the world.'},
                    **{n:registry[n] for n in trial.rng.sample([n for n in registry if n!=target and n!='TOGGLEGAMEMENU'],4)}}
                trial.step(case_id+'.close', 'Close every open panel and bag. Leave the world view visible with no new windows.',close_actions,
                    lambda b,a,s:{'status':'panel_close_pass' if not a.get('panels') and not a.get('bags') else ('controller_failure' if s!='escape' else 'client_or_protocol_failure'),
                        'oracle':{'all_panels_closed':not a.get('panels') and not a.get('bags'),'qualified_scope':'panel visibility only'}},diagnostic_action='escape')
        trial.clean_panels();trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt.update(finished_at=time.time(),counts=dict(Counter(r['status'] for r in trial.receipt['cases'])))
        trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'counts':trial.receipt['counts'],'failure':trial.receipt['failure']}))
    return trial.receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--bindings',type=Path,required=True);p.add_argument('--controller',choices=['laya','code'],default='code')
    args=p.parse_args();panel_suite(args.output,args.bindings,args.controller)


if __name__=='__main__':main()
