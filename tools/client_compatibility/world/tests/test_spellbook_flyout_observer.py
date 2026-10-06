"""Read stock flyout identity and training gates without casting or UI setters."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('trained',[True,False])
def test_flyout_preserves_slot_and_visible_button_training_identity(trained):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SpellBookObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal trained='+str(trained).lower()+'''
    local function forbidden() error('passive observer invoked a setter or cast') end
    CastSpellByID=forbidden;CastSpell=forbidden;CreateFrame=forbidden
    GetNumSpellTabs=function() return 1 end
    GetSpellTabInfo=function() return 'Demonology',0,0,1 end
    SpellBook_GetCurrentPage=function() return 1,1 end
    SpellBookFrame={IsVisible=function() return true end,bookType='spell',selectedSkillLine=1}
    SpellButton1={IsVisible=function() return true end,GetName=function() return 'SpellButton1' end,
        SetAttribute=forbidden,Click=forbidden}
    SpellBook_GetSpellBookSlot=function() return 1,'FLYOUT',10 end
    GetSpellBookItemName=function() return 'Summon Demon' end
    GetSpellBookItemInfo=function() return 'FLYOUT',10 end
    GetFlyoutInfo=function(id) assert(id==10);return 'Summon Demon','',2,trained end
    GetFlyoutSlotInfo=function(id,index)
        assert(id==10)
        return index==1 and 688 or 697,index==1 and 688 or 697,
            index==1 and trained or false,index==1 and 'Summon Imp' or 'Summon Voidwalker'
    end
    IsSpellKnown=function(id) return id==688 and trained end
    GetSpellInfo=function(id) assert(id==688);return 'Summon Imp' end
    SpellFlyout={IsVisible=function() return true end,GetParent=function() return SpellButton1 end,
        Toggle=forbidden,Hide=forbidden}
    SpellFlyoutButton1={spellID=688,IsVisible=function() return true end,
        IsEnabled=function() return trained end,GetName=function() return 'SpellFlyoutButton1' end,Click=forbidden,
        GetCenter=function() return 160,557 end,GetEffectiveScale=function() return 1 end}
    UIParent={GetEffectiveScale=function() return 1 end}
    GetScreenWidth=function() return 1280 end;GetScreenHeight=function() return 720 end
    SpellFlyoutButton2={spellID=697,IsVisible=function() return false end,Click=forbidden}
    Client442ObserveTooltip=function() return {lines={}} end
    local probe=Client442ObserveSpellBook()
    assert(probe.rows[1].flyout.id==10 and probe.rows[1].flyout.known==trained)
    assert(probe.rows[1].flyout.slots[1].id==688 and probe.rows[1].flyout.slots[1].known==trained)
    assert(probe.rows[1].flyout.slots[2].id==697 and probe.rows[1].flyout.slots[2].known==false)
    assert(probe.flyout.visible and probe.flyout.parent=='SpellButton1' and #probe.flyout.buttons==1)
    assert(probe.flyout.buttons[1].id==688 and probe.flyout.buttons[1].known==trained)
    assert(probe.flyout.buttons[1].enabled==trained and probe.flyout.buttons[1].name=='Summon Imp')
    assert(probe.flyout.buttons[1].point[1]==math.floor(160/1280*65535))
    assert(probe.flyout.buttons[1].point[2]==math.floor(163/720*65535))
    assert(probe.pet.exists==false)
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
