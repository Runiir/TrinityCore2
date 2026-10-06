"""Let Laya validate two stationary mount toggles with recorded cast feedback."""
import argparse
import shutil
import time
from pathlib import Path
from . import runtime,observe,farm_actions,action_queue,laya_ui


def run(output):
    output=output.resolve()
    if not output.is_relative_to(runtime.ROOT/'evidence'):raise ValueError('validation must use owned evidence')
    output.mkdir(parents=True,exist_ok=False)
    source=runtime.REPO/'tools/live_whitemane/addon/WhitemaneLiveObserver/Activity.lua'
    installed=Path.home()/'Games/_whitemane-60895_/Interface/AddOns/WhitemaneLiveObserver/Activity.lua'
    receipt={'started_at':time.time(),'gameplay_owner':'Laya','commands':[]}
    runtime.write(output/'receipt.json',receipt)
    try:
        runtime.monitor()
        shutil.copy2(source,installed)
        before=observe.observe(output/'before.png')
        reloaded=farm_actions.command_choice(output/'reload',before,'/reload',
            'Load cast timing telemetry for the supervised archaeology controller',
            'Reload the UI to activate the installed cast timing telemetry')
        receipt['reload']=reloaded
        if not reloaded['executed']:raise RuntimeError('Laya did not select the addon reload')
        row=observe.observe(output/'loaded.png')
        receipt['telemetry']={key:row['farm_ui'].get(key) for key in ('casting','gcd','mount_binding')}
        runtime.write(output/'receipt.json',receipt)
        if not row['farm_ui'].get('mount_binding'):raise RuntimeError('new mount binding telemetry is unavailable')
        initial_mounted=row['archaeology']['mounted']
        for index in range(2):
            a,m=row['archaeology'],row['movement']
            if a['flying'] or a['falling'] or m['in_combat'] or m['speed']:
                raise RuntimeError('stationary ground mount validation interrupted')
            action='dismount' if a['mounted'] else 'mount'
            choice,request,response=laya_ui.choose({
                'goal':'Validate the mount toggle with observed cast completion, then restore the initial mounted state',
                'mounted':a['mounted'],'flying':a['flying'],'combat':m['in_combat'],
                'stationary':m['speed']==0,'mount_binding':row['farm_ui']['mount_binding'],
                'test_command':index+1,'initial_mounted':initial_mounted},
                'Choose the mount toggle for this stationary supervised test, or wait.',
                {action:'Press Shift+Space to '+action,'wait':'Wait without input'})
            decision={'choice':choice,'request':request,'response':response}
            receipt['commands'].append(decision);runtime.write(output/'receipt.json',receipt)
            if choice=='wait':break
            decision['result']=action_queue.run(output/f'command_{index}',row,action,
                lambda _:farm_actions.inputs.execute('World of Warcraft','key',{'key':'shift+space','hold':.15}),
                lambda current:current['archaeology']['mounted']==(action=='mount'),observe.observe,
                uses_gcd=action=='mount',
                allowed=lambda current:not current['archaeology']['flying'] and not current['archaeology']['falling']
                    and not current['movement']['in_combat'] and current['movement']['speed']==0)
            row=decision['result']['after'];runtime.write(output/'receipt.json',receipt)
        receipt.update(completed=len(receipt['commands'])==2 and all(c.get('result',{}).get('completed') for c in receipt['commands']),
            restored_mounted_state=row['archaeology']['mounted']==initial_mounted)
    except Exception as error:
        receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
    finally:
        receipt['finished_at']=time.time();runtime.write(output/'receipt.json',receipt)
    return receipt


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    receipt=run(parser.parse_args().output)
    print(json.dumps({key:receipt.get(key) for key in ('completed','failure','restored_mounted_state','telemetry')}
        | {'laya_choices':[c['choice'] for c in receipt['commands']]}))
