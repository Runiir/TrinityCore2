"""Native restoration tolerates float rounding and rejects the observed10% drift."""
from copy import deepcopy
from tools.client_compatibility.interaction_stance_bar import restored_native_state


def test_native_restore_rejects_observed_boost_loss_and_accepts_float_rounding():
    baseline={'form':17,'health':162515,'power':0,
        'stats':{'strength':6319,'armor':23689,'health':162515,
            'damage':[8146.9990234375,10121.939453125]}}
    changed=deepcopy(baseline);changed['stats']['damage']=[7406.3623046875,9201.76171875]
    assert not restored_native_state(baseline,changed)
    rounded=deepcopy(baseline);rounded['stats']['damage'][0]+=.001
    assert restored_native_state(baseline,rounded)
    rounded['health']-=1
    assert not restored_native_state(baseline,rounded)
