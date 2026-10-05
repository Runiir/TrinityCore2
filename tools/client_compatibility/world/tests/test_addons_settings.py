"""Owned AddOns observations must not confuse enable preferences with unloading."""
import copy
import subprocess
from pathlib import Path
import pytest
from tools.client_compatibility.interaction_addons_settings import COMPAT,HARNESS,pending_checks,valid_row,row_matches,AddonsTrial,cadence_ready
from tools.client_compatibility.interaction_trial import Trial


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


@pytest.mark.parametrize('fps,accepted',[(15,True),(10,True),(9.9,False),(None,False),(True,False),('15',False),(float('nan'),False),(float('inf'),False)])
def test_short_addons_click_requires_measured_frame_cadence(fps,accepted):
    assert cadence_ready({'framerate':fps}) is accepted


def test_only_the_guarded_addons_selection_uses_a_short_pulse(monkeypatch):
    monkeypatch.setattr(Trial,'step',lambda self,case,goal,actions,oracle,**kw:actions)
    t=AddonsTrial.__new__(AddonsTrial);actions={'click':{'kind':'click','value':[430,205],'hold':1.2}}
    assert t.step('settings.addons.pending_off','goal',actions,None)['click']['hold']==.2
    assert t.step('fixture.restore_addons_selection','goal',actions,None)['click']['hold']==.2
    assert t.step('settings.addons.open','goal',actions,None)['click']['hold']==1.2


@pytest.mark.parametrize('change',[None,'name','kind','caption','disabled','no_handler','foreign_checkbox'])
def test_row_button_requires_the_exact_owned_checkbox_identity_and_click_handler(change):
    check={'name':'AddonListEntry2Enabled'}
    row={'name':'AddonListEntry2','kind':'Button','text':'Owned Compatibility','enabled':True,'addon_onclick':True}
    if change=='name':row['name']='AddonListEntry1'
    elif change=='kind':row['kind']='CheckButton'
    elif change=='caption':row['text']='foreign'
    elif change=='disabled':row['enabled']=False
    elif change=='no_handler':row['addon_onclick']=False
    elif change=='foreign_checkbox':check['name']='ForeignEntry2Enabled'
    assert row_matches(row,check,'Owned Compatibility')==(change is None)


def test_pinned_addon_getters_use_name_first_and_never_request_a_setter():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/AddOnsObservation.lua'
    script=r'''
local names={ClientMovementHarness=true,Client442Compatibility=true}
local reads=0
UnitName=function(unit) assert(unit=='player');return 'Harnessone' end
AddonList={IsVisible=function() return true end}
C_AddOns=setmetatable({
 EnableAddOn=function() error('observer called an enable setter') end,
 DisableAddOn=function() error('observer called a disable setter') end,
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


def test_post_click_listener_records_delivery_without_invoking_or_replacing_a_handler():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/AddOnsObservation.lua'
    script=r'''
local callback,installs,checked=nil,0,true
UnitName=function() return 'Harnessone' end
AddonListEntry2Enabled=setmetatable({
 HookScript=function(self,kind,fn) assert(kind=='OnClick');installs=installs+1;callback=fn end,
 GetName=function() return 'AddonListEntry2Enabled' end,
 GetChecked=function() return checked end,
}, {__index=function(_,key) error('observer attempted a setter or handler '..key) end})
C_AddOns={GetAddOnEnableState=function(name,char) assert(name=='Client442Compatibility' and char=='0');return 2 end}
dofile(arg[1]);Client442ObserveAddOns();Client442ObserveAddOns()
local probe=Client442ObserveAddOnClicks();assert(installs==1 and #probe.events==0 and probe.hook_installed)
assert(checked==true) -- installing observations did not click or toggle anything
checked=false -- an ordinary player event, simulated by this test
for i=1,11 do callback(AddonListEntry2Enabled,'LeftButton',false) end
probe=Client442ObserveAddOnClicks();assert(#probe.events==8 and probe.events[1].serial==4)
assert(probe.events[8].serial==11 and probe.events[8].checked==false and probe.events[8].enable_all==2)
assert(probe.events[8].button=='LeftButton' and probe.events[8].down_known and probe.events[8].down==false)
assert(checked==false)
'''
    subprocess.run(['lua','-',str(source)],input=script,text=True,capture_output=True,check=True,timeout=3)


def test_preference_posthooks_are_bounded_observations_and_do_not_invoke_setters():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/AddOnsObservation.lua'
    script=r'''
local hooks={}
UnitName=function() return 'Harnessone' end
C_AddOns={
 EnableAddOn=function() error('observer invoked EnableAddOn') end,
 DisableAddOn=function() error('observer invoked DisableAddOn') end,
 GetAddOnInfo=function(name) if name==2 or name=='Client442Compatibility' then return 'Client442Compatibility' end end,
 GetAddOnEnableState=function(name,char) assert(name=='Client442Compatibility' and char=='0');return 2 end,
}
hooksecurefunc=function(api,method,fn) assert(api==C_AddOns and not hooks[method]);hooks[method]=fn end
dofile(arg[1]);Client442ObserveAddOns();Client442ObserveAddOns()
local probe=Client442ObserveAddOnClicks();assert(#probe.preference_calls==0)
assert(hooks.EnableAddOn and hooks.DisableAddOn)
hooks.EnableAddOn(2,'0') -- simulate the post-call observation, not the original setter
probe=Client442ObserveAddOnClicks();local row=probe.preference_calls[1]
assert(row.method=='C_AddOns.EnableAddOn' and row.requested==2 and row.owned_name=='Client442Compatibility' and row.enable_all==2)
for i=1,10 do hooks.DisableAddOn('foreign-account-data','private-character') end
probe=Client442ObserveAddOnClicks();assert(#probe.preference_calls==8)
for _,row in ipairs(probe.preference_calls) do assert(row.requested==nil and row.character==nil and row.owned_name==nil) end
'''
    subprocess.run(['lua','-',str(source)],input=script,text=True,capture_output=True,check=True,timeout=3)
