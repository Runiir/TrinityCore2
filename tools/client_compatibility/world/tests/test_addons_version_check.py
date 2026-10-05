"""Version-check outcomes require the inverse checkbox and unchanged addon rows."""
import copy
import pytest
from tools.client_compatibility.interaction_addons_version_check import version_checks
from tools.client_compatibility.world.tests.test_addons_settings import original


def test_version_check_outcome_accepts_only_the_requested_flag_change():
    before=original();after=copy.deepcopy(before);after['version_check']=False
    assert all(version_checks(after,before,False).values())
    assert not all(version_checks(after,before,True).values())


@pytest.mark.parametrize('change',['integer_flag','missing_flag','closed','disabled_addon','unloaded_addon','missing_addon','count'])
def test_version_check_cannot_qualify_an_unrelated_addon_or_panel_change(change):
    before=original();after=copy.deepcopy(before);after['version_check']=False
    if change=='integer_flag':after['version_check']=0
    elif change=='missing_flag':after.pop('version_check')
    elif change=='closed':after['visible']=False
    elif change=='disabled_addon':after['rows']['ClientMovementHarness']['enable_all']=0
    elif change=='unloaded_addon':after['rows']['Client442Compatibility']['loaded']=False
    elif change=='missing_addon':after['rows'].pop('Client442Compatibility')
    elif change=='count':after['count']=3
    assert not all(version_checks(after,before,False).values())
