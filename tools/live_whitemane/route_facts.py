"""Attach the current addon leg and comparable public fares to legal choices."""
import math


def distance(a,b):
    if not a or not b or a.get('instance')!=b.get('instance'):return math.inf
    return math.hypot(a['north']-b['north'],a['west']-b['west'])


def describe(route,options):
    kind=route.get('kind');origin=route.get('origin') or {};exit=route.get('exit') or {}
    current=route.get('fare_copper')
    result={'kind':kind,'instruction':route.get('instruction'),
        'flight_master':origin.get('master_name') or origin.get('name'),
        'flight_destination':exit.get('name'),'fare_copper':current,
        'actions':{}}
    choices=dict(options)
    for key,(label,target) in choices.items():
        matching=(key=='flight' and kind in ('taxi','site','portal') or key=='taxi' and kind=='taxi'
            or key=='portal' and kind=='portal' or key=='teleport' and kind=='shortcut')
        facts={'follows_addon_next_leg':bool(matching)}
        if matching and kind=='taxi':
            native=label.startswith('Right-click')
            facts['native_approach_available']=native
            label=('Right-click ' if native else 'Reach flight master ' if key=='flight' else 'Take the flight from ')+str(result['flight_master'])
            label+=' for '+str(exit.get('name'))
            if native:label+='; client approaches and opens taxi'
            if current is not None:label+=f'; known fare {current} copper'
        if key.startswith(('portal_','flight_portal_')) and target:
            portal=(target if target.get('to') else next((p for p in route.get('known_portals',[])
                if key=='flight_portal_'+p.get('key','')),{}))
            fares=[f for f in route.get('fare_options',[]) if f.get('exit_id')==exit.get('id')
                and distance(portal.get('to'),f.get('origin_point'))<=1500]
            if fares:
                fare=min(fares,key=lambda f:distance(portal.get('to'),f['origin_point']))
                price=fare['fare_copper']
                facts.update(alternate_origin= fare.get('origin_name'),fare_copper=price,
                    fare_source=fare.get('fare_source'),same_flight_destination=exit.get('name'),
                    more_expensive_than_addon_route=current is not None and price>current)
                # Laya's installed formatter limits each option to 48
                # tokens. Keep the label short; retain all price facts in
                # state, where the expanded context can carry them intact.
                label=('Fly to ' if key.startswith('flight_') else 'Use ')+str(portal.get('destination'))+' portal'
                label+=f'; onward {exit.get("name")} flight costs {price} copper'
                if current is not None:label+=f' versus {current} on the addon route'
        result['actions'][key]=facts
        choices[key]=(label,target)
    result['task']=('Reach flight master '+str(result['flight_master'])+' and fly to '+str(exit.get('name'))
        if kind=='taxi' else route.get('instruction'))
    return result,choices
