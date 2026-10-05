"""Copy an owned player name or close its stock report form through observed controls."""
import time
from .interaction_control_target import target
from .interaction_operations import controls,point
from .interaction_macros import require
from .interaction_private_clipboard import copied_name,marker


def menu_click(t,label,text,oracle,*,await_state=None):
    row=target(t,label,lambda c:c['text']==text)
    if not row.get('enabled') or row['kind'] not in ('MenuItem','Button'):
        raise RuntimeError('owned player menu item is not enabled')
    t.io.move(*point(row));time.sleep(1)
    return t.step(label,'Use the observed '+text+' item for the owned player.',
        {'click':{'kind':'click','value':point(row),'hold':1.2}},
        lambda b,a,s:oracle(b,a,s=='click'),diagnostic_action='click',await_state=await_state)


def expected_names(seed):
    name=seed['observed_sender']
    if not isinstance(name,str) or name.split('-',1)[0]!='Harnesstwo' or seed['expected_native_guid']!=2:
        raise RuntimeError('owned name copy/report source differs')
    return {name,name.split('-',1)[0]}


def copy(t,seed):
    expected=expected_names(seed)
    def outcome(b,a,s):
        result=copied_name(t,expected,fixture['owner_window']);t.receipt['owned_name_clipboard']=result;t.persist()
        checks={'ordinary_copy':s,'exact_owned_name':result['exact_owned_name'],
            'owned_guard_replaced':result['owned_guard_replaced'],'owned_menu_before':'ContextMenu' in b['panels'],
            'only_transient_menu_after':set(a['panels']).issubset({'ContextMenu','DropDownList1','DropDownList2'}),
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'owned_player_name_copy_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'clipboard':result}}
    with marker(t) as fixture:
        t.receipt['owned_copy_clipboard_fixture']=fixture;t.persist()
        probe=copied_name(t,{fixture['marker']})
        t.receipt['owned_copy_clipboard_fixture_probe']=probe;t.persist()
        if not probe['exact_owned_name'] or probe['owner_window']!=fixture['owner_window']:
            raise RuntimeError('private clipboard marker is not readable from its owned provider; no Copy sent')
        require(menu_click(t,'chat.copy_if_available','Copy Character Name',outcome),'owned_player_name_copy_pass')


def report(t,seed):
    expected=expected_names(seed)
    require(menu_click(t,'fixture.open_owned_player_report','Report Player',lambda b,a,s:
        {'status':'owned_report_ui_open' if s and 'ReportFrame' in a['panels'] and not a.get('lua_errors') and
            not a.get('blocked_actions') else 'client_or_protocol_failure'},
        await_state=lambda a:'ReportFrame' in a['panels']),'owned_report_ui_open')
    rows=controls(t);state,frame=t.observe('owned_report_ui_rendered')
    context=owned_report_context(t,seed);checks=report_identity(rows,expected,context)
    checks['attributed_owned_chat_source']=context
    t.receipt['owned_report_ui']={'checks':checks,'controls':rows,'state':state,'frame':frame,'submitted':False,
        'public_guid_available':any(c.get('report_player_guid') is not None for c in rows if c.get('report_action')=='close')};t.persist()
    if not all(checks.values()):raise RuntimeError('owned report form identity or close/submit controls differ')
    control=target(t,'chat.report_ui_cancel',lambda c:c.get('report_action')=='close' and
        c.get('report_player_name') in expected and report_guid_matches(c,context))
    if not control.get('enabled') or control['kind']!='Button':raise RuntimeError('observed report close is not enabled')
    t.io.move(*point(control));time.sleep(1)
    require(t.step('chat.report_ui_cancel','Close the owned report form with its observed Close button.',
        {'close':{'kind':'click','value':point(control),'hold':1.2}},lambda b,a,s:
        {'status':'owned_report_ui_cancel_pass' if s=='close' and 'ReportFrame' in b['panels'] and
            'ReportFrame' not in a['panels'] and not a.get('lua_errors') and not a.get('blocked_actions')
            else 'client_or_protocol_failure','oracle':{'submitted':False,'identity':checks}},
        diagnostic_action='close',await_state=lambda a:'ReportFrame' not in a['panels']),'owned_report_ui_cancel_pass')


def report_guid_matches(row,owned_context=False):
    guid=row.get('report_player_guid')
    return guid=='Player-1-00000002' or (guid is None and owned_context)


def owned_report_context(t,seed):
    pointer=t.receipt.get('player_link_pointer_settled',{}).get('pointer',{})
    link=pointer.get('chat_link') or {}
    public=t.receipt.get('player_menu',{}).get('state',{}).get('chat_probes',[])
    return (seed.get('expected_native_guid')==2 and bool(seed.get('checks')) and all(seed['checks'].values()) and
        link.get('frame')=='ChatFrame1' and link.get('data','').startswith('player:'+seed['observed_sender']+':') and
        len([r for r in public if r.get('event')=='CHAT_MSG_WHISPER' and r.get('text')==seed['token'] and
            r.get('sender')==seed['observed_sender']])==1)


def report_identity(rows,expected,owned_context=False):
    close=[c for c in rows if c.get('report_action')=='close']
    submit=[c for c in rows if c.get('report_action')=='submit']
    return {'one_close':len(close)==1,'one_submit':len(submit)==1,
        'owned_name':len(close)==1 and close[0].get('report_player_name') in expected,
        'owned_guid_or_attributed_chat_source':len(close)==1 and report_guid_matches(close[0],owned_context),
        'submission_not_ready':len(submit)==1 and submit[0].get('enabled') is False}
