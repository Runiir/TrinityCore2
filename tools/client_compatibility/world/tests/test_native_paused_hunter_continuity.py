"""A verified native restart may preserve the bridge while replacing the scout."""
from copy import deepcopy
import pytest
from tools.client_compatibility.world.tests.test_resource_paused_class_continuity import data
from tools.client_compatibility.interaction_resource_paused_class_fixture import continuity
from tools.client_compatibility.stopped_native_lineage import SCHEMA


def native_data():
    t,o,p,f,pause,d=deepcopy(data());before=o['runtime']
    t.receipt['runtime']={**t.receipt['runtime'],'worldserver':{'pid':6},'modern_world':before['modern_world']}
    d.update(schema=SCHEMA,native_before=before['worldserver'],native=t.receipt['runtime']['worldserver'],
        after=before['modern_world'],native_restarted=True,bridge_unchanged=True,native_unchanged=False)
    return t,o,p,f,pause,d


def test_bound_native_restart_preserves_retained_hunter_and_original_scout():continuity(*native_data(),'source')


@pytest.mark.parametrize('fault',['old_native','same_native','restart','bridge_flag','bridge_changed','wrong_native','primary','saved','old_scout'])
def test_partial_native_restart_or_saved_changes_are_refused(fault):
    t,o,p,f,pause,d=native_data()
    if fault=='old_native':d['native_before']={'pid':99}
    elif fault=='same_native':d['native']=o['runtime']['worldserver'];t.receipt['runtime']['worldserver']=d['native']
    elif fault=='restart':d['native_restarted']=False
    elif fault=='bridge_flag':d['bridge_unchanged']=False
    elif fault=='bridge_changed':t.receipt['runtime']['modern_world']={'pid':99}
    elif fault=='wrong_native':d['native']={'pid':99}
    elif fault=='primary':d['primary_stopped']=False
    elif fault=='saved':pause['after']={}
    else:d['scout_lifetime']=o['runtime']['client'];t.receipt['runtime']['client']=d['scout_lifetime']
    with pytest.raises(RuntimeError):continuity(t,o,p,f,pause,d,'source')
