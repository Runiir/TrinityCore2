"""Learn Tame Beast through the owned Hunter's ordinary native trainer service."""
import argparse,json,re,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,reviewed,character,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import protected,trainer_contract
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_control_training import catalog
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .interaction_spellbook_navigation import known
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import Cursor


SPELL=1515
TRAINER=40
NAME='Benjamin Foxworthy'
PRICE=646 # Native quote: the680 base cost with the current friendly discount.
LESSONS={'tame':('Tame Beast',1515,1515,[]),'control':('Control Pet',79682,93321,[[79682,93321,1]])}


def baseline(t,preparation,lesson='tame'):
    old=prepared(t,preparation)
    if tuple(t.fixture[k] for k in ('guid','account_id','character_name','race','class','level'))!=(
            6,2,'Harnesshunt',1,3,10):raise RuntimeError('requires the exact prepared Hunter')
    trainer_contract();checks=protected(old)
    if lesson not in LESSONS:raise ValueError('unsupported owned Hunter lesson')
    if lesson=='control':
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT SpellId,MoneyCost,ReqLevel FROM client442_world.trainer_spell '
                'WHERE TrainerId=40 AND SpellId=79682');training=q.fetchall()
            q.execute('SELECT entry,SpellID,Active FROM client442_world.spell_learn_spell WHERE entry=79682');relation=q.fetchall()
        if training!=((79682,680,10),) or relation!=((79682,93321,1),):
            raise RuntimeError('native Control Pet prerequisite differs')
    if not all(checks.values()):raise RuntimeError('protected Hunter actors differ')
    t.receipt.update(protected_checks=checks,qualified_scope='Owned Hunter training prerequisite only; no qualification.')
    return old,actors.session_entry(t.fixture)['session']


def prior(t,path,session,phase):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned Hunter receipt')
    e=json.loads(path.read_text())
    if (e.get('completed') is not True or e.get('failure') or not e.get('finished_at') or
        e.get('phase')!=phase or e.get('actor')!=t.fixture or e.get('runtime')!=t.receipt['runtime'] or
        e.get('native_session')!=session or
        e.get('fixture_source',{}).get('sha256')!=t.receipt['fixture_source']['sha256'] or
        set(e.get('protected_checks',{}))!={f'actor_{g}_unchanged' for g in range(1,6)} or
        not all(e['protected_checks'].values())):raise RuntimeError('closed same-entry Hunter source differs')
    t.receipt['source']={'path':str(path),'sha256':lab.sha256(path)};return e


def recon(t,preparation,source):
    old,session=baseline(t,preparation);entry_source(t,source,session,preparation)
    t.clean_panels();t.execute({'kind':'chat','value':'/targetexact '+NAME})
    state,frame=t.observe('hunter_trainer_staged')
    if state.get('target',{}).get('name')!=NAME or not state['target'].get('visible'):
        raise RuntimeError('existing owned Hunter trainer absent')
    checks=protected(old)
    if not all(checks.values()):raise RuntimeError('protected Hunter actors differ')
    t.receipt.update(state=state,frame=frame,native_session=session,
        entry_source={'path':str(source.resolve()),'sha256':lab.sha256(source)},
        protected_checks=checks,phase='hunter_trainer_staged',completed=True)


def refresh(t,preparation,source):
    old,session=baseline(t,preparation);e=prior(t,source,session,'hunter_trainer_staged')
    state,frame=t.observe('hunter_trainer_refreshed');target=state.get('target',{})
    if target.get('guid')!=e['state']['target']['guid'] or target.get('name')!=NAME or not target.get('visible'):
        raise RuntimeError('staged Hunter trainer no longer matches the closed source')
    checks=protected(old)
    if not all(checks.values()):raise RuntimeError('protected Hunter actors differ')
    t.receipt.update(state=state,frame=frame,native_session=session,protected_checks=checks,
        phase='hunter_trainer_staged',completed=True,input_sent=False,
        qualified_scope='Read-only same-session Hunter trainer staging refresh; no input or qualification.')


def open_trainer(t,preparation,source,review_path):
    old,session=baseline(t,preparation);e=prior(t,source,session,'hunter_trainer_staged')
    d=reviewed(t,review_path,NAME)
    if d['frame']['sha256']!=e['frame']['sha256']:raise RuntimeError('reviewed Hunter trainer image differs')
    state,_=t.observe('hunter_trainer_before')
    if state.get('target',{}).get('guid')!=e['state']['target']['guid']:
        raise RuntimeError('current Hunter trainer identity differs')
    def opened(b,a,s):
        return {'status':'hunter_trainer_open_pass' if s=='interact' and any(x in a['panels'] for x in
            ('GossipFrame','ClassTrainerFrame')) else 'client_or_protocol_failure','oracle':{'panels':a['panels']}}
    require(t.step('hunter.trainer_interact','Speak to the reviewed nearby Hunter trainer.',
        {'interact':{'kind':'click','value':d['point'],'button':3,'hold':.4,
            'description':'Right-click the reviewed visible '+NAME+'.'}},opened,
        diagnostic_action='interact'),'hunter_trainer_open_pass')
    state,_=t.observe('hunter_trainer_response')
    if 'GossipFrame' in state['panels']:
        require(click_case(t,'hunter.trainer_gossip','Open the normal Hunter trainer service.',
            lambda c:'train' in c['text'].lower(),lambda b,a,s:{'status':'hunter_service_pass' if s and
                'ClassTrainerFrame' in a['panels'] else 'client_or_protocol_failure'}),'hunter_service_pass')
    state,frame=t.observe('hunter_trainer_open')
    if 'ClassTrainerFrame' not in state['panels']:raise RuntimeError('stock Hunter trainer absent')
    native=catalog(session,t.receipt['started_at'],entry=46983,trainer_id=TRAINER)
    oracle=Inventory(lab.ROOT,session,6).poll();checks=protected(old)
    t.receipt.update(state=state,frame=frame,trainer_controls=controls(t),native_catalog=native,
        native_session=session,resources=resources(oracle),saved_spells=known(6),protected_checks=checks,
        phase='hunter_trainer_open',completed=all(checks.values()))
    if not all(checks.values()):raise RuntimeError('protected Hunter actors differ')


def select(t,preparation,source,lesson='tame'):
    old,session=baseline(t,preparation,lesson);e=prior(t,source,session,'hunter_trainer_open')
    name,parent,learned,relation=LESSONS[lesson]
    rows=[r for r in e['native_catalog']['rows'] if r[0]==parent]
    # Native class trainers omit ReqLevel once the player satisfies it.
    if len(rows)!=1 or rows[0][1:4]!=[1,PRICE,0]:raise RuntimeError('native Hunter lesson unavailable')
    state,_=t.observe('tame_selection_before')
    if 'ClassTrainerFrame' not in state['panels']:raise RuntimeError('stock Hunter trainer no longer open')
    for attempt in range(8):
        current=[c for c in controls(t) if re.fullmatch(r'ClassTrainerSkill\d+',c['name'])]
        if any(c['text'].strip()==name for c in current):break
        header=next((c for i,c in enumerate(current[:-1]) if c['text'] and
            not c['text'].startswith('  ') and current[i+1]['text'].startswith('  ')),None)
        if header is None:raise RuntimeError(name+' is absent from observed trainer rows')
        require(click_case(t,f'hunter.collapse_header_{attempt}','Collapse the observed expanded trainer header.',
            lambda c:c['name']==header['name'] and c['text']==header['text'],
            lambda b,a,s:{'status':'hunter_header_pass' if s and 'ClassTrainerFrame' in a['panels'] else
                'client_or_protocol_failure'}),'hunter_header_pass')
    def selected(b,a,s):
        service=a.get('trainer',{}).get('service',{})
        checks={'ordinary_select':bool(s),'name':service.get('name')==name,
            'available':service.get('state')=='available','cost':service.get('cost')==PRICE,
            'level':service.get('level')==rows[0][3],'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'hunter_lesson_selected_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native':rows[0],'public':service}}
    require(click_case(t,'hunter.select_'+lesson,'Select the observed available '+name+' lesson.',
        lambda c:c['name'].startswith('ClassTrainerSkill') and c['text'].strip()==name,
        selected),'hunter_lesson_selected_pass')
    state,frame=t.observe('tame_selected');oracle=Inventory(lab.ROOT,session,6).poll();checks=protected(old)
    t.receipt.update(state=state,frame=frame,native_lesson=rows[0],native_trainer_guid=e['native_catalog']['guid'],
        native_session=session,resources=resources(oracle),saved_spells=known(6),protected_checks=checks,
        lesson=lesson,phase=lesson+'_lesson_selected',completed=all(checks.values()))
    if not all(checks.values()):raise RuntimeError('protected Hunter actors differ')


def learned_checks(rows,guid,before_spells,after_spells,before,after,relation,lesson='tame'):
    name,parent,learned,expected_relation=LESSONS[lesson]
    exact=lambda direction,name,body:[p for p in rows if p.get('direction')==direction and
        p.get('name')==name and p.get('body')==body.hex()]
    native=exact('from_native','SMSG_LEARNED_SPELL',struct.pack('<II',learned,0))
    modern=exact('to_client','SMSG_LEARNED_SPELLS',struct.pack('<IIBIB',1,0,0,learned,0))
    commands=exact('to_native','CMSG_TRAINER_BUY_SPELL',struct.pack('<QII',guid,TRAINER,parent))
    return {'one_native_purchase':len(commands)==1,'native_learned':len(native)==1,
        'modern_learned':len(modern)==1,'exact_native_relation':relation==expected_relation,
        'saved_lesson':not any(r[0] in (parent,learned) for r in before_spells) and
            after_spells==sorted(before_spells+[[parent,1,0]]),
        'exact_charge_inventory':after=={**before,'money':before['money']-PRICE}}


def learn(t,preparation,source,lesson='tame'):
    old,session=baseline(t,preparation,lesson);e=prior(t,source,session,lesson+'_lesson_selected')
    name,parent,learned_spell,expected_relation=LESSONS[lesson]
    # Older closed Tame Beast sources precede the explicit lesson field.
    if e.get('lesson','tame')!=lesson or e['native_lesson'][0]!=parent:
        raise RuntimeError('selected Hunter lesson identity differs')
    packets=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in packets.poll():pass
    oracle=Inventory(lab.ROOT,session,6).poll();before=resources(oracle)
    state,_=t.observe('tame_purchase_before');service=state.get('trainer',{}).get('service',{})
    if (before!=e['resources'] or known(6)!=e['saved_spells'] or any(r[0] in (parent,learned_spell) for r in known(6)) or
        service.get('name')!=name or service.get('state')!='available' or service.get('cost')!=PRICE or
        before['money']<=PRICE):raise RuntimeError('selected untrained Hunter lesson or resources differ')
    started=time.time();t.receipt.update(native_session=session,before=before,native_lesson=e['native_lesson'],
        purchase_started_at=started,lesson=lesson,retained_change='Normally purchased '+name+' and its exact quoted646 copper charge.')
    def learned_outcome(b,a,s):
        lab.server_command('saveall');time.sleep(1);oracle.poll();after=resources(oracle)
        safe={'CMSG_TRAINER_BUY_SPELL','SMSG_TRAINER_BUY_SUCCEEDED','SMSG_TRAINER_BUY_FAILED',
            'SMSG_LEARNED_SPELL','SMSG_LEARNED_SPELLS'}
        rows=[r for r in packets.poll() if r.get('session')==session and r.get('time',0)>=started and r.get('name') in safe]
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT entry,SpellID,Active FROM client442_world.spell_learn_spell WHERE entry=%s OR SpellID=%s',
                (parent,learned_spell))
            relation=[list(r) for r in q.fetchall()]
        checks=learned_checks(rows,e['native_trainer_guid'],e['saved_spells'],known(6),before,after,relation,lesson)
        checks.update(ordinary_train=bool(s),protected_originals=all(protected(old).values()),
            ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        t.receipt.update(purchase_packets=rows,purchase_checks=checks,after=after,native_learn_relation=relation,
            protected_checks=protected(old));t.persist()
        return {'status':'hunter_training_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'before_money':before['money'],'after_money':after['money']}}
    require(click_case(t,'hunter.train_'+lesson,'Purchase the selected native '+name+' lesson once.',
        lambda c:c['name']=='ClassTrainerTrainButton',learned_outcome),'hunter_training_pass')
    t.clean_panels();state,frame=t.observe('tame_training_closed')
    t.receipt.update(state=state,frame=frame,phase='tame_beast_trained' if lesson=='tame' else 'control_pet_trained',completed=True,
        qualified_scope='Normal '+name+' purchase on the separate native level10 Hunter. '
            'Exact native/client learn and copper/inventory evidence; pet operations remain open.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['recon','refresh','open','select','learn'])
    for name in ('preparation','source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--review',type=Path);p.add_argument('--lesson',choices=LESSONS,default='tame');a=p.parse_args()
    if a.action=='open' and not a.review:p.error('requires the fresh trainer image review')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='recon':recon(t,a.preparation,a.source)
            elif a.action=='refresh':refresh(t,a.preparation,a.source)
            elif a.action=='open':open_trainer(t,a.preparation,a.source,a.review)
            elif a.action=='select':select(t,a.preparation,a.source,a.lesson)
            else:learn(t,a.preparation,a.source,a.lesson)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase')}),flush=True)
