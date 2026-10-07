"""A bridge replacement must preserve the same scout and the stopped primary."""
from copy import deepcopy
from pathlib import Path
import pytest
from tools.client_compatibility import interaction_single_scout_bridge_deploy as deploy


def data():
    native={'pid':1};client={'pid':2};before={'pid':3};build={'source':'candidate'}
    after={'pid':4,'build':build};runtime={'worldserver':native,'modern_world':after,'client':client}
    primary={'path':'primary/episode.json','sha256':'stop'}
    source={'path':'boundary/episode.json','sha256':'boundary'}
    tests={'path':'tests.json','sha256':'tests'}
    baseline={str(i):{'native':{'online':0}} for i in range(1,7)}
    e={'phase':'owned_tame_diagnostic_parked_boundary','actor':{'guid':2},
        'checks':dict.fromkeys(range(20),True),'all_offline_snapshot':baseline,
        'runtime':{'worldserver':native,'modern_world':before,'client':client},'primary_stop_source':primary}
    d={'schema':deploy.SCHEMA,'boundary_source':source,'primary_stop_source':primary,'tests_source':tests,
        'installed':True,'installation_checks':dict.fromkeys(range(6),True),'offline_baselines':baseline,
        'native':native,'before':before,'after':after,'scout_lifetime':client,'build':build,'parked_reconnect_attempt':{}}
    return e,d,runtime,{'runtime':{'worldserver':native}}


def invoke(monkeypatch,tmp_path,values):
    e,d,runtime,stop=values;path=tmp_path/'deployment.json';path.write_text(__import__('json').dumps(d))
    monkeypatch.setattr(deploy,'closed',lambda p:e)
    monkeypatch.setattr(deploy,'primary_stopped',lambda p:stop)
    monkeypatch.setattr(deploy,'tests',lambda p,b:None)
    monkeypatch.setattr(deploy,'bound',lambda p:d['boundary_source'] if str(p).endswith('episode.json') else d['tests_source'])
    return deploy.verified_report(tmp_path,runtime)


def test_one_scout_bridge_replacement_preserves_client_lifetime(monkeypatch,tmp_path):
    d=invoke(monkeypatch,tmp_path,data());assert d['scout_lifetime']=={'pid':2}


@pytest.mark.parametrize('fault',['native','scout','before','after','same_bridge','candidate','primary_source',
    'source_phase','source_check','source_count','source_actor','missing_actor','online_actor','changed_saved',
    'installation','install_count','not_installed','schema','fake_primary_reconnect','native_primary_source'])
def test_unbound_source_client_restart_or_fake_primary_is_refused(monkeypatch,tmp_path,fault):
    e,d,runtime,stop=deepcopy(data())
    if fault=='native':runtime['worldserver']={'pid':99}
    elif fault=='scout':runtime['client']={'pid':99}
    elif fault=='before':d['before']={'pid':99}
    elif fault=='after':d['after']={'pid':99}
    elif fault=='same_bridge':d['after']=d['before']
    elif fault=='candidate':d['build']={'source':'wrong'}
    elif fault=='primary_source':d['primary_stop_source']={}
    elif fault=='source_phase':e['phase']='other'
    elif fault=='source_check':e['checks'][0]=False
    elif fault=='source_count':e['checks'].pop(0)
    elif fault=='source_actor':e['actor']['guid']=6
    elif fault=='missing_actor':e['all_offline_snapshot'].pop('6')
    elif fault=='online_actor':e['all_offline_snapshot']['6']['native']['online']=1
    elif fault=='changed_saved':d['offline_baselines']={}
    elif fault=='installation':d['installation_checks'][0]=False
    elif fault=='install_count':d['installation_checks'].pop(0)
    elif fault=='not_installed':d['installed']=False
    elif fault=='schema':d['schema']='client442_bridge_deployment_v1'
    elif fault=='fake_primary_reconnect':d['parked_reconnect_attempt']['primary']={'completed':True}
    else:stop['runtime']['worldserver']={'pid':99}
    with pytest.raises(RuntimeError):invoke(monkeypatch,tmp_path,(e,d,runtime,stop))
