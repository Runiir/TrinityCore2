"""Inspect stock Master Volume controls before reversible numeric setting trials."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_profession_recipes import RecipeTrial
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search
from .interaction_control_target import target
from .interaction_operations import controls,point
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite


class SettingsTrial(RecipeTrial):
    def step(self,case_id,goal,actions,oracle,**kwargs):
        actions={k:{**v,'hold':max(v.get('hold',0),1.2)} if v['kind']=='key' and v['value'] in ('Escape','Return') else v
            for k,v in actions.items()}
        return super().step(case_id,goal,actions,oracle,**kwargs)


def click_control(t,label,control,ready,status):
    t.io.move(*point(control));time.sleep(1)
    require(t.step(label,'Use the observed stock settings control.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},
        lambda b,a,s:{'status':status if s=='click' and ready(a) and not a.get('lua_errors') and
            not a.get('blocked_actions') else 'client_or_protocol_failure'},diagnostic_action='click',await_state=ready),status)


def inspect(t):
    layout=None
    try:
        t.settings_search=open_search(t);layout=detail(t,'volume_layout_baseline')
        t.receipt['volume_layout_baseline']=layout;t.persist()
        if layout.get('unapplied'):raise RuntimeError('original settings contain unapplied changes')
        search(t,'Master Volume','fixture.find_master_volume')
        current=detail(t,'master_volume_rendered');rows=controls(t);state,frame=t.observe('master_volume_recon')
        t.receipt['volume_recon']={'settings':current,'controls':rows,'state':state,'frame':frame,
            'qualified':False,'scope':'Read-only control reconnaissance. No volume mutation or qualification.'};t.persist()
        matches=[c for c in rows if c.get('setting_variable')=='Sound_MasterVolume']
        if not matches:raise RuntimeError('stock Master Volume setting controls are absent')
    finally:
        if layout is not None:
            search(t,layout.get('search') or '','fixture.restore_volume_search')
            current=detail(t,'volume_layout_restore_before')
            if current.get('category')!=layout.get('category'):
                name=layout['category']['name']
                control=target(t,'fixture.restore_volume_category',lambda c:c['text']==name or c['text'].startswith(name+'|T'))
                click_control(t,'fixture.restore_volume_category',control,lambda a:
                    detail(t,'volume_category_restored')['category']==layout['category'],'settings_category_restored')
            current=detail(t,'volume_layout_restored')
            checks={k:current.get(k)==layout.get(k) for k in ('search','category','cvars','values','unapplied')}
            t.receipt['volume_layout_restoration']={'checks':checks};t.persist()
            if not all(checks.values()):raise RuntimeError('original volume settings layout differs')
            close=target(t,'fixture.close_volume_recon',lambda c:c['kind']=='Button' and c['text']=='Close')
            click_control(t,'fixture.close_volume_recon',close,lambda a:'SettingsPanel' not in a['panels'],
                'settings_panel_closed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=inspect,preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
