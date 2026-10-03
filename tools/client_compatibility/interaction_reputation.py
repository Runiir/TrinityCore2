"""Exercise ordinary reputation controls with public and native faction oracles."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,command
from .interaction_macros import require
from .interaction_observation import read_page
from .interaction_trade import inventory


def native_state():
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT race,class,watchedFaction FROM client442_characters.characters WHERE guid=1')
        character=q.fetchone()
        q.execute('SELECT faction,standing,flags FROM client442_characters.character_reputation WHERE guid=1 ORDER BY faction')
        rows=q.fetchall()
    return {'character':character,'rows':rows}


def native_catalog(state):
    data=(lab.ROOT/'data/dbc/enUS/Faction.dbc').read_bytes()
    magic,count,fields,width,strings=struct.unpack_from('<4s4I',data)
    if magic!=b'WDBC' or (fields,width)!=(26,104) or len(data)!=20+count*width+strings:
        raise RuntimeError('unexpected native faction DBC layout')
    text=data[20+count*width:];race,cls=state['character'][:2];race_mask,class_mask=1<<(race-1),1<<(cls-1)
    saved={row[0]:row[1:] for row in state['rows']};catalog={};by_index={}
    # ReputationMgr initializes by ascending faction ID and overwrites duplicate
    # reputation-list indexes. Superseded test/placeholder DBC IDs are not state.
    rows=sorted((struct.unpack_from('<26I',data,20+i*width) for i in range(count)),key=lambda row:row[0])
    for row in rows:
        if row[1]<256:by_index[row[1]]=row
    for row in by_index.values():
        base=0
        for j in range(4):
            value=struct.unpack('<i',struct.pack('<I',row[10+j]))[0]
            if ((row[2+j]&race_mask or row[2+j]==0 and row[6+j]!=0) and
                    (row[6+j]&class_mask or row[6+j]==0 and value!=0)):
                base=value;break
        if row[0] not in saved:raise RuntimeError('saveall omitted native faction state')
        offset,flags=saved[row[0]]
        catalog[row[0]]={'id':row[0],'index':row[1],'base':base,'offset':offset,'value':base+offset,
            'flags':flags,'name':text[row[23]:].split(b'\0',1)[0].decode('utf-8')}
    return catalog


def detail(t,label,page=1):
    try:
        state,frame=read_page(t,label,'reputation','/tcui reputation '+str(page),
            ready=lambda s:s.get('reputation_probe',{}).get('page')==page)
        t.receipt.setdefault('reputation_details',{})[label]={'state':state,'frame':frame};t.persist()
        return state['reputation_probe']
    finally:command(t,'/tcui state')


def catalog(t,label):
    initial=detail(t,label);count=initial['count'];rows=list(initial['rows'])
    if type(count)is not int or not 1<=count<=500:raise RuntimeError('public faction count exceeds bound')
    for page in range(2,(count+7)//8+1):
        probe=detail(t,label+'_'+str(page),page)
        if probe['count']!=count:raise RuntimeError('faction catalog changed during observation')
        rows.extend(probe['rows'])
    if len(rows)!=count or [r['index'] for r in rows]!=list(range(1,count+1)):
        raise RuntimeError('public faction catalog is incomplete')
    return {**initial,'rows':rows}


def standing_oracle(public,native):
    values=[]
    for row in public['rows']:
        if row['header'] and not row['has_rep']:continue
        faction=native.get(row.get('id'))
        matches=bool(faction and row['name']==faction['name'] and row['value']==faction['value'] and
            row['at_war']==bool(faction['flags']&2) and row['inactive']==bool(faction['flags']&32))
        values.append({'public':row,'native':faction,'passed':matches})
    if not values or not all(r['passed'] for r in values):raise RuntimeError('public faction standing or flags differ from native')
    return values


def open_panel(t):
    require(t.step('reputation.open_panel','Open the reputation window.',
        {'open':{'kind':'key','value':'u','description':'Press the installed reputation binding U.'}},
        lambda b,a,s:{'status':'reputation_open_pass' if 'ReputationFrame' in a['panels'] else
        'client_or_protocol_failure'},diagnostic_action='open'),'reputation_open_pass')


def inspect_faction(t,public,native,faction_id,label):
    row=next(r for r in public['rows'] if r.get('id')==faction_id and not r['header'])
    target=lambda c:c['text']==row['name'] and c['name'].startswith('ReputationBar')
    visible=lambda p:any(c['name']=='ReputationDetailFrame' and c['visible'] for c in p['controls'])
    # Stock ReputationBar_OnClick hides an already-open selected detail. Test
    # that ordinary close explicitly before clicking again to inspect it.
    if public.get('selected',{}).get('id')==faction_id and visible(public):
        def closed(b,a,s):
            probe=detail(t,label+'_detail_closed')
            return {'status':'reputation_detail_close_pass' if s and not visible(probe) else
                'client_or_protocol_failure','oracle':probe}
        require(click_case(t,label+'.close_existing','Close the already-selected '+row['name']+' detail.',target,closed),
            'reputation_detail_close_pass')
    def selected(b,a,s):
        probe=detail(t,label+'_selected');chosen=probe.get('selected',{})
        passed=s and chosen.get('id')==faction_id and chosen['value']==native[faction_id]['value'] and visible(probe)
        return {'status':'reputation_standing_pass' if passed else 'client_or_protocol_failure','oracle':probe}
    require(click_case(t,label,'Inspect the '+row['name']+' reputation standing.',target,selected),'reputation_standing_pass')


def inspect_stormwind(t,public,native,label='reputation.inspect_stormwind'):
    inspect_faction(t,public,native,72,label)


def suite(t,controls=False):
    actors.session_entry(t.fixture);t.clean_panels();before,items=native_state(),inventory()
    t.receipt['baseline']={'native':before,'inventory_money':items};t.persist()
    try:
        open_panel(t);public=catalog(t,'catalog_baseline');native=native_catalog(before)
        t.receipt['catalog_oracle']=standing_oracle(public,native);t.receipt['public_baseline']=public;t.persist()
        watched=before['character'][2]
        expected_watch=next((r for r in native.values() if r['index']==watched),None)
        actual_watch=public.get('watched',{})
        if (expected_watch is None and actual_watch.get('name') or expected_watch is not None and
                (actual_watch.get('id'),actual_watch.get('value'))!=(expected_watch['id'],expected_watch['value'])):
            raise RuntimeError('public watched faction differs from the native saved index')
        inspect_stormwind(t,public,native)
        if controls:
            from .interaction_reputation_controls import suite_controls
            suite_controls(t,public,before,native)
    finally:
        t.clean_panels();checks={'native_reputation_unchanged':native_state()==before,'inventory_money_unchanged':inventory()==items}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('reputation read trial changed the native baseline')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--controls',action='store_true');a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t,a.controls);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
