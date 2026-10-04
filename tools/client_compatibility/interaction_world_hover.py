"""Hover a visually reviewed owned world character with an exact GUID oracle."""
import argparse,json,select,sys,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_ground_movement import suite
from .interaction_social import actor
from .interaction_targeting import selection
from .interaction_sit_stand import pose,afk
from .interaction_trial import binding_key
from .interaction_actionbar_pages import detail
from .interaction_tooltips import tooltip
from .interaction_macros import require


def phase(t,peer,oracle,session,peer_session):
    from .observation.inventory import Inventory
    with actor(peer.fixture['actor']):
        other=Inventory(lab.ROOT,peer_session,peer.fixture['guid']).poll()
        if afk(other):peer.execute({'kind':'chat','value':'/afk'})
        if pose(other)['stand']==1:
            peer.execute({'kind':'key','value':binding_key(peer.ground_bar['keys']['SITORSTAND'][0]),'hold':.4})
    time.sleep(3)
    before,frame=t.observe('world_hover_scene')
    print(json.dumps({'review_required':True,'actor':t.fixture['actor'],
        'scene':str(t.out/frame['file']),'sha256':frame['sha256'],'expected_peer':peer.guid}),flush=True)
    if not select.select([sys.stdin],[],[],60)[0]:
        raise RuntimeError('reviewed world hover point was not supplied within60seconds')
    choice=json.loads(sys.stdin.readline());point=choice.get('point')
    if (choice.get('scene_sha256')!=frame['sha256'] or not isinstance(point,list) or len(point)!=2 or
            not all(isinstance(v,int) for v in point) or not 0<=point[0]<1280 or not 0<=point[1]<720):
        raise RuntimeError('hover choice does not bind the reviewed owned scene')
    t.receipt['world_hover_choice']={'scene':frame,'point':point,'source':'visual_review','qualification':False};t.persist()
    current=selection(oracle)
    def outcome(b,a,s):
        units=detail(t,'world_mouseover',lambda p:p['targeting']['units']['mouseover']==peer.guid)['targeting']['units']
        probe=tooltip(t,'world_peer_tooltip');lines=probe.get('lines') or []
        checks={'ordinary_hover':s=='hover','owned_mouseover':units['mouseover']==peer.guid,
            'stock_tooltip_visible':probe.get('visible') is True,
            'owned_character_title':bool(lines) and lines[0].get('left')==peer.fixture['character_name'],
            'native_selection_preserved':selection(oracle)==current,
            'position':a['world_position']==b['world_position'],
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'owned_world_hover_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':probe,'mouseover':units['mouseover'],'expected':peer.guid}}
    try:
        require(t.step('targeting.mouseover_tooltip','Hover the reviewed nearby owned world character.',
            {'hover':{'kind':'hover','value':point}},outcome,diagnostic_action='hover'),'owned_world_hover_pass')
    finally:t.execute({'kind':'hover','value':[1000,360]})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output,work=phase,separated=True)
