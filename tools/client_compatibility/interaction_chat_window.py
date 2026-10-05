"""Inspect the stock chat tab menu before choosing reversible window controls."""
import argparse,json,math,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_observation import read_page
from .interaction_operations import command,controls,point
from .interaction_control_target import target,click,edit
from .interaction_macros import require
from . import lab_runtime as lab


def detail(t,label):
    label=str(len(t.receipt.get('chat_window_details',{})))+'_'+label
    try:
        state,frame=read_page(t,label,'chat','/tcui chat')
        t.receipt.setdefault('chat_window_details',{})[label]={'state':state,'frame':frame};t.persist()
        probe=state['chat_window_probe']
        if not probe['available']:raise RuntimeError('public chat-window info API is unavailable')
        return probe
    finally:command(t,'/tcui state')


def recon(t):
    before=detail(t,'chat_windows_original');t.receipt['chat_window_baseline']=before;t.persist()
    control=target(t,'stock_general_chat_tab',lambda c:c['name']=='ChatFrame1Tab')
    require(t.step('fixture.chat_tab_menu','Inspect the observed General chat-tab context menu.',
        {'menu':{'kind':'click','value':point(control),'button':3,'description':'Right-click the observed General chat tab.'}},
        lambda b,a,s:{'status':'stock_chat_menu_visible' if s=='menu' and
            any(p in a['panels'] for p in ['DropDownList1','ContextMenu']) else 'client_or_protocol_failure'},
        diagnostic_action='menu'),'stock_chat_menu_visible')
    rows=controls(t);t.receipt['chat_menu_observed_controls']=rows;t.persist();t.clean_panels()
    after=detail(t,'chat_windows_recon_restored')
    fields=['id','name','font_size','color','alpha','shown','locked','docked','uninteractable',
        'frame_visible','actual_font','actual_font_size','font_flags','scroll_offset']
    signature=lambda probe:[{k:row.get(k) for k in fields} for row in probe['windows']]
    same=signature(before)==signature(after) and before['selected']==after['selected']
    t.receipt['chat_window_recon_restored']=same;t.persist()
    if not same:raise RuntimeError('chat-window settings changed during read-only menu inspection')


def font_recon(t):
    before=detail(t,'font_recon_original');menu(t,1,'fixture.font_recon_menu')
    control=target(t,'font_recon_submenu',lambda c:c['text']=='Font Size')
    t.io.move(*point(control));time.sleep(1)
    rows=controls(t);state,frame=t.observe('font_submenu_rendered')
    t.receipt['font_submenu_recon']={'controls':rows,'frame':frame,'input':{'hover':point(control)}};t.persist()
    t.clean_panels();after=detail(t,'font_recon_restored')
    keys=['id','name','font_size','actual_font','actual_font_size','color','alpha','shown','locked','docked']
    same=[{k:r.get(k) for k in keys} for r in before['windows']]==[{k:r.get(k) for k in keys} for r in after['windows']]
    t.receipt['font_recon_restored']=same;t.persist()
    if not same:raise RuntimeError('font submenu inspection changed chat settings')


NAMES={'TC442Chat','TC442Renamed'}


def menu(t,index,label):
    control=target(t,label,lambda c:c['name']=='ChatFrame'+str(index)+'Tab')
    require(t.step(label,'Open the observed stock chat-tab menu.',
        {'menu':{'kind':'click','value':point(control),'button':3,'description':'Right-click the observed chat tab.'}},
        lambda b,a,s:{'status':'stock_chat_menu_visible' if s=='menu' and
            any(p in a['panels'] for p in ['DropDownList1','ContextMenu']) else 'client_or_protocol_failure'},
        diagnostic_action='menu'),'stock_chat_menu_visible')


def option(t,label,text,oracle):
    return click(t,label,'Use the observed stock '+text+' control.',lambda c:c['text']==text,oracle)


def named(t,label,text,name):
    require(option(t,label+'_dialog',text,lambda b,a,s:{'status':'chat_name_dialog' if s and
        'StaticPopup1' in a['panels'] else 'client_or_protocol_failure'}),'chat_name_dialog')
    require(edit(t,label+'_name','Enter the exact disposable chat-window name.',
        lambda c:c['name']=='StaticPopup1EditBox' or ('chat' in c.get('context','').lower() and not c['name']),
        name),'ui_edit_pass')
    def accepted(b,a,s):
        after=detail(t,label+'_result');matches=[r for r in after['windows'] if r['name']==name]
        checks={'ordinary_confirm':s,'one_owned_window':len(matches)==1,'visible_owned_window':bool(matches and
            matches[0]['frame_visible'] and matches[0]['tab_visible']),
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_chat_name_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':after}}
    require(click(t,label,'Confirm the exact disposable chat-window name.',lambda c:
        c['name']=='StaticPopup1Button1',accepted),'stock_chat_name_pass')


def font(t,index,size,label):
    menu(t,index,label+'_menu')
    control=target(t,label+'_submenu',lambda c:c['text']=='Font Size')
    t.receipt.setdefault('chat_font_submenus',[]).append({'control':control,'input':{'hover':point(control)}});t.persist()
    t.io.move(*point(control));time.sleep(.8)
    def outcome(b,a,s):
        after=detail(t,label+'_result');row=next(r for r in after['windows'] if r['id']==index)
        checks={'ordinary_click':s,'actual_font_size':math.isclose(row['actual_font_size'],size,abs_tol=.01),
            'still_owned':row['name'] in NAMES,'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_chat_font_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':after,'expected_size':size}}
    require(option(t,label,str(size)+' pt',outcome),'stock_chat_font_pass')


def close_owned(t,index,label):
    current=detail(t,label+'_guard');row=next(r for r in current['windows'] if r['id']==index)
    if row['name'] not in NAMES:raise RuntimeError('refusing to close a chat window outside exact owned names')
    menu(t,index,label+'_menu')
    def outcome(b,a,s):
        after=detail(t,label+'_result');row=next(r for r in after['windows'] if r['id']==index)
        checks={'ordinary_close':s,'hidden_frame':not row['frame_visible'],'hidden_tab':not row['tab_visible'],
            'not_shown':not row['shown'],'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_chat_close_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'closed_slot':row,'public':after}}
    require(option(t,label,'Close Window',outcome),'stock_chat_close_pass')


def mutate(t,closed_source=None):
    before=detail(t,'chat_mutation_original');closed_ids=set()
    if closed_source:
        source=closed_source.resolve()
        if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
            raise ValueError('require the exact owned closed-window failure receipt')
        old=json.loads(source.read_text())
        if (old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or not old.get('finished_at') or
                old['completed'] or old['failure']!='RuntimeError: fresh target control was not observed: chat.font_size' or
                not all(old['native_restoration']['checks'].values()) or
                not all(old['chat_mutation_restoration']['checks'].values()) or
                json.loads(json.dumps(t.receipt['native_baseline']))!=old['native_baseline']):
            raise RuntimeError('closed source or original native fixture differs')
        index=old['owned_chat_window']['id']
        expected=next(r for r in old['chat_mutation_restoration']['closed_slot_metadata'] if r['id']==index)
        current=next(r for r in before['windows'] if r['id']==index)
        if current!=expected or current['name'] not in NAMES or any(current[k] for k in ['shown','frame_visible','tab_visible']):
            raise RuntimeError('exact source-attributed closed slot metadata differs')
        closed_ids.add(index);t.receipt['prior_closed_chat_source']={'file':str(source),'sha256':lab.sha256(source),
            'closed_slot':current,'native_fixture_unchanged':True};t.persist()
    existing={r['id']:r for r in before['windows'] if r.get('name') and r['id'] not in closed_ids}
    if before['selected']!=1 or before['windows'][0]['name']!='General' or any(r['name'] in NAMES and
            r['id'] not in closed_ids for r in before['windows']):
        raise RuntimeError('requires the original selected General tab and absent disposable names')
    t.receipt['chat_mutation_baseline']=before;t.persist();owned=None;created=None
    fields=['id','name','font_size','color','alpha','shown','locked','docked','uninteractable',
        'frame_visible','actual_font','actual_font_size','font_flags','scroll_offset']
    try:
        menu(t,1,'fixture.create_chat_menu');named(t,'chat.chat_tab_create','Create New Window','TC442Chat')
        current=detail(t,'created_owned_chat');created=next(r for r in current['windows'] if r['name']=='TC442Chat')
        owned=created['id']
        if owned in existing:raise RuntimeError('stock creation reused an originally named chat window')
        t.receipt['owned_chat_window']=created;t.persist()
        menu(t,owned,'fixture.rename_chat_menu');named(t,'chat.chat_tab_rename','Rename Window','TC442Renamed')
        original_size=round(created['actual_font_size'])
        if not math.isclose(created['actual_font_size'],original_size,abs_tol=.01) or original_size==16:
            raise RuntimeError('requires a different integral original disposable-window font')
        font(t,owned,16,'chat.font_size');font(t,owned,original_size,'fixture.restore_chat_font')
        close_owned(t,owned,'chat.chat_tab_close');owned=None
    finally:
        t.clean_panels();current=detail(t,'chat_mutation_cleanup')
        leftovers=[r for r in current['windows'] if r['name'] in NAMES and (r['frame_visible'] or r['tab_visible'] or r['shown'])]
        for row in leftovers:
            if row['id'] in existing:raise RuntimeError('cleanup found an originally named slot; refusing close')
            close_owned(t,row['id'],'fixture.close_owned_chat_'+str(row['id']))
        current=detail(t,'chat_mutation_after_cleanup')
        if current['selected']!=before['selected']:
            require(click(t,'fixture.restore_original_chat_tab','Restore the original selected chat tab.',
                lambda c:c['name']=='ChatFrame'+str(before['selected'])+'Tab',lambda b,a,s:{'status':'chat_selection_restored'
                    if s and detail(t,'chat_selection_restored')['selected']==before['selected'] else
                    'client_or_protocol_failure'}),'chat_selection_restored')
        after=detail(t,'chat_mutation_restored')
        checks={'existing_windows':all(all(row.get(k)==next(r for r in after['windows'] if r['id']==index).get(k)
            for k in fields) for index,row in existing.items()),'original_selection':after['selected']==before['selected'],
            'no_visible_owned_window':not any(r['name'] in NAMES and (r['shown'] or r['frame_visible'] or r['tab_visible'])
                for r in after['windows'])}
        t.receipt['chat_mutation_restoration']={'checks':checks,'closed_slot_metadata':
            [r for r in after['windows'] if r['id'] not in existing],
            'limits':'Closing an owned disposable window may retain stock hidden-slot metadata. Existing named windows and their settings must remain exact; no byte-identical chat-cache claim.'};t.persist()
        if not all(checks.values()):raise RuntimeError('original named chat windows or selection differ')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mutate',action='store_true');p.add_argument('--font-recon',action='store_true')
    p.add_argument('--closed-source',type=Path);a=p.parse_args()
    if a.closed_source and not a.mutate:p.error('closed source applies only to a fresh mutation trial')
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=(lambda t:mutate(t,a.closed_source)) if a.mutate else font_recon if a.font_recon else recon,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
