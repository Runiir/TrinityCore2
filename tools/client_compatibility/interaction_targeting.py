"""Ordinary owned-party targeting, local focus and unit-frame hover checks."""
import argparse,struct,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import binding_key
from .interaction_ground_movement import suite
from .interaction_actionbar_pages import detail
from .interaction_operations import point
from .interaction_macros import require
from .interaction_tooltips import tooltip
from .observation.journal import entries


def selection(oracle):
    return oracle.poll().pair(oracle.guid,'UNIT_FIELD_TARGET')


def target(t,oracle,session,case,action,wanted):
    since=time.time()
    def outcome(before,after,selected):
        rows=[{k:p[k] for k in ['time','name','direction','body']} for p in
            entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('time',0)>=since and
            p.get('session')==session and p.get('name')=='CMSG_SET_SELECTION']
        expected=f'Player-1-{wanted:08X}' if wanted else ''
        checks={'ordinary_input':selected=='target',
            'public_target':(after.get('target',{}).get('guid') or '')==expected,
            'native_target':selection(oracle)==wanted,
            'native_request':any(p['direction']=='to_native' and p['body']==struct.pack('<Q',wanted).hex() for p in rows),
            'modern_request':any(p['direction']=='from_client' for p in rows),
            'position':before['world_position']==after['world_position'],
            'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
        return {'status':'native_owned_target_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native_target':selection(oracle),'requests':rows,'expected':expected}}
    require(t.step(case,'Select the attributed owned target through ordinary input.',
        {'target':dict(action,description='Use the observed stock targeting control or command.')},
        outcome,diagnostic_action='target',
        await_state=lambda s:(s.get('target',{}).get('guid') or '')==(f'Player-1-{wanted:08X}' if wanted else '')),
        'native_owned_target_pass')


def focus(t,oracle,wanted,label):
    value='/focus' if wanted else '/clearfocus'
    expected=f'Player-1-{wanted:08X}' if wanted else ''
    current=selection(oracle)
    def outcome(before,after,selected):
        probe=detail(t,label+'_focus',lambda p:p['targeting']['units']['focus']==expected)['targeting']
        checks={'ordinary_command':selected=='focus','public_focus':probe['units']['focus']==expected,
            'target_preserved':after.get('target',{}).get('guid')==before.get('target',{}).get('guid'),
            'native_selection_preserved':selection(oracle)==current,
            'position':after['world_position']==before['world_position'],
            'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
        return {'status':'local_focus_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'expected_focus':expected,'native_selection':current,'public':probe,
                'scope':'Client-local focus UI; no server focus field or packet acceptance claim.'}}
    require(t.step(label,'Change the stock client focus using its ordinary slash command.',
        {'focus':{'kind':'chat','value':value,'description':'Send '+value+' through the ordinary chat box.'}},
        outcome,diagnostic_action='focus'),
        'local_focus_pass')


def hover(t,oracle,peer,frame):
    current=selection(oracle)
    def outcome(before,after,selected):
        units=detail(t,'party_mouseover',lambda p:p['targeting']['units']['mouseover']==peer.guid)['targeting']['units']
        probe=tooltip(t,'party_target_tooltip')
        lines=[r.get('left','') for r in probe.get('lines') or []]
        checks={'ordinary_hover':selected=='hover',
            'owned_mouseover':units['mouseover']==peer.guid,
            'stock_tooltip_visible':probe.get('visible') is True,
            'owned_character_title':bool(lines) and lines[0]==peer.fixture['character_name'],
            'selection_preserved':selection(oracle)==current,
            'position':before['world_position']==after['world_position'],
            'ui_clean':not after.get('lua_errors') and not after.get('blocked_actions')}
        return {'status':'owned_unit_hover_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':probe,'frame':frame}}
    require(t.step('targeting.mouseover_tooltip','Hover the stock owned party-member frame.',
        {'hover':{'kind':'hover','value':point(frame),'description':'Hover the observed party1 unit frame.'}},
        outcome,diagnostic_action='hover'),'owned_unit_hover_pass')
    t.execute({'kind':'hover','value':[1000,360]})


def phase(t,peer,oracle,session,peer_session):
    before,_=t.observe('targeting_phase');bar=detail(t,'targeting_bindings')
    observed=bar.get('targeting',{})
    if before.get('observer_version',0)<77 or observed.get('units',{}).get('focus'):
        raise RuntimeError('requires observer77 and an empty original focus')
    keys={name:bar['keys'].get(name) for name in ['TARGETSELF','TARGETPARTYMEMBER1']}
    frames=[f for f in observed.get('party_frames',[]) if f['unit']=='party1']
    if not all(keys.values()) or len(frames)!=1 or observed['units'].get('party1')!=peer.guid:
        raise RuntimeError('requires unambiguous observed owned-party frames and targeting bindings')
    self_action={'kind':'key','value':binding_key(keys['TARGETSELF'][0]),'hold':.4}
    party_action={'kind':'key','value':binding_key(keys['TARGETPARTYMEMBER1'][0]),'hold':.4}
    t.receipt.update(targeting_fixture={'keys':keys,'party_frame':frames[0],'peer_guid':peer.guid},
        qualified_scope='Owned idle party targeting via stock self/party bindings, clear/last-target commands, party-frame click, local focus and hover. Native selection fields/requests prove target changes. Focus and hover are client-local outcomes. Original empty focus, target, party, positions and native resources restore.');t.persist()
    try:
        target(t,oracle,session,'targeting.target_self',self_action,t.fixture['guid'])
        target(t,oracle,session,'targeting.clear_target',{'kind':'chat','value':'/cleartarget'},0)
        target(t,oracle,session,'targeting.party_target',party_action,peer.fixture['guid'])
        target(t,oracle,session,'fixture.target_self_before_click',self_action,t.fixture['guid'])
        target(t,oracle,session,'targeting.click_target',{'kind':'click','value':point(frames[0])},peer.fixture['guid'])
        target(t,oracle,session,'targeting.target_last',{'kind':'chat','value':'/targetlasttarget'},t.fixture['guid'])
        target(t,oracle,session,'fixture.target_peer_for_focus',party_action,peer.fixture['guid'])
        focus(t,oracle,peer.fixture['guid'],'targeting.focus')
        focus(t,oracle,0,'targeting.clear_focus')
        hover(t,oracle,peer,frames[0])
    finally:
        probe=detail(t,'targeting_cleanup')['targeting']
        if probe['units']['focus']:focus(t,oracle,0,'fixture.clear_focus')
        t.execute({'kind':'hover','value':[1000,360]})
        t.receipt['focus_restored']=not detail(t,'focus_restored')['targeting']['units']['focus'];t.persist()
        if not t.receipt['focus_restored']:raise RuntimeError('original empty focus did not restore')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output,work=phase,separated=True)
