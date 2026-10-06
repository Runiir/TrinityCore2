"""Preserve one native-paid training purchase after a captured pet-mode disconnect."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,character,saved,pets,SCRIPT_BOUNDARY
from .interaction_pet_control_training import protected,persisted_training,learn_relation
from .interaction_pet_target import PetOracle,pair
from .interaction_bridge_deploy import shot
from .observation.journal import entries,player_entry
from .world.buffer import Reader
from .world.objects import INDEX


def catalog(body):
    r=Reader(bytes.fromhex(body))
    guid,family,duration,react,command,flags=r.unpack('QHIBBH')
    buttons=list(r.unpack('10I'));count=r.unpack('B')[0]
    actions=list(r.unpack('I'*count));count=r.unpack('B')[0]
    cooldowns=[list(r.unpack('IHII')) for _ in range(count)];r.end()
    return dict(guid=guid,family=family,duration=duration,react=react,command=command,
        flags=flags,buttons=buttons,actions=actions,cooldowns=cooldowns)


def proof(failed,selected,packets,events):
    session=failed['native_session'];start=failed['purchase_started_at'];end=failed['finished_at']
    packets=[p for p in packets if p.get('session')==session and start<=p.get('time',0)<=end]
    def one(direction,name):
        rows=[p for p in packets if p.get('direction')==direction and p.get('name')==name]
        if len(rows)!=1:raise RuntimeError('training proof requires one '+direction+' '+name)
        return rows[0]
    client=one('from_client','CMSG_TRAINER_BUY_SPELL')
    purchase=one('to_native','CMSG_TRAINER_BUY_SPELL')
    r=Reader(bytes.fromhex(purchase['body']));identity=r.unpack('QII');r.end()
    if identity!=(selected['native_trainer_guid'],154,80388):
        raise RuntimeError('owned native purchase identity differs')
    native=one('from_native','SMSG_LEARNED_SPELL');modern=one('to_client','SMSG_LEARNED_SPELLS')
    if (native['body']!='bf6c010000000000' or modern['body']!='010000000000000000bf6c010000'):
        raise RuntimeError('native and public dependent learned spell differ')
    pet=one('from_native','SMSG_PET_SPELLS');decoded=catalog(pet['body'])
    closed=[e for e in events if e.get('session')==session and e.get('event')=='native_stream_closed' and
        start<=e.get('time',0)<=end and e.get('error')=='unsupported native pet mode']
    if (len(closed)!=1 or decoded['guid']>>52!=0xf14 or decoded['react']!=3 or decoded['command']!=1 or
        not client['time']<=purchase['time']<=native['time']<=modern['time']<=pet['time']<=closed[0]['time'] or
        closed[0]['time']-pet['time']>1):
        raise RuntimeError('paid training pet-mode failure is not attributable')
    if any(p.get('name')=='SMSG_PET_SPELLS_MESSAGE' for p in packets):
        raise RuntimeError('pet catalog unexpectedly reached the client')
    return {'purchase':purchase,'client_purchase':client,'native_learned':native,'modern_learned':modern,
        'native_pet_spells':pet,'catalog':decoded,'native_closed':closed[0]}


def recover(t,preparation,failed_path):
    old=prepared(t,preparation);failed_path=failed_path.resolve()
    if failed_path.name!='episode.json' or not failed_path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a private owned failed training receipt')
    failed=json.loads(failed_path.read_text())
    if (t.fixture.get('guid')!=5 or failed.get('completed') is not False or not failed.get('finished_at') or
        failed.get('failure')!='RuntimeError: RuntimeError: UI observation did not become decodable' or
        failed.get('actor')!=t.fixture or failed.get('runtime')!=t.receipt['runtime'] or
        failed.get('fixture_source',{}).get('sha256')!=lab.sha256(preparation) or
        not failed.get('purchase_started_at') or len(failed.get('cases',[]))!=1 or
        failed['cases'][0].get('id')!='control.train' or
        failed['cases'][0].get('status')!='infrastructure_failure'):
        raise RuntimeError('closed paid-training failure differs')
    path=Path(failed['trainer_source']['path']).resolve();selected=json.loads(path.read_text())
    if (lab.sha256(path)!=failed['trainer_source']['sha256'] or not selected.get('completed') or not selected.get('finished_at') or
        selected.get('failure') or selected.get('actor')!=t.fixture or selected.get('runtime')!=t.receipt['runtime'] or
        selected.get('phase')!='control_lesson_selected' or selected.get('native_session')!=failed['native_session']):
        raise RuntimeError('closed selected lesson source differs')
    p=proof(failed,selected,entries(lab.ROOT/'evidence/world_packets.jsonl'),
        entries(lab.ROOT/'logs/modern_world.jsonl'))
    entry=player_entry(lab.ROOT,t.fixture['guid'],failed['native_session'])
    pet=PetOracle(failed['native_session'],5,entry['time']).poll()
    native=pet.pet;fields=native['fields'] if native else {}
    if (not native or native['guid']!=p['catalog']['guid'] or pair(fields,'UNIT_FIELD_SUMMONEDBY')!=5 or
        pair(pet.player,'UNIT_FIELD_SUMMON')!=native['guid'] or fields.get(INDEX['UNIT_FIELD_PETNUMBER'])!=2):
        raise RuntimeError('captured pet catalog ownership links differ')
    row=character(5,2);current_saved=saved(5);current_pets=pets(5)
    relation=learn_relation()
    expected_saved={**old['natural_saved'],'spells':current_saved['spells']}
    checks=protected(old)
    keys=lambda rows:sorted((r['id'],r['entry'],r['owner'],r['name']) for r in rows)
    checks.update(class_offline=row['online']==0,exact_charge=row['money']==failed['before']['money']-selected['native_lesson'][2],
        parent_spell_persisted=current_saved==expected_saved and persisted_training(
            old['natural_saved']['spells'],current_saved['spells'],relation),
        dependent_native_relation=relation==[[80388,93375,1]],
        retained_pet_identity=keys(current_pets)==keys(old['retained_class_pets']))
    t.receipt.update(failed_training_source={'path':str(failed_path),'sha256':lab.sha256(failed_path)},
        training_disconnect_proof=p,native_owned_pet=native,native_summon=pair(pet.player,'UNIT_FIELD_SUMMON'),
        native_learn_relation=relation,recovery_checks=checks,input_sent=False,
        retained_class_fixture=row,retained_class_saved=current_saved,retained_class_pets=current_pets,
        retained_change='Ordinary purchase of80388, native-dependent93375 and exact copper spend; whole trial failed.',
        qualified_scope='Read-only purchase/failure attribution and offline registration recovery. No gameplay qualification.')
    t.persist()
    if not all(checks.values()):raise RuntimeError('paid training state or protected originals differ')
    if actors.register(2)!=old['origin_actor']:raise RuntimeError('original actor registration differs')
    t.receipt.update(checks={k:checks[k] for k in ['original_character','original_saved_rows','native_worldserver','class_offline']},
        completed=True,phase='await_original_selection_review',frame=shot(t.out/'origin_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['preparation','failed-training','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:recover(t,a.preparation,a.failed_training)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}),flush=True)
