"""Inspect the eligible stock warlock trainer before a native-bound purchase."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_owned_class_fixture import prepared,reviewed,origin_checks,character,saved,pets,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .interaction_spellbook_navigation import known
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import entries,Cursor
from .world.buffer import Reader


def protected(old):
    r=old['retained_level_one'];checks=origin_checks(old)
    checks.update(retained_level_one_character=character(4,2)==r['character'],
        retained_level_one_saved=saved(4)==r['saved'],retained_level_one_pets=pets(4)==r['pets'])
    return checks


def persisted_training(before,after,relation):
    # LearnSpell marks the93375 child dependent; SaveSpells persists its80388
    # parent. Requiring a saved child row would contradict native persistence.
    return relation==[[80388,93375,1]] and after==sorted(before+[[80388,1,0]])


def learn_relation():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT entry,SpellID,Active FROM client442_world.spell_learn_spell WHERE entry=80388')
        return [list(r) for r in q.fetchall()]


def catalog(session,since,*,entry=906,trainer_id=154):
    found=None
    for p in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if (p.get('session')!=session or p.get('time',0)<since or p.get('direction')!='from_native' or
            p.get('name')!='SMSG_TRAINER_LIST'):continue
        r=Reader(bytes.fromhex(p['body']));guid,kind,trainer,count=r.unpack('QIII')
        if (guid>>32)&0xfffff!=entry or trainer!=trainer_id:continue
        if count>4096:raise RuntimeError('trainer count exceeds native bound')
        rows=[r.unpack('IBIBII2iII') for _ in range(count)]
        found={'packet':p,'guid':guid,'trainer':trainer,'kind':kind,'rows':[list(x) for x in rows]}
    if found is None:raise RuntimeError('owned native trainer catalog absent')
    return found


def baseline(t,preparation):
    old=prepared(t,preparation)
    if (t.fixture['character_name'],t.fixture['race'],t.fixture['class'],t.fixture['level'])!=('Harnessctrl',1,9,10):
        raise RuntimeError('requires the separate eligible control fixture')
    checks=protected(old)
    if not all(checks.values()):raise RuntimeError('protected original fixtures differ')
    t.receipt.update(protected_checks=checks,qualified_scope='Eligible stock trainer reconnaissance only; no qualification.')
    return old,actors.session_entry(t.fixture)['session']


def recon(t,preparation,source):
    old,session=baseline(t,preparation);entry_source(t,source,session,preparation)
    t.clean_panels();t.execute({'kind':'chat','value':'/targetexact Maximillian Crowe'})
    state,frame=t.observe('trainer_staged')
    if state.get('target',{}).get('name')!='Maximillian Crowe' or not state['target'].get('visible'):
        raise RuntimeError('existing owned trainer target absent')
    t.receipt.update(state=state,frame=frame,native_session=session,
        entry_source={'path':str(source.resolve()),'sha256':lab.sha256(source)},
        protected_checks=protected(old),phase='control_trainer_staged',completed=True)


def open_trainer(t,preparation,source,review_path):
    old,session=baseline(t,preparation);source=source.resolve();e=json.loads(source.read_text())
    if (e.get('completed') is not True or e.get('failure') or not e.get('finished_at') or
        e.get('phase')!='control_trainer_staged' or e.get('actor')!=t.fixture or
        e.get('runtime')!=t.receipt['runtime'] or e.get('native_session')!=session):
        raise RuntimeError('closed same-entry trainer staging differs')
    d=reviewed(t,review_path,'Maximillian Crowe')
    if d['frame']['sha256']!=e['frame']['sha256']:raise RuntimeError('reviewed trainer image differs')
    state,_=t.observe('trainer_before_interaction')
    if state.get('target',{}).get('guid')!=e['state']['target']['guid']:
        raise RuntimeError('current trainer target identity differs')
    t.receipt.update(staging_source={'path':str(source),'sha256':lab.sha256(source)},native_session=session)
    def opened(b,a,s):
        return {'status':'trainer_open_pass' if s=='interact' and any(x in a['panels'] for x in
            ['GossipFrame','ClassTrainerFrame']) else 'client_or_protocol_failure','oracle':{'panels':a['panels']}}
    require(t.step('control.trainer_interact','Speak to the reviewed nearby warlock trainer.',
        {'interact':{'kind':'click','value':d['point'],'button':3,'hold':.4,
            'description':'Right-click the reviewed visible Maximillian Crowe.'}},opened,
        diagnostic_action='interact'),'trainer_open_pass')
    state,_=t.observe('trainer_response')
    if 'GossipFrame' in state['panels']:
        require(click_case(t,'control.trainer_gossip','Open the normal class trainer service.',
            lambda c:'train' in c['text'].lower(),lambda b,a,s:{'status':'trainer_service_pass' if s and
                'ClassTrainerFrame' in a['panels'] else 'client_or_protocol_failure'}),'trainer_service_pass')
    state,frame=t.observe('trainer_open')
    if 'ClassTrainerFrame' not in state['panels']:raise RuntimeError('stock class trainer absent')
    native=catalog(session,t.receipt['started_at']);oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.receipt.update(state=state,frame=frame,trainer_controls=controls(t),native_catalog=native,
        resources=resources(oracle),saved_spells=known(t.fixture['guid']),protected_checks=protected(old),
        phase='control_trainer_open',completed=True)
    if not all(t.receipt['protected_checks'].values()):raise RuntimeError('protected original fixtures differ')


def prior(t,source,session,phase):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned trainer receipt')
    e=json.loads(source.read_text())
    if (e.get('completed') is not True or e.get('failure') or not e.get('finished_at') or
        e.get('phase')!=phase or e.get('actor')!=t.fixture or e.get('runtime')!=t.receipt['runtime'] or
        e.get('native_session')!=session or not all(e.get('protected_checks',{}).values())):
        raise RuntimeError('closed same-entry trainer source differs')
    t.receipt['trainer_source']={'path':str(source),'sha256':lab.sha256(source)};return e


def select(t,preparation,source):
    old,session=baseline(t,preparation);e=prior(t,source,session,'control_trainer_open')
    rows=[r for r in e['native_catalog']['rows'] if r[0]==80388]
    if len(rows)!=1 or rows[0][1]!=1:raise RuntimeError('native Control Demon lesson unavailable')
    state,_=t.observe('trainer_selection_before')
    if 'ClassTrainerFrame' not in state['panels']:raise RuntimeError('stock trainer no longer open')
    for header in ['Affliction','Demonology','Destruction']:
        current=[c for c in controls(t) if re.fullmatch(r'ClassTrainerSkill\d+',c['name'])]
        if any(c['text'].strip()=='Control Demon' for c in current):break
        index=next((i for i,c in enumerate(current) if c['text'].strip()==header),None)
        # A collapsed header is followed by another unindented header. Never
        # toggle it back open while revealing the General lesson below.
        if index is not None and index+1<len(current) and current[index+1]['text'].startswith('  '):
            require(click_case(t,'control.collapse_'+header.lower(),'Collapse the observed '+header+' trainer header.',
                lambda c:c['name'].startswith('ClassTrainerSkill') and c['text'].strip()==header,
                lambda b,a,s:{'status':'trainer_header_pass' if s and 'ClassTrainerFrame' in a['panels'] else
                    'client_or_protocol_failure'}),'trainer_header_pass')
    def selected(b,a,s):
        service=a.get('trainer',{}).get('service',{})
        checks={'ordinary_select':bool(s),'name':service.get('name')=='Control Demon',
            'available':service.get('state')=='available','cost':service.get('cost')==rows[0][2],
            'native_level_requirement':service.get('level')==rows[0][3],
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'control_lesson_selected_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native':rows[0],'public':service}}
    require(click_case(t,'control.select_lesson','Select the observed available Control Demon lesson.',
        lambda c:c['name'].startswith('ClassTrainerSkill') and c['text'].strip()=='Control Demon',
        selected),'control_lesson_selected_pass')
    state,frame=t.observe('control_selected');oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.receipt.update(state=state,frame=frame,native_lesson=rows[0],native_trainer_guid=e['native_catalog']['guid'],native_session=session,
        resources=resources(oracle),saved_spells=known(t.fixture['guid']),protected_checks=protected(old),
        phase='control_lesson_selected',completed=True)


def learn(t,preparation,source):
    old,session=baseline(t,preparation);e=prior(t,source,session,'control_lesson_selected')
    packets=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in packets.poll():pass
    oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll();before=resources(oracle)
    state,_=t.observe('control_purchase_before');service=state.get('trainer',{}).get('service',{})
    price=e['native_lesson'][2]
    if (before!=e['resources'] or known(t.fixture['guid'])!=e['saved_spells'] or
        any(r[0]==93375 for r in e['saved_spells']) or service.get('name')!='Control Demon' or
        service.get('state')!='available' or service.get('cost')!=price or not 0<price<before['money']):
        raise RuntimeError('selected untrained native lesson or resources differ')
    started=time.time();t.receipt.update(native_session=session,before=before,native_lesson=e['native_lesson'],
        purchase_started_at=started,retained_change='Normally purchased Control Demon and its exact native copper charge.')
    def learned(b,a,s):
        lab.server_command('saveall');time.sleep(1);oracle.poll();after=resources(oracle)
        rows=[r for r in packets.poll() if r.get('session')==session and r.get('time',0)>=started]
        safe={'CMSG_TRAINER_BUY_SPELL','SMSG_TRAINER_BUY_SUCCEEDED','SMSG_TRAINER_BUY_FAILED',
            'SMSG_LEARNED_SPELL','SMSG_LEARNED_SPELLS','SMSG_PET_SPELLS','SMSG_PET_SPELLS_MESSAGE'}
        rows=[r for r in rows if r.get('name') in safe]
        native=[r for r in rows if r.get('direction')=='from_native' and r['name']=='SMSG_LEARNED_SPELL'
            and Reader(bytes.fromhex(r['body'])).unpack('II')==(93375,0)]
        modern=[r for r in rows if r.get('direction')=='to_client' and r['name']=='SMSG_LEARNED_SPELLS'
            and r['body']=='010000000000000000bf6c010000']
        commands=[r for r in rows if r.get('direction')=='to_native' and r['name']=='CMSG_TRAINER_BUY_SPELL'
            and Reader(bytes.fromhex(r['body'])).unpack('QII')==(e['native_trainer_guid'],154,80388)]
        expected={**before,'money':before['money']-price}
        relation=learn_relation()
        checks={'ordinary_train':bool(s),'one_native_purchase':len(commands)==1,'native_learned':len(native)==1,
            'modern_learned':len(modern)==1,'saved_control_parent':persisted_training(
                e['saved_spells'],known(t.fixture['guid']),relation),
            'exact_charge_inventory':after==expected,'protected_originals':all(protected(old).values()),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        t.receipt.update(purchase_packets=rows,purchase_checks=checks,after=after,native_learn_relation=relation,
            protected_checks=protected(old));t.persist()
        return {'status':'control_training_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'price':price,'before':before['money'],'after':after['money']}}
    require(click_case(t,'control.train','Purchase the selected native Control Demon lesson once.',
        lambda c:c['name']=='ClassTrainerTrainButton',learned),'control_training_pass')
    t.clean_panels();state,frame=t.observe('control_training_closed')
    t.receipt.update(state=state,frame=frame,phase='control_demon_trained',completed=True,
        qualified_scope='Normal Control Demon purchase on an explicit native level10 test fixture. '
            'Native and modern learned93375 plus exact copper spend and inventory agreement; pet catalog/commands remain open.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['recon','open','select','learn'])
    for name in ['preparation','source','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--review',type=Path);a=p.parse_args()
    if a.action=='open' and not a.review:p.error('requires a fresh visual review of the trainer')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='recon':recon(t,a.preparation,a.source)
            elif a.action=='open':open_trainer(t,a.preparation,a.source,a.review)
            elif a.action=='select':select(t,a.preparation,a.source)
            else:learn(t,a.preparation,a.source)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}))
