"""Stock archaeology selection and earned-fragment solve with native oracles."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,command
from .interaction_macros import require
from .interaction_observation import read_page
from .interaction_currency import native_state as currencies
from .interaction_trade import inventory


def dbc(name,fields):
    path=lab.ROOT/'data/dbc/enUS'/(name+'.dbc');body=path.read_bytes()
    magic,count,width,size,strings=struct.unpack_from('<4s4I',body)
    if magic!=b'WDBC' or (width,size)!=(fields,fields*4) or len(body)!=20+count*size+strings:
        raise RuntimeError('unexpected native '+name+' layout')
    text=body[20+count*size:]
    rows=[struct.unpack_from('<'+str(fields)+'I',body,20+i*size) for i in range(count)]
    return rows,lambda index:text[index:].split(b'\0',1)[0].decode()


def native():
    saved=currencies();guid=actors.load()['guid']
    with lab.connection() as con,con.cursor() as cur:
        cur.execute('SELECT branch,project FROM client442_characters.character_archaeology_projects '
            'WHERE guid=%s ORDER BY branch',(guid,));projects=cur.fetchall()
        cur.execute('SELECT project,time,count FROM client442_characters.character_archaeology_completed '
            'WHERE guid=%s ORDER BY project',(guid,));completed=cur.fetchall()
    return {'currencies':saved,'projects':projects,'completed':completed,'inventory':inventory()}


def contracts(state):
    branches,text=dbc('ResearchBranch',6)
    branch={r[0]:{'name':text(r[1]),'currency':r[3],'keystone':r[5]} for r in branches}
    projects,text=dbc('ResearchProject',9)
    project={r[0]:{'id':r[0],'name':text(r[1]),'branch':r[4],'spell':r[5],'sockets':r[6],'cost':r[8]} for r in projects}
    effects,_=dbc('SpellEffect',27)
    items={r[24]:r[10] for r in effects if r[1]==24 and r[10]>0}
    quantity={r[0]:r[1] for r in state['currencies']}
    result=[]
    for kind,id in state['projects']:
        p=project[id]
        if p['branch']!=kind:raise RuntimeError('native project branch differs')
        result.append({**p,**branch[kind],'project_name':p['name'],
            'quantity':quantity.get(branch[kind]['currency'],0),'item':items.get(p['spell'])})
    return result


def detail(t,label,page=1):
    try:
        state,frame=read_page(t,label,'archaeology','/tcui archaeology '+str(page),
            ready=lambda s:s.get('archaeology_probe',{}).get('page')==page)
        t.receipt.setdefault('archaeology_details',{})[label]={'state':state,'frame':frame};t.persist()
        return state['archaeology_probe']
    finally:command(t,'/tcui state')


def catalog(t,label):
    first=detail(t,label);count=first['race_count'];rows=list(first.get('races') or [])
    if not 1<=count<=40:raise RuntimeError('archaeology races exceed bound')
    for page in range(2,(count+3)//4+1):
        probe=detail(t,label+'_'+str(page),page)
        if probe['race_count']!=count:raise RuntimeError('race count changed')
        rows.extend(probe.get('races') or [])
    if len(rows)!=count or [r['index'] for r in rows]!=list(range(1,count+1)):
        raise RuntimeError('incomplete archaeology race catalog')
    return {**first,'races':rows}


def open_panel(t):
    require(t.step('archaeology.professions_navigation','Open professions.',
        {'skills':{'kind':'key','value':'k','description':'Press K for professions.'}},
        lambda b,a,s:{'status':'archaeology_navigation_pass' if 'SpellBookFrame' in a['panels'] else
            'client_or_protocol_failure'},diagnostic_action='skills'),'archaeology_navigation_pass')
    require(click_case(t,'archaeology.open','Open Archaeology.',lambda c:c['text']=='Archaeology',
        lambda b,a,s:{'status':'archaeology_open_pass' if s and 'ArchaeologyFrame' in a['panels'] else
            'client_or_protocol_failure'}),'archaeology_open_pass')


def select(t,contract,public):
    matches=[r for r in public['races'] if r['name']==contract['name']]
    if len(matches)!=1:raise RuntimeError('native branch has no unique public race')
    row=matches[0];button=row.get('button') or {}
    if (row['quantity']!=contract['quantity'] or row['required']!=contract['cost'] or
        row['keystone']!=contract['keystone'] or not button.get('visible') or not button.get('enabled')):
        raise RuntimeError('visible race currency/project disagrees with native contract')
    def outcome(b,a,s):
        probe=detail(t,'selected_project');selected=probe.get('selected') or {};progress=probe['progress']
        checks={'visible':probe['artifact_visible'],'native_spell':selected.get('spell')==contract['spell'],
            'name':selected.get('name')==contract['project_name']==probe.get('rendered_artifact'),
            'quantity':progress.get('base')==contract['quantity'],'cost':progress.get('cost')==contract['cost'],
            'no_keystones':progress.get('adjust')==0,'solvable':bool(progress.get('can_solve'))==
                (contract['quantity']>=contract['cost'])}
        return {'status':'archaeology_project_pass' if s and all(checks.values()) else
            'client_or_protocol_failure','oracle':{'checks':checks,'contract':contract,'public':probe}}
    require(click_case(t,'archaeology.select_race','Inspect the current '+contract['name']+' project.',
        lambda c:c['name']==button['name'],outcome),'archaeology_project_pass')


def solve(t,contract,baseline):
    def outcome(b,a,s):
        deadline=time.monotonic()+18;samples=[]
        while True:
            after=native();history=next((r for r in after['completed'] if r[0]==contract['id']),None)
            prior=next((r for r in baseline['completed'] if r[0]==contract['id']),None)
            completed=bool(history and history[2]==(prior[2] if prior else 0)+1)
            samples.append({'time':time.time(),'completed':completed})
            if completed or time.monotonic()>deadline:break
            time.sleep(.5)
        expected=[tuple([r[0],r[1]-contract['cost'],*r[2:]]) if r[0]==contract['currency'] else r
            for r in baseline['currencies']]
        old={r[3]:r for r in baseline['inventory']['items']};new={r[3]:r for r in after['inventory']['items']}
        added=[r for id,r in new.items() if id not in old]
        public=catalog(t,'after_solve');race=next(r for r in public['races'] if r['name']==contract['name'])
        checks={'ordinary_solve':s,'native_completion':completed,'exact_fragment_spend':after['currencies']==tuple(expected),
            'existing_items_preserved':all(new.get(id)==r for id,r in old.items()),
            'artifact_created':len(added)==1 and added[0][0]==t.fixture['guid'] and
                added[0][4]==contract['item'] and added[0][5]==1 and added[0][6]==t.fixture['guid'],
            'money_preserved':after['inventory']['money']==baseline['inventory']['money'],
            'public_fragments':race['quantity']==contract['quantity']-contract['cost'],
            'public_history':any(r['spell']==contract['spell'] and r['count']==history[2] for r in race['completed'])
                if history else False}
        t.receipt['solve_outcome']={'checks':checks,'native':after,'public':public,'samples':samples};t.persist()
        return {'status':'archaeology_solve_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':t.receipt['solve_outcome']}
    require(click_case(t,'archaeology.solve_project','Solve this project with earned fragments and no keystones.',
        lambda c:c['name']=='ArchaeologyFrameArtifactPageSolveFrameSolveButton',outcome),'archaeology_solve_pass')
    require(t.step('archaeology.artifact_bag','Open the backpack and inspect the crafted artifact.',
        {'bag':{'kind':'key','value':'b','description':'Press B to open the backpack.'}},
        lambda b,a,s:{'status':'archaeology_artifact_visible_pass' if s=='bag' and 0 in a.get('bags',[]) and
            any(r['id']==contract['item'] and r['count']==1 for r in a.get('bag_items',[])) else
            'client_or_protocol_failure','oracle':{'expected_item':contract['item'],'bag_items':a.get('bag_items')}},
        diagnostic_action='bag'),'archaeology_artifact_visible_pass')


def suite(t,do_solve=False):
    actors.session_entry(t.fixture);t.clean_panels();baseline=native();t.receipt['baseline']=baseline;t.persist()
    try:
        available=contracts(baseline);t.receipt['project_contracts']=available;t.persist()
        chosen=next((r for r in available if r['name']=='Draenei' and r['quantity']>=r['cost'] and r['item']),None)
        if chosen is None:raise RuntimeError('earned Draenei fragment fixture unavailable')
        open_panel(t);public=catalog(t,'race_catalog');t.receipt['public_baseline']=public;t.persist()
        select(t,chosen,public)
        if do_solve:solve(t,chosen,baseline)
    finally:
        t.clean_panels();after=native();t.receipt['native_after']=after
        t.receipt['native_unchanged']=after==baseline;t.persist()
        if not do_solve and after!=baseline:raise RuntimeError('read-only project trial mutated native state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--solve',action='store_true');a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.solve);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
