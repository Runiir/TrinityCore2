"""Pet spell knowledge must query the public pet namespace, without gameplay calls."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('book',['pet','spell'])
def test_pet_and_player_spellbook_knowledge_are_distinct(book):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SpellBookObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal kind='+json.dumps(book)+'''
    local function forbidden() error('observer called a gameplay setter') end
    CastSpell=forbidden;CastSpellByID=forbidden;CreateFrame=forbidden
    BOOKTYPE_PET='pet';BOOKTYPE_SPELL='spell'
    SpellBookFrame={bookType=kind,IsVisible=function() return true end}
    SpellButton1={IsVisible=function() return true end,GetName=function() return 'SpellButton1' end}
    SpellBook_GetSpellBookSlot=function() return 1,'SPELL',3110 end
    GetSpellBookItemName=function(slot,book) assert(slot==1 and book==kind);return 'Firebolt','',3110 end
    GetSpellBookItemInfo=function() return 'SPELL',3110 end
    IsSpellKnown=function(id,pet) assert(id==3110 and type(pet)=='boolean');return pet end
    Client442ObserveTooltip=function() return {lines={}} end
    local probe=Client442ObserveSpellBook()
    assert(probe.rows[1].id==3110 and probe.rows[1].known==(kind=='pet'))
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
