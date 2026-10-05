"""Laya uses only the user-authorized key 1 until the current combat clears."""
import json
import time
from . import runtime,inputs,laya_ui
from .observe import observe


def ready(row):
    c=(row.get('farm_ui') or {}).get('combat') or {}
    return (row['movement']['in_combat'] and not row['movement']['dead'] and c.get('target_exists')
        and c.get('hostile') and not c.get('target_dead') and c.get('attack_usable')
        and c.get('attack_in_range') not in (False,0)
        and c.get('cooldown_ends',0)<=row['farm_ui']['uptime']
        and not row['archaeology']['casting'])


def run(folder):
    folder.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();last_progress=start;last_health=None;last_press=0;count=0
    result={'started_at':time.time(),'action':'key 1 only','casts':0,'completed':False}
    runtime.write(folder/'combat.json',result)
    while True:
        row=observe(folder/'latest.png');m=row['movement'];c=(row.get('farm_ui') or {}).get('combat') or {}
        if (runtime.ROOT/'run/stop_dig').exists() or m['dead'] or not m['in_world']:
            raise RuntimeError('combat interrupted by supervisor or unavailable player')
        if not m['in_combat']:
            result.update(completed=True,finished_at=time.time());runtime.write(folder/'combat.json',result);return result
        health=c.get('target_health')
        if health is not None and (last_health is None or health<last_health):last_progress=time.monotonic()
        last_health=health
        if time.monotonic()-last_progress>30:raise RuntimeError('key-1 combat has made no target-health progress for 30 seconds')
        # Cooldown and energy readiness are local reads. No failed-cast spam.
        if not ready(row) or time.monotonic()-last_press<1:
            time.sleep(.1);continue
        state={'goal':'End combat using Sinister Strike on the current target',
            'combat':True,'hostile_target_alive':True,'Sinister_Strike_ready':True,'target_in_range':True}
        action,request,response=laya_ui.choose(state,'Use key 1 on the current target while combat is active.',
            {'attack':'Press 1 for Sinister Strike','wait':'Wait without input'})
        decision={'at':time.time(),'choice':action,'request':request,'response':response,'executed':False}
        if action=='attack':
            fresh=observe(folder/'precheck.png')
            if fresh['runtime']!=row['runtime'] or not ready(fresh):continue
            decision['input']=inputs.execute('World of Warcraft','key',{'key':'1','hold':.15})
            decision['executed']=True;last_press=time.monotonic();count+=1
        with (folder/'decisions.jsonl').open('a') as handle:handle.write(json.dumps(decision)+'\n')
        result['casts']=count;runtime.write(folder/'combat.json',result)
        time.sleep(.1)
