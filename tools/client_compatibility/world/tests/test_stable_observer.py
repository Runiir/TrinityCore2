"""Closed panels do not read pet caches; open observations never move pets."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('visible',[False,True])
def test_stock_stable_cache_and_events_are_passive(visible):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/StableObservation.lua'
    program='local visible='+str(visible).lower()+'''
    local function forbidden() error('observer invoked a gameplay setter') end
    SetPetSlot=forbidden;PickupStablePet=forbidden;ClosePetStables=forbidden;SetCVar=forbidden
    local handler,registered,reads=nil,{},0
    CreateFrame=function(kind) assert(kind=='Frame');return {
        RegisterEvent=function(_,event) registered[event]=true end,
        SetScript=function(_,kind,fn) assert(kind=='OnEvent');handler=fn end} end
    PetStableFrame={IsVisible=function() return visible end,page=1,selectedPet=1}
    PetStableNameText={GetText=function() return 'Harnesswolf' end}
    PetStableLevelText={GetText=function() return 'Level10' end}
    UIParent={GetSize=function() return 1280,720 end}
    PetStableActivePet1={petSlot=1,GetCenter=function() return 640,360 end,
        IsVisible=function() return true end,IsEnabled=function() return true end}
    GetStablePetInfo=function(slot)
        assert(slot>=1 and slot<=205);reads=reads+1
        if slot==1 then return 1,'Harnesswolf',10,'Wolf','Ferocity' end
    end
    GetNumStableSlots=function() return 16 end
    C_PlayerInfo={GetPetStableCreatureDisplayInfoID=function(slot) assert(slot==1);return 2404 end}
    Enum={PlayerInteractionType={StableMaster=22}}
    C_PlayerInteractionManager={IsInteractingWithNpcOfType=function(kind) assert(kind==22);return true end,
        IsValidNPCInteraction=function(kind) assert(kind==22);return true end}
    dofile('''+json.dumps(str(source))+''')
    assert(registered.PET_STABLE_SHOW and registered.PET_STABLE_UPDATE and registered.PET_STABLE_CLOSED)
    handler(nil,'PET_STABLE_SHOW');handler(nil,'PET_STABLE_SHOW')
    local p=Client442ObserveStables()
    assert(p.visible==visible and p.stable_slots==16 and p.events.PET_STABLE_SHOW.count==2 and p.event_sequence==2)
    assert(reads==205 and #p.pets==1 and p.pets[1].slot==1 and p.pets[1].name=='Harnesswolf')
    assert(p.pets[1].level==10 and p.pets[1].display_id==2404)
    assert(p.interaction_type==22 and p.interacting and p.valid_interaction)
    handler(nil,'PLAYER_INTERACTION_MANAGER_FRAME_SHOW',8)
    assert(Client442ObserveStables().event_sequence==2)
    handler(nil,'PLAYER_INTERACTION_MANAGER_FRAME_SHOW',22)
    assert(Client442ObserveStables().events.PLAYER_INTERACTION_MANAGER_FRAME_SHOW.count==1)
    if visible then
        assert(p.name=='Harnesswolf')
        assert(#p.buttons==1 and p.buttons[1].enabled and p.buttons[1].slot==1)
    else assert(#p.buttons==0) end
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
