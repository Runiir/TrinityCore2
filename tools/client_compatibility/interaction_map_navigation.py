"""Stock zone/continent map navigation and owned public digsite overlays."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial,binding_key
from .interaction_operations import command,click_case
from .interaction_macros import require
from .interaction_observation import read_page
from .interaction_archaeology_projects import native
from .observation.map_data import catalog as static_maps


def detail(t,label):
    try:
        state,frame=read_page(t,label,'map','/tcui map')
        t.receipt.setdefault('map_details',{})[label]={'state':state,'frame':frame};t.persist()
        return state['map_probe']
    finally:command(t,'/tcui state')


def nav_oracle(t,label,expected):
    probe=detail(t,label)
    checks={'visible':probe['visible'],'expected_map':probe['id']==expected,
        'native_preserved':native()==t.map_baseline}
    return {'status':'map_navigation_pass' if all(checks.values()) else 'client_or_protocol_failure',
        'oracle':{'checks':checks,'public':probe}}


def suite(t):
    actors.session_entry(t.fixture);t.clean_panels();t.map_baseline=native()
    t.receipt['native_baseline']=t.map_baseline;before=detail(t,'before_map')
    if not before.get('best') or not before.get('binding_keys'):
        raise RuntimeError('public player map/binding fixture is absent')
    zone=before['best'];parent=zone['parent'];key=binding_key(before['binding_keys'][0])
    if zone['type']!=3 or not parent:
        raise RuntimeError('requires an outdoor zone with a continent parent')
    t.receipt['map_fixture']={'zone':zone,'continent':parent,'digsites':before['digsites_enabled']};t.persist()
    try:
        require(t.step('map.bound_open','Open the world map through its binding.',
            {'map':{'kind':'key','value':key,'description':'Press the observed world-map binding.'}},
            lambda b,a,s:nav_oracle(t,'zone_open',zone['id']),diagnostic_action='map'),'map_navigation_pass')
        probe=detail(t,'zone_coordinates')
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT map,position_x,position_y,position_z FROM client442_characters.characters WHERE guid=%s',
                (t.fixture['guid'],));position=q.fetchone()
        public=probe.get('world_position') or [];normalized=probe.get('player') or {}
        matches=[r for r in static_maps()['world_map_areas'].values() if r['name']==zone['name'] and r['map']==position[0]]
        if len(matches)!=1:raise RuntimeError('player zone has no unique pinned native map rectangle')
        left,right,top,bottom=matches[0]['bounds']
        expected={'x':(position[2]-left)/(right-left),'y':(position[1]-top)/(bottom-top)}
        checks={'native_xy':len(public)>=2 and abs(public[0]-position[1])<.1 and abs(public[1]-position[2])<.1,
            'map_normalized':all(abs(normalized.get(k,-1)-v)<.0001 for k,v in expected.items()),
            'named_zone':probe['info']['name']==zone['name']}
        t.receipt['coordinates_oracle']={'checks':checks,'native_position':position,'public':probe,
            'native_map_rectangle':matches[0],'native_normalized_position':expected,
            'limits':'Public UnitPosition Z is not qualified by the planar coordinate check.'};t.persist()
        if not all(checks.values()):raise RuntimeError('public map planar coordinates differ from native/player zone')
        require(click_case(t,'map.continent_zoom_out','Zoom out to the continent.',
            lambda c:c['name']=='WorldMapZoomOutButton',
            lambda b,a,s:nav_oracle(t,'continent_open',parent)),'map_navigation_pass')
        continent=detail(t,'continent_digsites');ids=[r['id'] for r in continent['sites']]
        if not ids or len(ids)!=len(set(ids)):
            raise RuntimeError('public continent has no unique owned digsites')
        for enabled in [False,True]:
            current=detail(t,'overlay_pre_'+str(enabled))
            if current['digsites_enabled']!=enabled:
                def outcome(b,a,s):
                    probe=detail(t,'overlay_'+str(enabled));pins=probe['icon_pins'];checks={
                        'cvar':probe['digsites_enabled']==enabled,'checkbox':probe['digsite_checkbox']==enabled,
                        'same_sites':[r['id'] for r in probe['sites']]==ids,
                        'visible_icons':len(pins)==len(ids) and all(p['visible'] for p in pins) if enabled else not pins,
                        'native_preserved':native()==t.map_baseline}
                    return {'status':'map_digsite_overlay_pass' if all(checks.values()) else
                        'client_or_protocol_failure','oracle':{'checks':checks,'public':probe}}
                require(click_case(t,'map.digsites_'+str(enabled),'Set the stock digsite overlay '+str(enabled)+'.',
                    lambda c:c['name']=='WorldMapShowDigsites',outcome),'map_digsite_overlay_pass')
        require(t.step('map.bound_close','Close the world map with its binding.',
            {'map':{'kind':'key','value':key,'description':'Press the observed world-map binding.'}},
            lambda b,a,s:{'status':'map_close_pass' if 'WorldMapFrame' not in a['panels'] else
                'client_or_protocol_failure'},diagnostic_action='map'),'map_close_pass')
        require(t.step('map.bound_reopen_zone','Reopen the map at the player zone.',
            {'map':{'kind':'key','value':key,'description':'Press the observed world-map binding.'}},
            lambda b,a,s:nav_oracle(t,'zone_reopened',zone['id']),diagnostic_action='map'),'map_navigation_pass')
    finally:
        current=detail(t,'restoration_pre')
        if current['digsites_enabled']!=before['digsites_enabled']:
            if not current['visible']:
                t.execute({'kind':'key','value':key})
            def restored(b,a,s):
                probe=detail(t,'restored_overlay')
                passed=probe['digsites_enabled']==before['digsites_enabled']
                return {'status':'map_setting_restored' if passed else 'cleanup_failure',
                    'oracle':{'initial':before['digsites_enabled'],'public':probe}}
            require(click_case(t,'map.digsite_setting_restore','Restore the original digsite-display preference.',
                lambda c:c['name']=='WorldMapShowDigsites',restored),'map_setting_restored')
        t.clean_panels();t.receipt['native_after']=native();t.receipt['native_preserved']=t.receipt['native_after']==t.map_baseline
        t.receipt['digsites_setting_restored']=detail(t,'restoration_final')['digsites_enabled']==before['digsites_enabled'];t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
