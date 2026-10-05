"""Roundtrip stock Move Pad and Interact Key settings with rendered outcomes."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,restore_layout
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search
from .interaction_control_target import target
from .interaction_operations import point,controls
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite

SPECS={'enableMovePad':('Move Pad','settings.interface',True),
    'PROXY_ENABLE_INTERACT':('Interact Key','settings.keyboard_controls',False)}


def agrees(probe,variable,wanted):
    if type(wanted) is not bool:raise ValueError('requires a boolean target')
    actual=probe.get('values',{}).get(variable)
    return type(actual) is bool and actual==wanted and (
        not SPECS[variable][2] or probe.get('cvars',{}).get(variable)==str(int(wanted)))


def toggle(t,layout,variable,wanted,label):
    control=target(t,label+'_target',lambda c:c['kind']=='CheckButton' and c.get('enabled') and
        c.get('setting_variable')==variable)
    if type(control.get('checked')) is not bool or control['checked']==wanted:
        raise RuntimeError('stock checkbox is not in the opposite original state')
    t.io.move(*point(control));time.sleep(1)
    def outcome(b,a,s):
        after=detail(t,label+'_value',lambda p:agrees(p,variable,wanted))
        rendered=target(t,label+'_checked',lambda c:c['kind']=='CheckButton' and
            c.get('setting_variable')==variable and c.get('checked')==wanted and c.get('setting_value')==wanted)
        rows=controls(t) if variable=='enableMovePad' else []
        state,frame=t.observe(label+'_rendered')
        checks={'ordinary_checkbox':s=='click','public_setting':agrees(after,variable,wanted),
            'rendered_checkbox':rendered['checked']==wanted and rendered['setting_value']==wanted,
            'interact_binding_preserved':after['interact_keys']==layout['interact_keys'],
            'no_pending_changes':after['unapplied']==layout['unapplied'],
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        if variable=='enableMovePad':
            pad=[c for c in rows if c.get('name','').startswith('MovePad') and c['kind']=='Button']
            checks.update(move_pad_visible=after['move_pad_visible']==wanted,
                move_pad_buttons=len(pad)>=4 if wanted else not pad)
        return {'status':'stock_control_setting_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'variable':variable,'expected':wanted,'public':after,
                'checkbox':rendered,'controls':rows,'state':state,'frame':frame}}
    require(t.step(label,'Change the observed stock '+SPECS[variable][0]+' checkbox and verify its rendered outcome.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click'),
        'stock_control_setting_pass')


def suite(t,variables):
    layout=None;attempted=[]
    t.receipt['qualified_scope']='Requested stock Move Pad/Interact Key enable checkboxes changed and reversed. Move Pad visibility/buttons and Interact Target binding are checked; all observed settings/layout and the native fixture restore. Pad movement, NPC interaction, binding assignment and reconnect persistence remain open.';t.persist()
    try:
        t.settings_search=open_search(t);layout=detail(t,'control_layout_baseline')
        t.receipt['control_layout_baseline']=layout;t.persist()
        keys=layout.get('interact_keys',{})
        if (layout.get('unapplied') or not isinstance(keys,dict) or keys.get('known') is not True or
            not all(isinstance(keys.get(k),str) for k in ('primary','secondary'))):
            raise RuntimeError('requires a clean settings layout and complete Interact Target key observation')
        for variable in variables:
            original=layout['values'].get(variable)
            if type(original) is not bool or not agrees(layout,variable,original):
                raise RuntimeError('original public stock control setting is unavailable or disagrees')
            if variable=='enableMovePad' and layout.get('move_pad_visible')!=original:
                raise RuntimeError('original Move Pad visibility disagrees with its setting')
        for variable in variables:
            term,operation,_=SPECS[variable];search(t,term,operation+'.search')
            attempted.append(variable);t.receipt['attempted_settings']=attempted.copy();t.persist()
            toggle(t,layout,variable,not layout['values'][variable],operation+'.change')
            toggle(t,layout,variable,layout['values'][variable],operation+'.restore')
    finally:
        if layout is not None:
            current=detail(t,'control_cleanup_guard')
            for variable in attempted:
                original=layout['values'][variable]
                if agrees(current,variable,original):continue
                term,operation,_=SPECS[variable];search(t,term,operation+'.cleanup_search')
                toggle(t,layout,variable,original,operation+'.cleanup_restore')
                current=detail(t,operation+'_cleanup_confirmed')
            restore_layout(t,layout,'fixture.restore_stock_controls')
            t.receipt['settings_layout_restoration']=t.receipt.pop('volume_layout_restoration')
            after=detail(t,'control_final_settings')
            checks={'interact_binding':after['interact_keys']==layout['interact_keys'],
                'move_pad':after['move_pad_visible']==layout['move_pad_visible']}
            t.receipt['control_restoration_checks']=checks;t.persist()
            if not all(checks.values()):raise RuntimeError('original Move Pad or Interact Target binding differs')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--setting',choices=list(SPECS),action='append',required=True);a=p.parse_args()
    if len(set(a.setting))!=len(a.setting):p.error('each setting may be requested once')
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:
            state,_=t.observe('stock_control_observer_guard')
            if state.get('observer_version',0)<108:raise RuntimeError('requires read-only settings observer108')
            native_suite(t,operations=lambda t:suite(t,a.setting),preserve_settings=False)
            t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
