"""Inspect the eligible stock warlock trainer before a native-bound purchase."""
import argparse,json,time
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
from .observation.journal import entries
from .world.buffer import Reader


def protected(old):
    r=old['retained_level_one'];checks=origin_checks(old)
    checks.update(retained_level_one_character=character(4,2)==r['character'],
        retained_level_one_saved=saved(4)==r['saved'],retained_level_one_pets=pets(4)==r['pets'])
    return checks


def catalog(session,since):
    found=None
    for p in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if (p.get('session')!=session or p.get('time',0)<since or p.get('direction')!='from_native' or
            p.get('name')!='SMSG_TRAINER_LIST'):continue
        r=Reader(bytes.fromhex(p['body']));guid,kind,trainer,count=r.unpack('QIII')
        if (guid>>32)&0xfffff!=906 or trainer!=154:continue
        if count>4096:raise RuntimeError('trainer count exceeds native bound')
        rows=[r.unpack('IBIBII2iII') for _ in range(count)]
        found={'packet':p,'guid':guid,'trainer':trainer,'kind':kind,'rows':[list(x) for x in rows]}
    if found is None:raise RuntimeError('owned native warlock trainer catalog absent')
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


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['recon','open'])
    for name in ['preparation','source','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--review',type=Path);a=p.parse_args()
    if a.action=='open' and not a.review:p.error('requires a fresh visual review of the trainer')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='recon':recon(t,a.preparation,a.source)
            else:open_trainer(t,a.preparation,a.source,a.review)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}))
