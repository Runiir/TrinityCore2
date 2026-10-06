"""Separate missing static spell information from learned native eligibility."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('missing',[0,80388,93375])
def test_control_lesson_and_learned_spell_are_passive_independent_reads(missing):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/PetControlObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal missing='+str(missing)+'''
    local function forbidden() error('observer called a setter') end
    CastSpell=forbidden;CastSpellByID=forbidden;SetCVar=forbidden;LearnSpell=forbidden
    local reads={}
    C_Spell={RequestLoadSpellData=forbidden,GetSpellInfo=function(id)
        assert(id==80388 or id==93375);reads[id]=(reads[id] or 0)+1
        if id~=missing then return {name='Control Demon',spellID=id} end
    end}
    GetSpellInfo=function(id) assert(id==80388 or id==93375) end
    IsSpellKnown=function(id) assert(id==80388 or id==93375);return id==93375 end
    local p=Client442ObserveControlDemon()
    assert(p.lesson.id==80388 and not p.lesson.known)
    assert(p.learned.id==93375 and p.learned.known)
    for _,r in ipairs({p.lesson,p.learned}) do
        assert(r.info_available==(r.id~=missing))
        if r.id==missing then assert(r.name==nil)
        else assert(r.name=='Control Demon') end
    end
    assert(reads[80388]==1 and reads[93375]==1)
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
