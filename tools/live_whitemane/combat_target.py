"""Laya selects a target or one retained client-native approach before key 1."""
import json
import math
import time
from . import inputs,laya_ui,runtime,action_queue
from .observe import observe
from tools.client_compatibility.interaction_trial import binding_key


def living(row):
    c=row['farm_ui'].get('combat') or {}
    engaged=c.get('target_engaged')
    if engaged is None:engaged=c.get('target_attacks_player')
    return bool(c.get('target_exists') and c.get('hostile') and not c.get('target_dead')
        and engaged is True)


class TargetApproach:
    def __init__(self):
        self.active=None;self.last_command=-math.inf

    def tick(self,folder,row,result):
        c=row['farm_ui'].get('combat') or {};now=time.monotonic()
        target=c.get('target_guid');world=row['archaeology'].get('world')
        outside=c.get('attack_in_range') in (False,0)
        if living(row) and not outside:
            if self.active:
                self.active.update(reached_melee_range=True,finished_at=time.time())
                self.active=None
            return False
        if action_queue.busy(row):return True
        if self.active:
            if not living(row) or target!=self.active['target_guid']:self.active=None
            else:
                old=self.active['last_world']
                if world and old and world['instance']==old['instance'] and math.hypot(
                        world['north']-old['north'],world['west']-old['west'])>.25:
                    self.active.update(last_world=world,last_progress=now)
                if now-self.active['last_progress']>5:
                    raise RuntimeError('combat target approach made no movement or range progress')
                return True
        if now-self.last_command<1:return True
        bindings=row['farm_ui'].get('bindings') or {}
        options={'wait':'Wait here'}
        attackers=[enemy for enemy in c.get('attackers') or []
            if enemy.get('guid') and enemy.get('name') and 0<enemy.get('x',0)<1 and 0<enemy.get('y',0)<1]
        if not living(row):
            options.update({f'target_attacker_{index}':'Select the observed attacker '+enemy['name']
                for index,enemy in enumerate(attackers)})
        elif outside and bindings.get('INTERACTTARGET'):
            if c.get('click_to_move')=='1':options['approach']='Interact with the selected hostile target to move into melee range'
        state={'task':'Reach melee range of the selected hostile target','combat':True,
            'target_alive':living(row),'in_melee_range':not outside if living(row) else None,
            'click_to_move':c.get('click_to_move')=='1','target_name':c.get('target_name'),
            'target_attacks_player':living(row),'observed_attackers':[enemy['name'] for enemy in attackers]}
        result['target_facts']=state
        if len(options)==1:return True
        action,request,response=laya_ui.choose(state,
            'Select a mob observed attacking this player. Move into melee range before using Sinister Strike.',options)
        decision={'at':time.time(),'choice':action,'request':request,'response':response,'executed':False}
        fresh=observe(folder/'target_precheck.png')
        fresh_c=fresh['farm_ui'].get('combat') or {}
        valid=(fresh['runtime']==row['runtime'] and fresh['movement']['in_combat']
            and not fresh['movement']['dead'] and fresh_c.get('target_guid')==target
            and not action_queue.busy(fresh) and not any(fresh['archaeology'].get(k)
                for k in ('mounted','flying','falling')))
        if not valid:return True
        if action=='approach' and (not living(fresh) or fresh_c.get('attack_in_range') not in (False,0)):
            return True
        if action.startswith('target_attacker_'):
            enemy=attackers[int(action.rsplit('_',1)[1])]
            current=next((item for item in fresh_c.get('attackers') or [] if item.get('guid')==enemy['guid']),None)
            if not current:return True
            decision['selected_attacker']=current
            decision['input']=inputs.execute('World of Warcraft','click',
                {'x':round(current['x']*runtime.WIDTH),'y':round(current['y']*runtime.HEIGHT),'button':1})
        if action=='approach':
            key=binding_key(bindings['INTERACTTARGET'][0])
            decision['input']=inputs.execute('World of Warcraft','key',{'key':key,'hold':.15})
            if action=='approach':
                self.active={'target_guid':target,'last_world':world,'last_progress':time.monotonic(),
                    'selected_at':decision['at'],'request':request,'response':response,'reached_melee_range':False}
                result.setdefault('approaches',[]).append(self.active);del result['approaches'][:-8]
        decision['executed']=action!='wait';self.last_command=time.monotonic()
        with (folder/'decisions.jsonl').open('a') as handle:handle.write(json.dumps(decision)+'\n')
        runtime.write(folder/'combat.json',result)
        return True
