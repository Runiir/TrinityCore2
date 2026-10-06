"""Passive command rows and public positions must remain attributable reads."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('position_mode',['available','missing','invalid'])
def test_pet_commands_read_ten_actions_without_submitting_or_setting(position_mode):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/PetCommandObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal mode='+json.dumps(position_mode)+'''
    local function forbidden() error('passive observer submitted a command') end
    PetFollow=forbidden;PetWait=forbidden;CastSpell=forbidden;SetCVar=forbidden
    local reads={}
    GetPetActionInfo=function(slot)
        assert(slot>=1 and slot<=10);reads[slot]=(reads[slot] or 0)+1
        return slot==1 and 'PET_ACTION_FOLLOW' or slot==2 and 'PET_ACTION_WAIT' or 'other',
            slot,true,slot==2,false,false,nil
    end
    UnitGUID=function(unit) return unit=='player' and 'Player-owned' or 'Pet-owned' end
    GetUnitSpeed=function(unit) return unit=='player' and 0 or 1 end
    UnitPosition=function(unit)
        if mode=='missing' then return nil end
        if mode=='invalid' then return 0/0,0,0,0 end
        if unit=='player' then return 10,20,30,0 end
        return 13,24,30,0
    end
    local p=Client442ObservePetCommands()
    assert(#p.actions==10 and p.owner_guid=='Player-owned' and p.pet_guid=='Pet-owned')
    assert(p.player_speed==0 and p.pet_speed==1)
    for i,row in ipairs(p.actions) do
        assert(reads[i]==1 and row.slot==i and row.available and row.is_token)
        assert(row.active==(i==2) and not row.autocast_allowed and not row.autocast_enabled)
    end
    assert(p.actions[1].name=='PET_ACTION_FOLLOW' and p.actions[2].name=='PET_ACTION_WAIT')
    if mode=='available' then
        assert(p.player_position.available and p.pet_position.available and p.distance==5)
    else assert(not p.player_position.available and not p.pet_position.available and p.distance==nil) end
    GetPetActionInfo=nil;UnitPosition=nil
    p=Client442ObservePetCommands()
    for _,row in ipairs(p.actions) do assert(not row.available and not row.active) end
    assert(not p.pet_position.available and p.distance==nil)
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
