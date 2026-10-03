"""Ordinary Cata currency controls with saved native and public-content oracles."""
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
        q.execute('SELECT Currency,Quantity,WeeklyQuantity,TrackedQuantity,Flags '
            'FROM client442_characters.character_currency WHERE CharacterGuid=%s ORDER BY Currency',
            (actors.load()['guid'],))
        return q.fetchall()


def native_catalog(state):
    data=(lab.ROOT/'data/dbc/enUS/CurrencyTypes.dbc').read_bytes()
    magic,count,fields,width,strings=struct.unpack_from('<4s4I',data)
    if magic!=b'WDBC' or (fields,width)!=(11,44) or len(data)!=20+count*width+strings:
        raise RuntimeError('unexpected native currency DBC layout')
    text=data[20+count*width:]
    entries={}
    for index in range(count):
        row=struct.unpack_from('<11I',data,20+index*width)
        entries[row[0]]=row
    out={}
    for kind,quantity,weekly,tracked,flags in state:
        row=entries[kind];precision=100 if row[9]&8 else 1
        modern=1901 if kind==392 else kind
        out[modern]={'id':modern,'native_id':kind,'name':text[row[2]:].split(b'\0',1)[0].decode(),
            'quantity':quantity//precision,'weekly':weekly//precision,'tracked':tracked//precision,
            'max_quantity':row[7]//precision,'static_weekly_cap':row[8]//precision,'flags':flags,
            'precision':precision,'category':row[1]}
    return out


def detail(t,label,page=1):
    try:
        state,frame=read_page(t,label,'currency','/tcui currency '+str(page),
            ready=lambda s:s.get('currency_probe',{}).get('page')==page)
        probe=state['currency_probe']
        t.receipt.setdefault('currency_details',{})[label]={'state':state,'frame':frame};t.persist()
        return probe
    finally:command(t,'/tcui state')


def catalog(t,label):
    initial=detail(t,label);count=initial['count'];rows=list(initial.get('rows') or [])
    if type(count)is not int or not 1<=count<=500:raise RuntimeError('public currency count exceeds bound')
    for page in range(2,(count+7)//8+1):
        probe=detail(t,label+'_'+str(page),page)
        if probe['count']!=count:raise RuntimeError('currency catalog changed during observation')
        rows.extend(probe.get('rows') or [])
    if len(rows)!=count or [r['index'] for r in rows]!=list(range(1,count+1)):
        raise RuntimeError('public currency catalog is incomplete')
    return {**initial,'rows':rows}


def content_oracle(public,native):
    rows=[]
    for row in public['rows']:
        if row['header']:continue
        saved=native.get(row.get('id'));info=row.get('info') or {}
        passed=bool(saved and row['name']==saved['name'] and row['count']==saved['quantity'] and
            info.get('name')==saved['name'] and info.get('quantity')==saved['quantity'])
        rows.append({'public':row,'native':saved,'passed':passed})
    if not rows or not all(r['passed'] for r in rows):raise RuntimeError('public currency differs from saved native quantity/name')
    return rows


def visible(probe,name):
    return any(c['name']==name and c['visible'] for c in probe['controls'])


def open_panel(t):
    require(t.step('currency.character_navigation','Open the character window.',
        {'character':{'kind':'key','value':'c','description':'Press C to open the character window.'}},
        lambda b,a,s:{'status':'currency_navigation_pass' if 'CharacterFrame' in a['panels'] else
        'client_or_protocol_failure'},diagnostic_action='character'),'currency_navigation_pass')
    require(click_case(t,'currency.open','Open the Currencies tab.',lambda c:c['name']=='CharacterFrameTab4',
        lambda b,a,s:{'status':'currency_open_pass' if s and 'TokenFrame' in a['panels'] else
        'client_or_protocol_failure'}),'currency_open_pass')


def inspect(t,row,native,label='currency.inspect_currency'):
    def oracle(b,a,s):
        probe=detail(t,label+'_selected');selected=probe.get('selected') or {}
        passed=s and selected.get('id')==row['id'] and visible(probe,'TokenFramePopup')
        if passed:content_oracle({'rows':[selected]},native)
        return {'status':'currency_inspect_pass' if passed else 'client_or_protocol_failure','oracle':probe}
    require(click_case(t,label,'Inspect '+row['name']+' currency options.',
        lambda c:c['text']==row['name'] and c['name'].startswith('TokenFrameContainerButton'),oracle),
        'currency_inspect_pass')


def headers(t,original):
    header=next(row for row in original['rows'] if row['header'] and row['expanded'])
    start=header['index'];end=next((r['index'] for r in original['rows'][start:] if r['header']),len(original['rows'])+1)
    hidden={r['id'] for r in original['rows'][start:end-1] if not r['header']}
    if not hidden:raise RuntimeError('expanded header has no attributable children')
    for expanded,label in [(False,'collapse'),(True,'expand')]:
        def oracle(b,a,s):
            probe=catalog(t,'header_'+label)
            current=next(r for r in probe['rows'] if r['header'] and r['name']==header['name'])
            ids={r.get('id') for r in probe['rows'] if not r['header']}
            passed=s and current['expanded']==expanded and (hidden<=ids if expanded else not hidden&ids)
            if expanded:passed=passed and probe['rows']==original['rows']
            return {'status':'currency_header_pass' if passed else 'client_or_protocol_failure','oracle':probe}
        require(click_case(t,'currency.'+label,'Click '+header['name']+' to '+label+' its currencies.',
            lambda c:c['text']==header['name'] and c['name'].startswith('TokenFrameContainerButton'),oracle),
            'currency_header_pass')


def suite(t):
    actors.session_entry(t.fixture);t.clean_panels();before,items=native_state(),inventory()
    t.receipt['baseline']={'native':before,'inventory_money':items};t.persist()
    try:
        open_panel(t);public=catalog(t,'catalog_baseline');native=native_catalog(before)
        t.receipt['public_baseline']=public;t.receipt['content_oracle']=content_oracle(public,native);t.persist()
        row=next(r for r in public['rows'] if not r['header']);inspect(t,row,native)
        headers(t,public)
        require(t.step('currency.close','Close the currencies window.',
            {'close':{'kind':'key','value':'Escape','description':'Press Escape to close the character window.'}},
            lambda b,a,s:{'status':'currency_close_pass' if 'TokenFrame' not in a['panels'] else
            'client_or_protocol_failure'},diagnostic_action='close'),'currency_close_pass')
    finally:
        t.clean_panels();checks={'native_currency_unchanged':native_state()==before,'inventory_money_unchanged':inventory()==items}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('currency read trial changed the native baseline')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
