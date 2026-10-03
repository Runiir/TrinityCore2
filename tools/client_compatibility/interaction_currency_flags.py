"""Stock Honor backpack/unused roundtrips with exact wire and saved-state checks."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_currency import open_panel,detail,catalog,inspect,native_state,native_catalog,content_oracle,semantic_rows
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_trade import inventory
from .observation.journal import entries
from .world.buffer import Reader

CURRENCY=1901
NATIVE_CURRENCY=392


def expected_native(baseline,flag,enabled):
    return tuple((id,q,w,tr,flags|flag if enabled else flags&~flag) if id==NATIVE_CURRENCY else (id,q,w,tr,flags)
        for id,q,w,tr,flags in baseline)


def requests(session,started):
    out=[]
    for p in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if p.get('session')!=session or p.get('time',0)<started or p.get('name')!='CMSG_SET_CURRENCY_FLAGS':continue
        direction=p.get('direction');r=Reader(bytes.fromhex(p['body']))
        if direction=='from_client':id,flags=r.unpack('IB')
        elif direction=='to_native':flags,id=r.unpack('II')
        else:continue
        r.end();out.append({'direction':direction,'id':id,'flags':flags,'time':p['time']})
    return out


def toggle(t,kind,enabled,label,baseline,session):
    flag=4 if kind=='backpack' else 8
    control='TokenFramePopupBackpackCheckbox' if kind=='backpack' else 'TokenFramePopupInactiveCheckbox'
    before=detail(t,'flags_pre_'+label);selected=before.get('selected') or {}
    checkbox=next(r for r in before['controls'] if r['name']==control)
    if selected.get('id')!=CURRENCY or not checkbox['visible'] or checkbox['checked']==enabled:
        raise RuntimeError('requires selected Honor checkbox in the opposite state')
    started=time.time()
    def outcome(b,a,s):
        public=catalog(t,'flags_'+label);actual=native_state();expected=expected_native(baseline,flag,enabled)
        packets=requests(session,started);target_flags=next(r[-1] for r in expected if r[0]==NATIVE_CURRENCY)
        matched=all(any(p['direction']==direction and p['id']==id and p['flags']==target_flags for p in packets)
            for direction,id in [('from_client',CURRENCY),('to_native',NATIVE_CURRENCY)])
        row=next((r for r in public['rows'] if r.get('id')==CURRENCY),None)
        public_flag=bool(row and row['watched' if kind=='backpack' else 'unused']==enabled)
        # Moving into a collapsed Unused category can hide the row. The selected
        # checkbox remains the stock acknowledgement; later ordinary reveal tests it.
        box=next(r for r in public['controls'] if r['name']==control)
        if kind=='unused' and enabled and row is None:public_flag=box['checked']==enabled
        if row:content_oracle({'rows':[row]},native_catalog(expected))
        passed=bool(s and public_flag and actual==expected and matched)
        oracle={'public':public,'native':actual,'expected_native':expected,'packets':packets,
            'wire_agreement':matched,'passed':passed}
        t.receipt.setdefault('flag_oracles',{})[label]=oracle;t.persist()
        return {'status':'currency_flag_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
    require(click_case(t,'currency.'+kind+'.'+label,('Enable' if enabled else 'Disable')+' '+kind+' for Honor Points.',
        lambda c:c['name']==control,outcome),'currency_flag_pass')


def reveal(t,original,label):
    public=catalog(t,label+'_catalog')
    row=next((r for r in public['rows'] if r.get('id')==CURRENCY),None)
    if row:return public,row
    old_headers={r['name'] for r in original['rows'] if r['header']}
    new_headers=[r for r in public['rows'] if r['header'] and r['name'] not in old_headers and not r['expanded']]
    if len(new_headers)!=1:raise RuntimeError('unused currency requires one attributable collapsed destination header')
    header=new_headers[0]
    def outcome(b,a,s):
        probe=catalog(t,label+'_expanded')
        return {'status':'currency_navigation_pass' if s and any(r.get('id')==CURRENCY for r in probe['rows'])
            else 'client_or_protocol_failure','oracle':probe}
    require(click_case(t,'currency.unused.reveal','Expand '+header['name']+' to reveal Honor Points.',
        lambda c:c['text']==header['name'] and c['name'].startswith('TokenFrameContainerButton'),outcome),
        'currency_navigation_pass')
    public=catalog(t,label+'_revealed');return public,next(r for r in public['rows'] if r.get('id')==CURRENCY)


def suite(t,kind,persist=False):
    session=actors.session_entry(t.fixture)['session'];t.clean_panels();baseline,items=native_state(),inventory()
    native=native_catalog(baseline);flag=4 if kind=='backpack' else 8;initial=bool(native[CURRENCY]['flags']&flag)
    if initial:raise RuntimeError('currency trial requires an initially clear flag')
    t.receipt['baseline']={'native':baseline,'inventory_money':items};t.persist();public=None
    try:
        open_panel(t);public=catalog(t,'flags_baseline');content_oracle(public,native)
        t.receipt['public_baseline']=public;t.persist()
        row=next(r for r in public['rows'] if r.get('id')==CURRENCY);inspect(t,row,native,'currency.flags.select')
        toggle(t,kind,True,'change',baseline,session)
        if kind=='backpack':
            def backpack(b,a,s):
                probe=detail(t,'backpack_visible');row=next((r for r in probe['backpack'] if r['id']==CURRENCY),{})
                passed=(s=='bag' and bool(row.get('visible')) and row.get('count')==native[CURRENCY]['quantity'] and
                    row.get('rendered_count')==str(native[CURRENCY]['quantity']))
                return {'status':'currency_backpack_visible_pass' if passed else 'client_or_protocol_failure','oracle':probe}
            require(t.step('currency.backpack.visible','Open the backpack and view watched Honor Points.',
                {'bag':{'kind':'key','value':'b','description':'Press B to open the backpack.'}},backpack,
                diagnostic_action='bag'),'currency_backpack_visible_pass')
        if persist:
            def reload(b,a,s):
                probe=catalog(t,'flags_after_reload');row=next((r for r in probe['rows'] if r.get('id')==CURRENCY),{})
                checks={'native_flags_preserved':native_state()==expected_native(baseline,flag,True),
                    'public_watch_preserved':row.get('watched') is True,'inventory_money_preserved':inventory()==items,
                    'resources_and_identity_preserved':all(a.get(k)==b.get(k) for k in ['guid','money','equipment','group','raid_profile']),
                    'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
                return {'status':'currency_persistence_pass' if s=='reload' and all(checks.values()) else
                    'client_or_protocol_failure','oracle':checks}
            require(t.step('currency.persist_reload','Reload and preserve watched Honor Points.',
                {'reload':{'kind':'chat','value':'/reload','description':'Use ordinary /reload.'}},reload,
                diagnostic_action='reload'),'currency_persistence_pass')
            t.clean_panels();open_panel(t)
            current=catalog(t,'flags_reload_reselect');row=next(r for r in current['rows'] if r.get('id')==CURRENCY)
            inspect(t,row,native_catalog(expected_native(baseline,flag,True)),'currency.flags.reload_select')
        elif kind=='unused':
            current,row=reveal(t,public,'unused_destination');inspect(t,row,native_catalog(expected_native(baseline,flag,True)),
                'currency.unused.reselect')
        toggle(t,kind,False,'restore',baseline,session)
    finally:
        current=native_state()
        if current!=baseline:
            state,_=t.observe('flag_cleanup_state')
            if 'TokenFrame' not in state['panels']:t.clean_panels();open_panel(t)
            current_public,row=reveal(t,public,'flags_cleanup');inspect(t,row,native_catalog(current),'currency.flags.cleanup_select')
            toggle(t,kind,initial,'cleanup_restore',baseline,session)
        restored=catalog(t,'flags_restored') if public else None
        t.clean_panels();checks={'native_currency_restored':native_state()==baseline,
            'inventory_money_unchanged':inventory()==items,'public_catalog_restored':not public or semantic_rows(restored)==semantic_rows(public)}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('currency flags did not restore the complete baseline')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--kind',choices=['backpack','unused'],default='backpack');p.add_argument('--persist',action='store_true');a=p.parse_args()
    if a.persist and a.kind!='backpack':p.error('reload persistence currently qualifies the backpack flag only')
    t=Trial(a.output,controller='code')
    try:suite(t,a.kind,a.persist);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
