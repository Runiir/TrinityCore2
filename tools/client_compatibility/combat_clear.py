"""Bounded keyboard melee recovery for incidental low-level digsite attackers."""
import json
import math
import re
import time
from . import lab_runtime as lab, archaeology_inputs, ground_navigation, site_boundaries
from .travel_inputs import face
from tools.second_client import ctl


def named_target_command(facts,name,failed_selections):
    if not name or not re.fullmatch("[A-Za-z '-]{1,100}",name) or failed_selections>2:return None
    if sum(value==name for value in facts['visible_unit_names'].values())!=1:return None
    return '/targetexact '+name


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
        failed_selections=0
        while time.monotonic() < deadline:
            movement, extra = archaeology_inputs.screenshot(path); facts = observer.poll()
            if movement['dead'] or movement['health_percent'] < 50: raise RuntimeError('melee recovery lost safe health')
            if not movement['in_combat']:
                receipt.update(after=facts, finished_at=time.time(), completed=True, still_mounted=False)
                lab.private_write(evidence, json.dumps(receipt, indent=2)+'\n')
                return receipt
            target = facts['selected_unit']
            hostiles = {h['guid'] for h in facts['visible_hostiles']}
            limit=45 if target and target['guid'] in facts['attacking_units'] else 12
            if not target or not target['health'] or target['guid'] not in hostiles or math.dist(facts['position'][:2],target['position'][:2])>limit:
                failed_selections+=1
                attackers=[h for h in facts['visible_hostiles'] if h['guid'] in facts['attacking_units']]
                keys=[]
                if attackers:
                    nearest=min(attackers,key=lambda h:math.dist(facts['position'][:2],h['position'][:2]))
                    if math.dist(facts['position'][:2],nearest['position'][:2])>.5:
                        keys.extend(face(inputs,observer,nearest['position']))
                    name=facts['visible_unit_names'].get(nearest['guid'])
                else:name=None
                if failed_selections in [3,6,9]:
                    current=observer.poll()['position'];hold=.8
                    goal=[current[0]-math.cos(current[3])*hold*4.5,
                        current[1]-math.sin(current[3])*hold*4.5,current[2]]
                    if site_boundaries.inside_segment(site['polygon'],current,goal):
                        ground_navigation.route(facts['map'],current,goal)
                        inputs.key('s',hold=hold);keys.append({'key':'s','hold':hold,'reason':'open a blocked attacker approach'})
                        time.sleep(.3)
                # This is the normal local WoW targeting command, typed through
                # the client. Its name comes from an ordinary creature query.
                # It avoids Tab skipping an attacker behind terrain/camera.
                command=named_target_command(facts,name,failed_selections)
                if command:
                    inputs.key('Return');inputs.type(command);inputs.key('Return')
                    keys.append({'local_client_command':command,'source':'ordinary visible creature query'})
                else:
                    if facts['selected_unit']:
                        inputs.key('Return');inputs.type('/cleartarget');inputs.key('Return')
                        keys.append({'local_client_command':'/cleartarget','reason':'reset an unsuitable or ambiguous selection'})
                    inputs.key('Tab');keys.append({'key':'Tab'})
                record('select', physical_keys=keys); time.sleep(.4)
                continue
            failed_selections=0
            # Unit::IsWithinMeleeRange measures XYZ with a minimum five-yard
            # reach. Trial 46 needlessly routed toward a 4.7-yard attacker.
            distance = math.dist(facts['position'][:3], target['position'][:3])
            keys = face(inputs, observer, target['position'])
            if distance > 5:
                route = ground_navigation.route(facts['map'], facts['position'], target['position'])
                goal = next((p for p in route['points'] if math.dist(p[:2], facts['position'][:2])>1), None)
                if goal and site_boundaries.inside_segment(site['polygon'], facts['position'], goal):
                    keys.extend(face(inputs, observer, goal))
                    hold = min(.7, math.dist(goal[:2],facts['position'][:2])/7, max(.05, (distance-3)/7))
                    inputs.key('w', hold=hold); keys.append({'key':'w','hold':hold})
            # Slot 1 is the provisioned Attack spell; repeated presses start
            # melee rather than invoking a privileged backend combat action.
            if observer.poll()['player_attack_target']!=target['guid']:
                inputs.key('1'); keys.append({'key':'1'})
            time.sleep(1.2)
            after = observer.poll(); record('melee', target_before=target,
                target_after=after['selected_unit'], physical_keys=keys)
            if not site_boundaries.contains(site['polygon'], after['position']):
                raise RuntimeError('melee recovery left the public digsite boundary')
        raise RuntimeError('bounded melee recovery did not clear combat')
    except Exception as error:
        receipt.update(finished_at=time.time(), completed=False, failure=f'{type(error).__name__}: {error}')
        lab.private_write(evidence, json.dumps(receipt, indent=2)+'\n')
        raise
