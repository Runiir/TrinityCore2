"""Stock keystone add/remove, weighted earned solve and completed-item tooltip."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_trial import Trial
from .interaction_operations import click_case,controls,point
from .interaction_macros import require
from .interaction_archaeology_projects import native,contracts,open_panel,catalog,select,detail,solve,completed_panel


def toggle(t,contract,baseline,added,label):
    def outcome(b,a,s):
        probe=detail(t,'keystone_'+label);progress=probe['progress']
        button=next(p for p in probe['keystone_buttons'] if p['index']==1)
        checks={'native_state_unchanged':native()==baseline,'selected_spell':probe['selected']['spell']==contract['spell'],
            'exact_base':progress['base']==contract['quantity'],'exact_cost':progress['cost']==contract['cost'],
            'exact_adjustment':progress['adjust']==(12 if added else 0),
            'socket_state':button['added']==added,'socket_icon':button['icon_visible']==added,
            'solvable':bool(progress['can_solve'])==(contract['quantity']+(12 if added else 0)>=contract['cost'])}
        t.receipt.setdefault('keystone_oracles',{})[label]={'checks':checks,'public':probe};t.persist()
        return {'status':'archaeology_keystone_pass' if s and all(checks.values()) else
            'client_or_protocol_failure','oracle':{'checks':checks,'public':probe}}
    require(click_case(t,'archaeology.keystone.'+label,'Add one keystone.' if added else 'Remove the selected keystone.',
        lambda c:c['name']=='ArchaeologyFrameArtifactPageSolveFrameKeystone1',outcome),'archaeology_keystone_pass')


def tooltip(t,contract,earned):
    probe=catalog(t,'tooltip_catalog')
    button=next(p for p in probe['completed_buttons'] if p['rendered']==contract['project_name'])
    row=next(c for c in controls(t) if c['name']==button['name'])
    expected=next(r for r in earned['completed'] if r[0]==contract['id'])
    def outcome(b,a,s):
        public=detail(t,'completed_project_tooltip');lines=public.get('tooltip_lines') or []
        checks={'visible':public['tooltip_visible'],'project_title':bool(lines) and lines[0]==contract['project_name'],
            'native_completion_count':(public['completion_format']%expected[2]) in lines,
            'timestamp_displayed':any(public['timestamp_caption'] in line for line in lines),
            'native_state_preserved':native()==earned,'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'archaeology_tooltip_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':public,'native_completion':expected}}
    require(t.step('archaeology.project_tooltip','Hover the completed artifact and inspect its tooltip.',
        {'hover':{'kind':'hover','value':point(row),'description':'Move the private mouse onto '+contract['project_name']+'.'}},
        outcome,diagnostic_action='hover'),'archaeology_tooltip_pass')


def suite(t):
    actors.session_entry(t.fixture);t.clean_panels();baseline=native();t.receipt['baseline']=baseline;t.persist()
    earned=None
    try:
        chosen=next((r for r in contracts(baseline) if r['name']=='Draenei' and r['sockets']>=1 and
            r['keystone'] and r['quantity']>=r['cost']-12 and r['item']),None)
        if not chosen:raise RuntimeError('requires an affordable current Draenei project with a keystone socket')
        stones=[r for r in baseline['inventory']['items'] if r[0]==t.fixture['guid'] and r[4]==chosen['keystone']]
        if len(stones)!=1 or stones[0][5]<2:raise RuntimeError('requires one existing Draenei keystone stack with a remainder')
        t.receipt['project_contracts']=[chosen];t.receipt['keystone_stack']=stones[0];t.persist()
        open_panel(t);select(t,chosen,catalog(t,'keystone_race_catalog'))
        toggle(t,chosen,baseline,True,'add');toggle(t,chosen,baseline,False,'remove')
        toggle(t,chosen,baseline,True,'solve_setup');solve(t,chosen,baseline,keystones=1)
        earned=native();t.clean_panels();completed_panel(t,'weighted_solve_history',earned)
        t.clean_panels();open_panel(t)
        require(click_case(t,'archaeology.tooltip_history','Open the completed artifacts tab.',
            lambda c:c['name']=='ArchaeologyFrameCompletedButton',
            lambda b,a,s:{'status':'archaeology_history_open_pass' if s else 'client_or_protocol_failure'}),
            'archaeology_history_open_pass')
        tooltip(t,chosen,earned)
    finally:
        t.clean_panels();after=native();t.receipt.update(native_after=after,
            earned_state_retained=earned is not None and after==earned);t.persist()
        if earned is not None and after!=earned:raise RuntimeError('earned weighted-solve state changed during read-only checks')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
