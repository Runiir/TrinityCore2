"""Enter the unchanged owned primary from a freshly reviewed offline screen."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_offline_bridge_deploy import review,snapshot
from .interaction_owned_class_fixture import character,saved,pets,SCRIPT_BOUNDARY
from .interaction_ground_movement import position
from .observation.journal import Cursor


def inventory(guid):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT ci.*,ii.* FROM client442_characters.character_inventory ci '
            'JOIN client442_characters.item_instance ii ON ii.guid=ci.item '
            'WHERE ci.guid=%s ORDER BY ci.bag,ci.slot',(guid,))
        return json.loads(json.dumps(q.fetchall()))


def retained(guid,account):
    return {'native':character(guid,account),'saved':saved(guid),'pets':pets(guid),'inventory':inventory(guid)}


def protected_snapshot():
    return {str(g):retained(g,a) for g,a in ((2,2),(3,2),(4,2),(5,2),(6,2))}


def source(t,review_path):
    d,e=review(t,review_path,'Enter World')
    if (t.fixture['actor'],t.fixture['guid'],t.fixture['character_name'],t.fixture['level'])!=('primary',1,'Harnessone',85):
        raise RuntimeError('requires the exact original owned primary')
    if (d.get('selected_character'),d.get('selected_level'))!=('Harnessone',85):
        raise RuntimeError('reviewed primary selection differs')
    if d.get('point')!=[640,660] or e.get('parked_snapshot')!=snapshot(t):
        raise RuntimeError('reviewed stock entry control or complete offline state changed')
    return e


def run(t,review_path):
    e=source(t,review_path);before=e['parked_snapshot'];others=protected_snapshot()
    t.receipt.update(offline_source=before,protected_baseline=others,qualification_added=False)
    t.persist();cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in cursor.poll():pass
    since=time.time();t.io.click(640,660,hold=1.2);time.sleep(8)
    state,frame=t.observe('primary_reentered',seconds=60)
    session=actors.session_entry(t.fixture)['session']
    packets=[{k:p[k] for k in ('time','name','direction')} for p in cursor.poll()
        if p.get('session')==session and p.get('time',0)>=since and
        p.get('name') in ('CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD')]
    checks={'owned_name':state['player']=='Harnessone','owned_guid':state['guid']==t.guid,
        'level':state['level']==85,'native_online':character(1,t.fixture['account_id'])['online']==1,
        'saved_rows':saved(1)==before['saved'],'retained_pets':pets(1)==before['pets'],
        'inventory':inventory(1)==before['inventory'],
        'money':character(1,t.fixture['account_id'])['money']==before['native']['money'],
        'saved_user_pose':position(1)==[before['native'][k] for k in
            ('position_x','position_y','position_z','orientation','map')],
        'public_planar_pose':math.dist(state['world_position'][:2],position(1)[:2])<.2,
        'ordinary_login':any(p['name']=='CMSG_PLAYER_LOGIN' and p['direction']=='from_client' for p in packets),
        'native_login':any(p['name']=='SMSG_LOGIN_VERIFY_WORLD' and p['direction']=='from_native' for p in packets),
        'protected_actors':protected_snapshot()==others,
        'idle_primary':not state['owner_melee']['active'] and not frame['movement']['in_combat'],
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(reentry_checks=checks,packets=packets,session=session,frame=frame,state=state,
        phase='owned_primary_combat_preparation',
        qualified_scope='Ordinary primary reentry for combat diagnosis only; no new interaction qualification.')
    t.persist()
    if not all(checks.values()):raise RuntimeError('fresh primary reentry preservation differs')
    t.receipt['completed']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.review)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','reentry_checks')}),flush=True)
