"""Cancel a stock exit confirmation, then discard one unapplied render change."""
import argparse,json,re,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_render_scale import scale,value_checks,pending_step,restore
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite


def dialog(probe):
    rows=probe.get('discard_dialogs') or []
    if (not isinstance(rows,list) or len(rows)!=1 or rows[0].get('which')!='GAME_SETTINGS_CONFIRM_DISCARD'
            or not re.fullmatch(r'StaticPopup[1-3]',rows[0].get('name',''))):
        raise RuntimeError('requires one observed stock unapplied-settings exit confirmation')
    return rows[0]['name']


def open_exit(t,label):
    control=target(t,label+'_close',lambda c:c['kind']=='Button' and c['text']=='Close' and c['enabled'])
    def outcome(b,a,s):
        current=detail(t,label+'_dialog',lambda p:bool(p.get('discard_dialogs')));name=dialog(current)
        checks=value_checks(current,t.render_layout,t.original,t.lower,True)
        checks.update(ordinary_close=s=='click',settings_visible=current['visible'] is True,
            observed_popup=name in a['panels'],ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status':'stock_settings_exit_dialog_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'popup_name':name}}
    require(t.step(label,'Open the stock exit confirmation for the unapplied render setting.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click'),
        'stock_settings_exit_dialog_pass')


def select(t,index,label):
    if type(index) is not int or index not in (1,3):raise ValueError('only Cancel or Discard and Exit is permitted')
    before=detail(t,label+'_before');name=dialog(before)
    if not all(value_checks(before,t.render_layout,t.original,t.lower,True).values()):
        raise RuntimeError('exit choice requires the exact unapplied render fixture')
    control=target(t,label+'_button',lambda c:c['kind']=='Button' and c['name']==name+'Button'+str(index)
        and c['enabled'])
    if index==1:t.receipt['discard_attempted']=True;t.persist()
    wanted=t.lower if index==3 else t.original
    def outcome(b,a,s):
        current=detail(t,label+'_result',lambda p:not p.get('discard_dialogs') and
            abs(scale(p)[1]-wanted)<1e-6 and p.get('visible') is (index==3))
        checks=value_checks(current,t.render_layout,t.original,wanted,index==3)
        checks.update(ordinary_dialog_choice=s=='click',dialog_closed=not current.get('discard_dialogs'),
            settings_visible=current.get('visible') is (index==3),
            ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status':'stock_settings_exit_choice_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'button_index':index,'public':current}}
    require(t.step(label,'Use the observed stock '+('Cancel' if index==3 else 'Discard and Exit')+' choice.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click'),
        'stock_settings_exit_choice_pass')


def suite(t):
    state,_=t.observe('discard_fixture')
    if state.get('observer_version',0)<116:raise RuntimeError('requires read-only settings observer116')
    t.receipt.update(custom_script_permission='blocked_by_user',qualified_scope='Owned primary: lower pending render-scale step without Apply, Close confirmation Cancel preserving the pending change, then Close and Discard and Exit restoring the original public CVar and proxy without applying the change. Original settings layout and native fixture restore. Other discard dialogs, defaults and persistence remain open.');t.persist()
    t.settings_search=open_search(t);layout=detail(t,'discard_layout_baseline');t.render_layout=layout
    t.original,pending=scale(layout)
    if layout.get('unapplied') is not False or abs(t.original-pending)>=1e-6 or layout.get('discard_dialogs'):
        raise RuntimeError('requires a clean applied render-scale fixture')
    t.receipt['render_layout_baseline']=layout;t.persist()
    try:
        search(t,'Render Scale','settings.cancel.render_scale_search')
        t.lower=pending_step(t,-1,'settings.cancel.render_scale_pending')
        t.receipt['discard_pending_scale']=t.lower;t.persist()
        open_exit(t,'settings.cancel.exit_dialog')
        select(t,3,'settings.cancel.keep_pending')
        open_exit(t,'settings.cancel.exit_dialog_again')
        select(t,1,'settings.cancel.discard_pending')
    finally:
        current=detail(t,'discard_cleanup_before')
        if current.get('discard_dialogs'):
            if t.receipt.get('discard_attempted'):raise RuntimeError('failed discard is not replayed during cleanup')
            select(t,1,'fixture.settings_discard.cleanup_exit')
            current=detail(t,'discard_cleanup_closed')
        if not current.get('visible'):
            t.clean_panels();t.settings_search=open_search(t)
        restore(t,layout)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=suite,preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt[k] for k in ['completed','failure']}),flush=True)


if __name__=='__main__':main()
