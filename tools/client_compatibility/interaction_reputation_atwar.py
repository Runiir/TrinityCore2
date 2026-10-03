"""Toggle an eligible earned faction's At War checkbox and restore it exactly."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_reputation import open_panel,detail,catalog,native_state,native_catalog,standing_oracle,inspect_faction
from .interaction_reputation_navigation import set_header,restore_headers
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_trade import inventory
from .observation.journal import entries
from .world.buffer import Reader

FACTION=21


def expected_native(baseline,enabled):
    rows=[(id,value,flags|2 if enabled else flags&~2) if id==FACTION else (id,value,flags)
        for id,value,flags in baseline['rows']]
    return {**baseline,'rows':tuple(rows)}


def request_packets(session,started):
    result=[]
    for packet in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if packet.get('session')!=session or packet.get('time',0)<started:continue
        name,direction=packet.get('name'),packet.get('direction')
        if direction=='from_client' and name in ['CMSG_SET_FACTION_AT_WAR','CMSG_SET_FACTION_NOT_AT_WAR']:
            r=Reader(bytes.fromhex(packet['body']));index=r.unpack('H')[0];r.end()
            result.append({'direction':direction,'name':name,'time':packet['time'],'index':index,
                'enabled':name=='CMSG_SET_FACTION_AT_WAR'})
        elif direction=='to_native' and name=='CMSG_SET_FACTION_ATWAR':
            r=Reader(bytes.fromhex(packet['body']));index,enabled=r.unpack('iB');r.end()
            result.append({'direction':direction,'name':name,'time':packet['time'],'index':index,'enabled':bool(enabled)})
    return result


def toggle(t,enabled,label,baseline,session,faction):
    before=detail(t,'atwar_pre_'+label)
    selected=before.get('selected') or {}
    checkbox=next(r for r in before['controls'] if r['name']=='ReputationDetailAtWarCheckbox')
    if (selected.get('id')!=FACTION or not selected.get('can_toggle_at_war') or
            not checkbox['visible'] or not checkbox['enabled'] or checkbox['checked']==enabled):
        raise RuntimeError('requires the selected eligible Booty Bay checkbox in the opposite state')
    started=time.time()
    def outcome(b,a,s):
        probe=detail(t,'atwar_'+label);actual=native_state();expected=expected_native(baseline,enabled)
        chosen=probe.get('selected') or {};control=next(r for r in probe['controls'] if r['name']=='ReputationDetailAtWarCheckbox')
        packets=request_packets(session,started)
        matched=all(any(p['direction']==direction and p['index']==faction['index'] and p['enabled']==enabled
            for p in packets) for direction in ['from_client','to_native'])
        passed=bool(s and chosen.get('id')==FACTION and chosen.get('at_war')==enabled and
            control['checked']==enabled and actual==expected and matched)
        oracle={'public':probe,'native':actual,'expected_native':expected,'packets':packets,
            'native_public_requests_agree':matched,'passed':passed}
        t.receipt.setdefault('atwar_oracles',{})[label]=oracle;t.persist()
        return {'status':'reputation_atwar_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
    require(click_case(t,'reputation.at_war.'+label,('Enable' if enabled else 'Disable')+' At War with Booty Bay.',
        lambda c:c['name']=='ReputationDetailAtWarCheckbox',outcome),'reputation_atwar_pass')


def suite(t):
    session=actors.session_entry(t.fixture)['session'];t.clean_panels();baseline,items=native_state(),inventory()
    native=native_catalog(baseline);initial=bool(native[FACTION]['flags']&2);public=None
    t.receipt['baseline']={'native':baseline,'inventory_money':items};t.persist()
    try:
        open_panel(t);public=catalog(t,'atwar_baseline');standing_oracle(public,native)
        t.receipt['public_baseline']=public;t.persist()
        # The earned Steamwheedle factions follow Alliance. Fold its children
        # with a normal stock header click to reveal the Booty Bay row.
        revealed=set_header(t,'Alliance',True,'atwar_reveal')
        inspect_faction(t,revealed,native,FACTION,'reputation.at_war.select')
        toggle(t,not initial,'change',baseline,session,native[FACTION])
        toggle(t,initial,'restore',baseline,session,native[FACTION])
    finally:
        current=native_state()
        if bool(native_catalog(current)[FACTION]['flags']&2)!=initial:
            probe=catalog(t,'atwar_cleanup_select')
            inspect_faction(t,probe,native,FACTION,'reputation.at_war.cleanup_select')
            toggle(t,initial,'cleanup_restore',baseline,session,native[FACTION])
        if public:restore_headers(t,public,'atwar_restore')
        restored=catalog(t,'atwar_restored') if public else None
        t.clean_panels();checks={'native_reputation_restored':native_state()==baseline,
            'inventory_money_unchanged':inventory()==items,'public_catalog_restored':not public or restored['rows']==public['rows']}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('At War trial failed exact native/public restoration')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
