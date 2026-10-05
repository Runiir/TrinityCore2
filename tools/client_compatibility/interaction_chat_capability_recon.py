"""Inspect stock chat capability controls without activating services or reports."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_chat_window import detail,recon
from .interaction_chat_settings import signature
from .interaction_operations import controls
from .interaction_chat_language import click
from .interaction_keybindings_native import suite as native_suite


def play(t):
    before=detail(t,'capability_original')
    t.receipt['capability_baseline']=before;t.persist()
    try:
        catalog=controls(t);state,frame=t.observe('capability_visible_stock_controls')
        t.receipt['capability_visible']={'controls':catalog,'state':state,'frame':frame};t.persist()
        recon(t)
        click(t,'fixture.capability_root_menu',lambda c:c['name']=='ChatFrameMenuButton')
        catalog=controls(t);state,frame=t.observe('capability_root_menu')
        t.receipt['capability_root_menu']={'controls':catalog,'state':state,'frame':frame};t.persist()
    finally:
        t.clean_panels();after=detail(t,'capability_restored')
        checks={'chat_settings':signature(before)==signature(after),
            'channels':before['channels']==after['channels'],
            'languages':before['languages']==after['languages'],'voice':before['voice']==after['voice']}
        t.receipt['capability_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('capability inspection changed public chat state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    t=Trial(p.parse_args().output,controller='code')
    try:native_suite(t,operations=play,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure']}),flush=True)
