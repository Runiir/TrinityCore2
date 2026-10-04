"""Preserve native character state across an owned packet-bridge reconnect."""
import time
from . import actors,lab_runtime as lab
from .observation.inventory import Inventory
from .interaction_trial import binding_key
from .interaction_actionbar_pages import detail
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .interaction_ground_movement import position


def oracle(t):
    session=actors.session_entry(t.fixture)['session']
    return Inventory(lab.ROOT,session,t.fixture['guid']).poll()


def capture(t):
    native=oracle(t)
    return {'resources':resources(native),'stats':native_state(native),'spells':known(t.fixture['guid']),
        'actions':saved_actions(t.fixture['guid']),'pose':pose(native),'afk':afk(native),
        'position':position(t.fixture['guid'])}


def restore(t,baseline):
    native=oracle(t)
    if afk(native)!=baseline['afk']:t.execute({'kind':'chat','value':'/afk'})
    current=pose(native)
    if current['stand']!=baseline['pose']['stand']:
        if {current['stand'],baseline['pose']['stand']}!={0,1} or current['sheath']!=baseline['pose']['sheath']:
            raise RuntimeError('bridge reconnect left an unsupported pose difference')
        bar=detail(t,'bridge_pose_binding')
        t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':.4})
        time.sleep(12)
    state,frame=t.observe('bridge_native_restored')
    checks={'resources':resources(native)==baseline['resources'],
        'stats':restored_native_state(baseline['stats'],native_state(native)),
        'spells':known(t.fixture['guid'])==baseline['spells'],
        'actions':saved_actions(t.fixture['guid'])==baseline['actions'],
        'pose':pose(native)==baseline['pose'],'afk':afk(native)==baseline['afk'],
        'position':position(t.fixture['guid'])==baseline['position'],
        'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions')}
    t.receipt['bridge_native_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('native character state differs after bridge reconnect')

