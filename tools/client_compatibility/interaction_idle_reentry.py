"""Reenter the owned scout from its separately reviewed character-selection screen."""
import argparse,json,time,hashlib
from pathlib import Path
from PIL import Image
from . import lab_runtime as lab,actors
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_lifecycle import Packets
from .interaction_spellbook_navigation import known


def run(t,source):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require the private failed scout observer preflight')
    old=json.loads(source.read_text())
    if (old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or old['completed'] or
        old.get('native_pose_before') or not old.get('finished_at') or
        old['failure']!='RuntimeError: UI observation did not become decodable' or
        t.fixture['guid']!=2):raise RuntimeError('exact scout preflight source differs')
    reviewed=source.parent/'cleanup_latest.png';frame=shot(t.out/'selection_before.png')
    # This text-only region of the reviewed selected row is stable despite lobby animation.
    crop=(1052,80,1169,114)
    digest=lambda p:hashlib.sha256(Image.open(p).crop(crop).tobytes()).hexdigest()
    if digest(reviewed)!=digest(t.out/frame['file']):raise RuntimeError('reviewed scout selection text differs')
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},selection_frame=frame,
        reviewed_selection={'file':str(reviewed),'sha256':lab.sha256(reviewed),'character':'Harnesstwo',
        'level':1,'input':[640,661],'text_crop':crop,'text_sha256':digest(reviewed)});t.persist()
    prior=actors.session_entry(t.fixture)['session'];started=time.time()
    t.execute({'kind':'click','value':[640,661]});time.sleep(8)
    state,frame=t.observe('scout_reentered',seconds=120);entry=actors.session_entry(t.fixture)
    packets=Packets(entry['session']);checks={'owned_guid':state['guid']==t.guid,
        'name':state['player']=='Harnesstwo','level':state['level']==1,'money':state['money']==0,
        'starter_mainhand':state['equipment'][15]==49778,'persisted_spells':known(2)==[],
        'solo':state['group']['members']==0,'no_lua_errors':not state.get('lua_errors'),
        'no_blocked_actions':not state.get('blocked_actions'),
        'ordinary_login':packets.has(started,'CMSG_PLAYER_LOGIN','from_client'),
        'native_login':packets.has(started,'SMSG_LOGIN_VERIFY_WORLD','from_native')}
    t.receipt.update(previous_session=prior,session=entry['session'],reentry_checks=checks,frame=frame);t.persist()
    if not all(checks.values()):raise RuntimeError('scout reentry fixture checks differ')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code')
        try:run(t,a.source);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
