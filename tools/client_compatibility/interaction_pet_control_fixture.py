"""Prepare a separate eligible native test fixture without altering retained pets."""
import argparse,asyncio,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_bridge_deploy import shot
from .interaction_parked_bridge import native,review
from .interaction_character_creator_probe import roster
from .interaction_owned_class_fixture import character,saved,pets,origin_checks,SCRIPT_BOUNDARY


def prepare(t,source,review_path,retained_path):
    for p in [source,retained_path]:
        if p.name!='episode.json' or not p.resolve().is_relative_to(lab.ROOT/'evidence'):
            raise ValueError('requires closed owned fixture receipts')
    old=json.loads(source.read_text());retained=json.loads(retained_path.read_text())
    if (old.get('completed') is not True or old.get('failure') or not old.get('finished_at') or
        old.get('actor')!=t.fixture or old.get('runtime')!=t.receipt['runtime'] or
        not old.get('qualified_scope','').startswith('Read-only owned offline scout preflight') or
        native(t)!=old.get('parked_native') or retained.get('completed') is not True or
        retained.get('failure') or not retained.get('finished_at') or
        retained.get('phase')!='await_original_selection_review' or
        retained.get('runtime')!=t.receipt['runtime'] or retained.get('actor',{}).get('guid')!=4 or
        retained.get('retained_class_fixture')!=character(4,2) or
        retained.get('retained_class_saved')!=saved(4) or retained.get('retained_class_pets')!=pets(4)):
        raise RuntimeError('current original or retained level-one fixture differs')
    checked=review(t,review_path,source,'native_pet_control_fixture')
    if checked['frame']['sha256']!=old['parked_frame']['sha256']:
        raise RuntimeError('reviewed original selection differs')
    before=roster(t)
    if any(r[1]=='Harnessctrl' for r in before):
        raise RuntimeError('control fixture already exists; inspect its preparation')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
            'COALESCE(c.npcflag,t.npcflag),c.MovementType,ct.TrainerId FROM client442_world.creature c '
            'JOIN client442_world.creature_template t ON t.entry=c.id '
            'JOIN client442_world.creature_trainer ct ON ct.CreatureId=c.id WHERE c.id=906 AND c.map=0')
        npc=q.fetchall()
        q.execute('SELECT SpellId,MoneyCost,ReqLevel FROM client442_world.trainer_spell '
            'WHERE TrainerId=154 AND SpellId=80388');training=q.fetchall()
    if (len(npc)!=1 or npc[0][2]!='Maximillian Crowe' or npc[0][9]!=0 or not npc[0][8]&16 or
        npc[0][10]!=154 or training!=((80388,680,10),)):
        raise RuntimeError('eligible native trainer contract differs')
    npc=npc[0];x,y,z,o=npc[4:8]
    position=(x+3*math.cos(o),y+3*math.sin(o),z,math.atan2(-math.sin(o),-math.cos(o))%(2*math.pi),0)
    t.receipt.update(source={'path':str(source.resolve()),'sha256':lab.sha256(source)},
        retained_source={'path':str(retained_path.resolve()),'sha256':lab.sha256(retained_path)},
        preparation_review={'path':str(review_path.resolve()),'sha256':lab.sha256(review_path),'frame':checked['frame']},
        origin_actor=t.fixture,origin_native=old['parked_native'],origin_saved=saved(2),origin_roster=before,
        retained_level_one={'character':character(4,2),'saved':saved(4),'pets':pets(4)},
        native_trainer=list(npc),training_contract=list(training[0]),
        preparation_contract={'name':'Harnessctrl','race':1,'class':9,'level':10,'money':10000,
            'position':list(position),'level_source':'native console character level, offline fixture only',
            'money_position_source':'owned offline fixture rows only','spell_aura_grants':False,
            'qualification':'none; Control Demon must be purchased through normal stock trainer UI'},
        phase='native_pet_control_fixture_creation_started',
        qualified_scope='Native test-account preparation only; no modern creation, leveling, training or pet qualification.')
    t.persist()
    created=asyncio.run(asyncio.wait_for(actors.create_character('Harnessctrl',1,9),45))
    if (created['guid'] in [1,2,3,4] or created['account_id']!=2 or created['level']!=1):
        raise RuntimeError('created control fixture identity differs')
    t.receipt['created_actor']=created;t.persist()
    lab.server_command('character level Harnessctrl 10')
    deadline=time.monotonic()+10
    while character(created['guid'],2)['level']!=10:
        if time.monotonic()>deadline:raise RuntimeError('native fixture level update absent')
        time.sleep(.1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('UPDATE client442_characters.characters SET money=10000,position_x=%s,position_y=%s,'
            'position_z=%s,orientation=%s,map=%s WHERE guid=%s AND account=2 AND name=%s '
            'AND level=10 AND online=0',(*position,created['guid'],'Harnessctrl'))
        if q.rowcount!=1:raise RuntimeError('offline control fixture staging rejected')
    fixture=actors.register(created['guid']);checks=origin_checks(t.receipt)
    checks.update(only_owned_fixture_added=roster(t)==before+[[fixture['guid'],'Harnessctrl',1,9,0,10,0]],
        retained_level_one_character=character(4,2)==t.receipt['retained_level_one']['character'],
        retained_level_one_saved=saved(4)==t.receipt['retained_level_one']['saved'],
        retained_level_one_pets=pets(4)==t.receipt['retained_level_one']['pets'],
        untrained=not any(r[0] in [80388,93375] for r in saved(fixture['guid'])['spells']))
    t.receipt.update(class_actor=fixture,natural_native=character(fixture['guid'],2),
        natural_saved=saved(fixture['guid']),checks=checks,phase='await_owned_class_lobby_review',
        frame=shot(t.out/'owned_lobby.png'),requires_next_screen_review=True)
    t.persist()
    if not all(checks.values()):raise RuntimeError('eligible fixture preparation changed protected state')
    t.receipt['completed']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','review','retained','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.source,a.review,a.retained)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}))
