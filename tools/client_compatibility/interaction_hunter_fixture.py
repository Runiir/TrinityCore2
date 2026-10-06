"""Prepare one owned Hunter on the existing scout without changing prior actors."""
import argparse,asyncio,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot,identity
from .interaction_parked_bridge import review
from .interaction_retained_class_fixture import closed
from .interaction_owned_class_fixture import character,saved,pets,origin_checks,SCRIPT_BOUNDARY
from .interaction_character_creator_probe import roster


NAME='Harnesshunt'


def inventory(guid):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT ci.*,ii.* FROM client442_characters.character_inventory ci '
            'JOIN client442_characters.item_instance ii ON ii.guid=ci.item '
            'WHERE ci.guid=%s ORDER BY ci.bag,ci.slot',(guid,))
        return json.loads(json.dumps(q.fetchall()))


def snapshots():
    return {str(g):{'native':character(g,1 if g==1 else 2),'saved':saved(g),
        'pets':pets(g),'inventory':inventory(g)} for g in (1,2,3,4,5)}


def protected(old):
    current=snapshots()
    return {f'actor_{g}_unchanged':current[g]==before for g,before in old['protected_baseline'].items()}


def preparation_contract(origin,current,park,primary,before):
    shared=lambda d:{k:d['runtime'][k] for k in ('worldserver','modern_world')}
    if (origin.get('actor')!={'schema':'client442_actor_v1','actor':'scout','guid':2,'account_id':2,
            'character_name':'Harnesstwo','race':1,'class':1,'level':1} or
        origin.get('runtime')!=current or
        not origin.get('qualified_scope','').startswith('Read-only owned offline scout preflight') or
        origin.get('parked_native')!=before['2']['native'] or
        park.get('actor',{}).get('guid')!=5 or park.get('phase')!='await_original_selection_review' or
        park.get('runtime')!=current or len(park.get('checks',{}))!=4 or not all(park['checks'].values()) or
        park.get('retained_class_fixture')!=before['5']['native'] or
        park.get('retained_class_saved')!=before['5']['saved'] or
        park.get('retained_class_pets')!=before['5']['pets'] or
        primary.get('actor',{}).get('guid')!=1 or shared(primary)!=shared(origin) or
        primary.get('parked_snapshot')!=before['1'] or
        any(row['native']['online']!=0 for row in before.values())):
        raise RuntimeError('closed original, retained or primary Hunter preparation boundary differs')


def trainer_contract():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
            'COALESCE(NULLIF(c.npcflag,0),t.npcflag),c.MovementType,ct.TrainerId '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id '
            'JOIN client442_world.creature_trainer ct ON ct.CreatureId=c.id '
            'WHERE c.guid=280678 AND c.id=46983 AND c.map=0');rows=q.fetchall()
        q.execute('SELECT SpellId,MoneyCost,ReqLevel FROM client442_world.trainer_spell '
            'WHERE TrainerId=40 AND SpellId=1515');spells=q.fetchall()
    expected=(280678,46983,'Benjamin Foxworthy',0,-9464.94,117.432,58.046,1.39626,49,0,40)
    if rows!=(expected,) or spells!=((1515,680,10),):raise RuntimeError('native Hunter trainer prerequisite differs')
    return list(rows[0]),list(spells[0])


def created_identity(fixture):
    return tuple(fixture.get(k) for k in ('actor','guid','account_id','character_name','race','class','level'))==(
        'scout',6,2,NAME,1,3,1)


def prepare(t,source,review_path,retained_path,primary_path):
    origin,park,primary=[closed(p) for p in (source,retained_path,primary_path)];before=snapshots()
    preparation_contract(origin,t.receipt['runtime'],park,primary,before)
    with actor('primary'):
        if identity('client')!=primary['runtime']['client']:raise RuntimeError('primary client lifetime differs')
    checked=review(t,review_path,source,'native_hunter_fixture')
    if checked['frame']!=origin['parked_frame']:raise RuntimeError('Hunter original selection review differs')
    npc,training=trainer_contract();previous=roster(t)
    if any(r[1]==NAME for r in previous):raise RuntimeError('Hunter already exists; inspect its actual preparation')
    x,y,z,o=npc[4:8];position=[x+3*math.cos(o),y+3*math.sin(o),z,(o+math.pi)%(2*math.pi),0]
    t.receipt.update(origin_actor=t.fixture,origin_native=before['2']['native'],origin_saved=before['2']['saved'],
        origin_roster=previous,protected_baseline=before,native_trainer=npc,training_contract=training,
        sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in (source,retained_path,primary_path)],
        preparation_review={'path':str(review_path),'sha256':lab.sha256(review_path),'frame':checked['frame']},
        preparation_contract={'name':NAME,'guid':6,'race':1,'class':3,'level':10,'money':10000,
            'position':position,'source':'Normal native-account creation, native offline level preparation and owned offline money/pose rows only.',
            'spell_pet_aura_grants':False,'extra_game_client':False},phase='native_hunter_creation_started',
        qualified_scope='Owned native-account Hunter prerequisite only; no modern creation, leveling, training or pet qualification.')
    t.persist();created=asyncio.run(asyncio.wait_for(actors.create_character(NAME,1,3),45))
    t.receipt['created_actor']=created;t.persist()
    if not created_identity(created):raise RuntimeError('created Hunter ownership or identity differs')
    lab.server_command('character level '+NAME+' 10');deadline=time.monotonic()+10
    while character(6,2)['level']!=10:
        if time.monotonic()>deadline:raise RuntimeError('native offline Hunter level update absent')
        time.sleep(.1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('UPDATE client442_characters.characters SET money=10000,position_x=%s,position_y=%s,'
            'position_z=%s,orientation=%s,map=%s WHERE guid=6 AND account=2 AND name=%s AND level=10 AND online=0',
            (*position,NAME))
        if q.rowcount!=1:raise RuntimeError('owned offline Hunter pose preparation rejected')
    fixture=actors.register(6);checks=origin_checks(t.receipt);checks.update(protected(t.receipt))
    checks.update(only_owned_hunter_added=roster(t)==previous+[[6,NAME,1,3,0,10,0]],
        untrained_tame=not any(r[0]==1515 for r in saved(6)['spells']))
    t.receipt.update(class_actor=fixture,natural_native=character(6,2),natural_saved=saved(6),
        natural_pets=pets(6),checks=checks,phase='await_owned_class_lobby_review',
        frame=shot(t.out/'owned_lobby.png'),requires_next_screen_review=True);t.persist()
    if not all(checks.values()):raise RuntimeError('Hunter preparation changed a protected actor or prerequisite')
    t.receipt['completed']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','review','retained','primary','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.source,a.review,a.retained,a.primary)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase')}),flush=True)
