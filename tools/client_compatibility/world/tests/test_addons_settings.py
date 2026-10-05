"""Owned AddOns observations must not confuse enable preferences with unloading."""
import copy
import subprocess
from pathlib import Path
import pytest
from tools.client_compatibility.interaction_addons_settings import COMPAT,HARNESS,pending_checks,valid_row


def original():
    return {'visible':True,'count':2,'version_check':True,'rows':{
        n:{'name':n,'title':n,'enable_all':2,'enable_character':2,
            'loaded':True,'loaded_or_loading':True,'version':'1.0'} for n in (COMPAT,HARNESS)}}


@pytest.mark.parametrize('flag',[0,1,2])
def test_pending_enable_getter_outcome_is_recorded_without_an_unload_claim(flag):
    before=original();after=copy.deepcopy(before)
    after['rows'][COMPAT]['enable_all']=after['rows'][COMPAT]['enable_character']=flag
    assert all(pending_checks(after,before).values())
    assert after['rows'][COMPAT]['loaded'] is True


@pytest.mark.parametrize('change',['unloaded','loading','harness','other_addon','missing_addon','name','title','version','count','version_check','panel'])
def test_pending_checkbox_cannot_accept_unrelated_state_changes(change):
    before=original();after=copy.deepcopy(before)
    if change=='unloaded':after['rows'][COMPAT]['loaded']=False
    elif change=='loading':after['rows'][COMPAT]['loaded_or_loading']=False
    elif change=='harness':after['rows'][HARNESS]['enable_all']=0
    elif change=='other_addon':after['rows']['foreign']=copy.deepcopy(after['rows'][COMPAT])
    elif change=='missing_addon':after['rows'].pop(HARNESS)
    elif change in ('name','title','version'):after['rows'][COMPAT][change]='foreign'
    elif change=='count':after['count']=3
    elif change=='version_check':after['version_check']=False
    else:after['visible']=False
    assert not all(pending_checks(after,before).values())


@pytest.mark.parametrize('flag',[True,'2',None,-1,3])
def test_enable_preference_requires_an_exact_supported_integer(flag):
    row=original()['rows'][COMPAT];row['enable_all']=flag
    assert not valid_row(row,COMPAT)


def test_pinned_addon_getters_use_name_first_and_never_request_a_setter():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/AddOnsObservation.lua'
    script=r'''
local names={ClientMovementHarness=true,Client442Compatibility=true}
local reads=0
UnitName=function(unit) assert(unit=='player');return 'Harnessone' end
AddonList={IsVisible=function() return true end}
C_AddOns=setmetatable({
 GetNumAddOns=function() return 2 end,
 IsAddonVersionCheckEnabled=function() return true end,
 GetAddOnInfo=function(name) assert(names[name]);return name,name end,
 IsAddOnLoaded=function(name) assert(names[name]);return true,true end,
 GetAddOnMetadata=function(name,key) assert(names[name] and key=='Version');return '1.0' end,
 GetAddOnEnableState=function(name,character)
  assert(names[name]);assert(character=='0' or character=='Harnessone');reads=reads+1;return 2
 end,
}, {__index=function(_,key) error('unexpected API or setter '..key) end})
dofile(arg[1]);local observed=Client442ObserveAddOns()
assert(observed.visible and observed.count==2 and observed.version_check and reads==4)
for name in pairs(names) do
 local row=observed.rows[name]
 assert(row.name==name and row.loaded and row.loaded_or_loading and row.enable_all==2 and row.enable_character==2)
end
'''
    subprocess.run(['lua','-',str(source)],input=script,text=True,capture_output=True,check=True,timeout=3)
