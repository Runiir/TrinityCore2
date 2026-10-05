"""Roundtrip requested stock colorblind and mouse-enable checkboxes."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial
from .interaction_settings_booleans import suite as boolean_suite
from .interaction_keybindings_native import suite as native_suite


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--setting',choices=['colorblindMode','enableMouseSpeed'],action='append');a=p.parse_args()
    variables=a.setting or ['colorblindMode']
    if len(set(variables))!=len(variables):p.error('each setting may be requested once')
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:
            state,_=t.observe('accessibility_observer_guard')
            if state.get('observer_version',0)<107:raise RuntimeError('requires read-only settings observer107')
            native_suite(t,operations=lambda t:boolean_suite(t,variables),preserve_settings=False)
            t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
