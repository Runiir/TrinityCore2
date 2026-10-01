"""Bounded keyboard melee recovery for incidental low-level digsite attackers."""
import json
import math
import re
import time
from . import lab_runtime as lab, archaeology_inputs, ground_navigation, site_boundaries
from .travel_inputs import face
from tools.second_client import ctl


def run(movement, extra, facts, observer, path):
    if extra['mounted']: raise RuntimeError('melee recovery requires a grounded unmounted character')
    ctl._launcher_env = lab.client_environment; inputs = ctl.Input()
    site = site_boundaries.active_site(facts['map'], facts['position'], extra['digsite_ids'])
    receipt = {'decision_origin': 'physical_safety_guard', 'reason': 'incidental combat blocks Survey',
        'before': facts, 'steps': [], 'started_at': time.time(), 'learned_combat_policy': False}
    evidence = path.with_suffix('.combat.json')
    def record(kind, **values):
        receipt['steps'].append({'time': time.time(), 'kind': kind, **values})
        lab.private_write(evidence, json.dumps(receipt, indent=2)+'\n')
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            movement, extra = archaeology_inputs.screenshot(path); facts = observer.poll()
            if movement['dead'] or movement['health_percent'] < 50: raise RuntimeError('melee recovery lost safe health')
            if not movement['in_combat']:
                receipt.update(after=facts, finished_at=time.time(), completed=True, still_mounted=False)
                lab.private_write(evidence, json.dumps(receipt, indent=2)+'\n')
                return receipt
            target = facts['selected_unit']
            hostiles = {h['guid'] for h in facts['visible_hostiles']}
            if not target or not target['health'] or target['guid'] not in hostiles or math.dist(facts['position'][:2],target['position'][:2])>12:
                attackers=[h for h in facts['visible_hostiles'] if h['guid'] in facts['attacking_units']]
                keys=[]
                if attackers:
                    nearest=min(attackers,key=lambda h:math.dist(facts['position'][:2],h['position'][:2]))
                    if math.dist(facts['position'][:2],nearest['position'][:2])>.5:
                        keys.extend(face(inputs,observer,nearest['position']))
                    name=facts['visible_unit_names'].get(nearest['guid'])
                else:name=None
                # This is the normal local WoW targeting command, typed through
                # the client. Its name comes from an ordinary creature query.
                # It avoids Tab skipping an attacker behind terrain/camera.
                if name and re.fullmatch("[A-Za-z '-]{1,100}",name):
                    command='/targetexact '+name
                    inputs.key('Return');inputs.type(command);inputs.key('Return')
                    keys.append({'local_client_command':command,'source':'ordinary visible creature query'})
                else:
                    inputs.key('Tab');keys.append({'key':'Tab'})
                record('select', physical_keys=keys); time.sleep(.4)
                continue
            distance = math.dist(facts['position'][:2], target['position'][:2])
            if distance > 12:
                inputs.key('Tab'); record('select', physical_keys=[{'key': 'Tab'}], rejected_distance=distance); time.sleep(.4)
                continue
            keys = face(inputs, observer, target['position'])
            if distance > 4:
                route = ground_navigation.route(facts['map'], facts['position'], target['position'])
                goal = next((p for p in route['points'] if math.dist(p[:2], facts['position'][:2])>1), None)
                if goal and site_boundaries.inside_segment(site['polygon'], facts['position'], goal):
                    keys.extend(face(inputs, observer, goal))
                    hold = min(.7, max(.05, (distance-3)/7))
                    inputs.key('w', hold=hold); keys.append({'key':'w','hold':hold})
            # Slot 1 is the provisioned Attack spell; repeated presses start
            # melee rather than invoking a privileged backend combat action.
            inputs.key('1'); keys.append({'key':'1'}); time.sleep(1.2)
            after = observer.poll(); record('melee', target_before=target,
                target_after=after['selected_unit'], physical_keys=keys)
            if not site_boundaries.contains(site['polygon'], after['position']):
                raise RuntimeError('melee recovery left the public digsite boundary')
        raise RuntimeError('bounded melee recovery did not clear combat')
    except Exception as error:
        receipt.update(finished_at=time.time(), completed=False, failure=f'{type(error).__name__}: {error}')
        lab.private_write(evidence, json.dumps(receipt, indent=2)+'\n')
        raise
