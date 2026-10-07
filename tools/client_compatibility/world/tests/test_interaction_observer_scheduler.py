"""Run the installed Lua scheduler and pixel encoder with read-only stock stubs."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ADDON = Path(__file__).resolve().parents[2] / 'observation/addon/ClientMovementHarness'


def observe_ticks(panel='', bags_open=True, ticks=80):
    lua = shutil.which('lua')
    if not lua:
        pytest.skip('Lua interpreter unavailable')
    script = r'''
local panel, bagsOpen, ticks = arg[2], arg[3] == 'true', tonumber(arg[4])
local clock, forbiddenCalls, actionReads = 0, 0, 0
local function forbidden()
    forbiddenCalls = forbiddenCalls + 1
    error('passive observer attempted gameplay input')
end
for _,name in ipairs({'SetCVar','SetBinding','SetActionBarPage','ChangeActionBarPage',
    'PickupAction','PlaceAction','PickupContainerItem','UseContainerItem','ClearCursor',
    'CastSpellByID','CastSpellByName','CastSpell','RunMacro','RunMacroText','SpellStopCasting',
    'FollowUnit','TargetUnit','ClearTarget','ToggleBag','OpenAllBags','CloseAllBags'}) do
    _G[name] = forbidden
end
local methods = {}
function methods:GetEffectiveScale() return 1 end
function methods:SetScale() end
function methods:SetSize() end
function methods:SetPoint() end
function methods:SetFrameStrata() end
function methods:SetFrameLevel() end
function methods:EnableMouse() end
function methods:RegisterEvent() end
function methods:SetScript(name, callback) self.scripts[name] = callback end
function methods:GetScript(name) return self.scripts[name] end
function methods:IsVisible() return self.visible end
function methods:IsEnabled() return true end
function methods:IsMouseEnabled() return false end
function methods:GetName() return self.name end
function methods:GetObjectType() return self.kind end
function methods:GetParent() return self.parent end
function methods:GetChildren() return unpack(self.children) end
function methods:GetRegions() end
function methods:GetCenter() return 400, 300 end
function methods:GetID() return self.id end
function methods:GetBagID() return self.bag end
function methods:GetText() return self.name or '' end
function methods:GetAttribute() end
function methods:GetChecked() return false end
function methods:Click() forbidden() end
function methods:Show() assert(self.name == 'ClientInteractionHarnessPanel') end
function methods:Hide() assert(self.name == 'ClientInteractionHarnessPanel') end
function methods:CreateTexture()
    local texture = {SetSize=methods.SetSize, SetPoint=methods.SetPoint}
    function texture:SetColorTexture(r,g,b)
        self.bytes = {math.floor(r*255+.5), math.floor(g*255+.5), math.floor(b*255+.5)}
    end
    self.textures[#self.textures+1] = texture
    return texture
end
local function frame(name, kind, visible)
    local value = setmetatable({name=name,kind=kind or 'Frame',visible=visible,
        children={},textures={},scripts={}}, {__index=methods})
    if name then _G[name]=value end
    return value
end
UIParent = frame('UIParent','Frame',true)
CreateFrame = function(kind,name,parent)
    local result = frame(name,kind,true);result.parent=parent;return result
end
geterrorhandler = function() return function(message) error(message) end end
seterrorhandler = function(handler) assert(type(handler)=='function') end
SlashCmdList = {}
GetBuildInfo = function() return '4.4.2','60895','',40402 end
UnitName = function(unit) return unit=='player' and 'Harnesstwo' or unit end
UnitGUID = function(unit) return unit=='player' and 'Player-1-00000002' or unit end
UnitLevel = function() return 1 end
UnitClass = function() return 'Warrior','WARRIOR' end
UnitHealth = function() return 100 end
UnitHealthMax = UnitHealth
GetNumBindings = function() return 0 end
GetNumMacros = function() return 0,0 end
GetInventoryItemID = function() end
UnitIsGroupLeader = function() return false end
GetScreenWidth = function() return 1280 end
GetScreenHeight = function() return 720 end
GetNumGroupMembers = function() return 13 end
IsInRaid = function() return true end
GetTime = function() return clock end
GetActionInfo = function(slot)
    assert(slot>=1 and slot<=12);actionReads=actionReads+1
    if slot==1 then return 'spell',6603 end
end
GetActionBarPage = function() return 1 end
GetActiveTalentGroup = function() return 1 end
GetNumShapeshiftForms = function() return 0 end
GetMoney = function() return 8708 end
CursorHasItem = function() return false end
C_Container = {GetContainerNumSlots=function(bag) return bag==0 and 16 or 0 end,
    GetContainerItemInfo=function(bag,slot)
        if bag==0 and slot==1 then return {itemID=6948,stackCount=1,isLocked=false} end
    end,PickupContainerItem=forbidden,UseContainerItem=forbidden}
for _,name in ipairs({'ChatEdit','SpellChannel','Pointer','TargetFrame','PetFrame','QuestLog',
    'Who','Equipment','SpellBook','Macros','Achievements','AddOns','AddOnClicks','Settings'}) do
    _G['Client442Observe'..name]=function() return {} end
end
Client442ObserveMelee = function() return {active=false,event_sequence=0} end
Client442ObserveDressUp = function() return {visible=false} end
Client442HookPerformanceTooltip = function() end
Client442PerformanceTooltipEvent = function() return {} end
for _,name in ipairs({'WhoFrame','AddonList','MacroFrame','SettingsPanel','DressUpFrame',
    'AchievementFrame','PaperDollFrame','SpellBookFrame','GameMenuFrame'}) do
    frame(name,'Frame',name==panel)
end
ContainerFrame1=frame('ContainerFrame1','Frame',bagsOpen);ContainerFrame1.id=0
for slot=1,16 do
    local child=frame('ContainerFrame1Item'..slot,'Button',bagsOpen)
    child.parent=ContainerFrame1;child.bag=0;child.id=slot
    ContainerFrame1.children[#ContainerFrame1.children+1]=child
end
for _,name in ipairs({'CharacterMicroButton','SpellbookMicroButton','TalentMicroButton',
    'AchievementMicroButton','QuestLogMicroButton','SocialsMicroButton','GuildMicroButton',
    'EJMicroButton','CollectionsMicroButton','MainMenuMicroButton','HelpMicroButton'}) do
    frame(name,'Button',true).parent=UIParent
end
for slot=1,12 do frame('ActionButton'..slot,'Button',true).action=slot end
dofile(arg[1]..'/SettingsObservation.lua')
-- Preserve the stock settings cadence predicate, with a read-only page stub.
Client442ObserveSettings = function() return {visible=SettingsPanel:IsVisible()} end
dofile(arg[1]..'/ActionBarObservation.lua')
dofile(arg[1]..'/ClientInteractions.lua')
local observer=ClientInteractionHarnessPanel
local function emit()
    local bytes={}
    for _,texture in ipairs(observer.textures) do
        for _,byte in ipairs(texture.bytes or {0,0,0}) do bytes[#bytes+1]=byte end
    end
    assert(bytes[1]==84 and bytes[2]==67 and bytes[3]==85 and bytes[4]==50)
    local size=bytes[5]*256+bytes[6];local text={}
    for index=11,10+size do text[#text+1]=string.char(bytes[index]) end
    print(table.concat(text))
end
emit()
for tick=1,ticks do
    clock=tick*.5
    observer.scripts.OnUpdate(observer,.5)
    emit()
end
assert(forbiddenCalls==0,'observer sent a setter/cast/control input')
print('ACTION_READS='..actionReads)
'''
    run = subprocess.run([lua, '-', str(ADDON), panel, str(bags_open).lower(), str(ticks)],
        input=script, text=True, capture_output=True, timeout=5)
    assert run.returncode == 0, run.stderr
    lines = run.stdout.splitlines()
    assert lines[-1].startswith('ACTION_READS=')
    samples = [json.loads(line) for line in lines[:-1]]
    assert len(samples) == ticks + 1
    errors = [sample['observer_error'] for sample in samples if 'observer_error' in sample]
    assert not errors, errors[:3]
    assert all(sample['observer_version'] == 146 for sample in samples if sample['mode'] != 'controls')
    return samples, int(lines[-1].partition('=')[2])


@pytest.mark.parametrize('bags_open', [True, False])
def test_actual_lua_scheduler_keeps_actionbars_and_normal_pages_fresh(bags_open):
    samples, reads = observe_ticks(bags_open=bags_open)
    modes = [sample['mode'] for sample in samples]
    assert modes[0] == 'state'
    assert all(modes[index+1] == 'state' for index in range(len(modes)-1) if modes[index] != 'state')
    bars = [index for index, mode in enumerate(modes) if mode == 'actionbars']
    assert bars and bars[0] <= 6
    assert all('actionbars' in modes[start:start+12] for start in range(len(modes)-11))
    expected_controls = {1,2,3} if bags_open else {1}
    assert {sample['page'] for sample in samples if sample['mode'] == 'controls'} >= expected_controls
    assert {sample['page'] for sample in samples if sample['mode'] == 'group'} == {1,2,3}
    assert 'settings' in modes
    for sample in samples:
        if sample['mode'] in ('state', 'controls'):
            assert sample['bags'] == ([0] if bags_open else {})
        if sample['mode'] == 'actionbars':
            assert len(sample['actionbar_probe']['actions']) == 12
            assert sample['actionbar_probe']['actions'][0]['id'] == 6603
    assert reads >= len(bars)*12


def test_actual_lua_scheduler_retains_panel_gating_and_group_control_progress():
    samples, _ = observe_ticks(panel='GameMenuFrame')
    modes = [sample['mode'] for sample in samples]
    assert 'actionbars' not in modes
    assert {'state','controls','group','settings'} <= set(modes)
    assert all(sample['panels'] == ['GameMenuFrame'] for sample in samples if sample['mode'] in ('state','controls'))


@pytest.mark.parametrize('panel,mode', [('WhoFrame','who'), ('AddonList','addons'), ('MacroFrame','macros'),
    ('SettingsPanel','settings'), ('DressUpFrame','dressup'), ('AchievementFrame','achievements'),
    ('PaperDollFrame','equipment'), ('SpellBookFrame','spellbook')])
def test_actual_lua_scheduler_preserves_special_page_priority(panel, mode):
    samples, _ = observe_ticks(panel=panel, ticks=15)
    # Sixth state cadence also offers actionbars for panel-free WhoFrame;
    # the established even-tick special page must retain priority.
    assert samples[11]['mode'] == mode
    assert all(samples[index+1]['mode'] == 'state' for index in range(len(samples)-1)
        if samples[index]['mode'] != 'state')
