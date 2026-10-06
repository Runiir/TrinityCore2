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


def capture(t,state=None):
    native=oracle(t)
    if state is None:state,_=t.observe('bridge_selection_baseline')
    return {'resources':resources(native),'stats':native_state(native),'spells':known(t.fixture['guid']),
        'actions':saved_actions(t.fixture['guid']),'pose':pose(native),'afk':afk(native),
        'position':position(t.fixture['guid']),
        'selection':{'native_guid':native.pair(t.fixture['guid'],'UNIT_FIELD_TARGET'),
            'public':{k:state.get('target',{}).get(k) for k in ('exists','guid','name')}}}


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
    if 'selection' in baseline:
        wanted=baseline['selection'];now=state.get('target',{});selected_again=False
        # A bridge reconnect can clear selection. Restore that exact prior name
        # only when both native and public selection are empty; retain new input.
        if wanted['native_guid'] and native.poll().pair(t.fixture['guid'],'UNIT_FIELD_TARGET')==0 and now.get('exists') is False:
            name=wanted['public'].get('name')
            if not isinstance(name,str) or not name or len(name)>128 or any(c in name for c in '\r\n'):
                raise RuntimeError('prior selected target has no safe ordinary target name')
            t.execute({'kind':'chat','value':'/targetexact '+name});selected_again=True
            state,frame=t.observe('bridge_selection_restored');now=state.get('target',{})
        selection_checks={'native':native.poll().pair(t.fixture['guid'],'UNIT_FIELD_TARGET')==wanted['native_guid'],
            'public':all(now.get(k)==v for k,v in wanted['public'].items())}
        t.receipt['bridge_selection_restoration']={'checks':selection_checks,'ordinary_selection_input':selected_again,
            'baseline':wanted,'frame':frame};t.persist()
        if not all(selection_checks.values()):raise RuntimeError('selected target differs after bridge reconnect; preserve current user input')
    checks={'resources':resources(native)==baseline['resources'],
        'stats':restored_native_state(baseline['stats'],native_state(native)),
        'spells':known(t.fixture['guid'])==baseline['spells'],
        'actions':saved_actions(t.fixture['guid'])==baseline['actions'],
        'pose':pose(native)==baseline['pose'],'afk':afk(native)==baseline['afk'],
        'position':position(t.fixture['guid'])==baseline['position'],
        'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions')}
    t.receipt['bridge_native_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('native character state differs after bridge reconnect')
