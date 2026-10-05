"""Inspect requested stock setting controls and restore the original layout."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,restore_layout
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail,search
from .interaction_operations import controls
from .interaction_keybindings_native import suite as native_suite

TERMS=('Mouse','Colorblind','Move Pad','Interact Key','Graphics','Render Scale',
    'View Distance','Ground Clutter','Resolution','Window Mode','Monitor')


def inspect(t,terms):
    layout=None
    t.receipt['qualified_scope']='Control reconnaissance only. Search and inspect requested stock controls, then restore the settings layout and native fixture. No setting mutation or gameplay qualification.'
    t.receipt['custom_script_permission']='blocked_by_user';t.persist()
    try:
        t.settings_search=open_search(t);layout=detail(t,'settings_layout_baseline')
        t.receipt['settings_layout_baseline']=layout;t.persist()
        if layout.get('unapplied'):raise RuntimeError('original settings contain unapplied changes')
        for index,term in enumerate(terms):
            label=f'settings_recon_{index:02}'
            search(t,term,label+'_search');current=detail(t,label+'_detail')
            rows=controls(t);state,frame=t.observe(label+'_rendered')
            t.receipt.setdefault('settings_recon',[]).append({'term':term,'settings':current,
                'controls':rows,'state':state,'frame':frame,'qualified':False});t.persist()
    finally:
        if layout is not None:
            restore_layout(t,layout,'fixture.restore_settings_recon')
            t.receipt['settings_layout_restoration']=t.receipt.pop('volume_layout_restoration');t.persist()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--term',choices=TERMS,action='append',required=True);a=p.parse_args()
    if len(set(a.term))!=len(a.term):p.error('each search term may be requested once')
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=lambda t:inspect(t,a.term),preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
