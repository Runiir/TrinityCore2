"""Attribute stock quest-log buttons and links through read-only getters."""
import json,shutil,subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('change',['valid','header','offset','unrelated','missing_getter','missing_buttons'])
def test_stock_button_identity_and_source_link_index_are_attributable(change):
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/QuestObservation.lua'
    program='dofile('+json.dumps(str(source))+')\nlocal change='+json.dumps(change)+'''
    local button={GetID=function() return 2 end,isHeader=change=='header'}
    QuestLogListScrollFrame={buttons={button}}
    FauxScrollFrame_GetOffset=function(scroll) assert(scroll==QuestLogListScrollFrame);return change=='offset' and 3 or 0 end
    GetQuestIDFromLogIndex=function(index) return index==2 and 28825 or 52 end
    if change=='missing_getter' then FauxScrollFrame_GetOffset=nil
    elseif change=='missing_buttons' then QuestLogListScrollFrame.buttons=nil end
    local result=Client442ObserveQuestLogControl(change=='unrelated' and {} or button)
    if change=='unrelated' or change=='missing_getter' or change=='missing_buttons' then assert(result==nil)
    else
        assert(result.index==2 and result.header==(change=='header'))
        assert(result.link_index==(change=='offset' and 5 or 2))
        assert(result.quest_id==(change=='offset' and 52 or 28825))
    end
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)


def test_hidden_fixture_reads_id_link_and_selection_without_expanding_or_selecting():
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/QuestObservation.lua'
    program='dofile('+json.dumps(str(source))+')\n'+'''
    QuestLogFrame={IsVisible=function() return false end};QuestLogListScrollFrame={}
    GetNumQuestLogEntries=function() return 1,1 end
    GetQuestLogSelection=function() return 1 end
    GetNumQuestWatches=function() return 0 end
    HybridScrollFrame_GetOffset=function() return 0 end
    GetQuestLogTitle=function(index) assert(index==1);return 'Stormwind City',0,nil,true,true,0,0,0 end
    GetQuestLink=function(id) assert(id==28825);return 'quest:28825:80' end
    C_QuestLog={IsOnQuest=function(id) assert(id==28825);return true end}
    ExpandQuestHeader=function() error('observer expanded header') end
    SelectQuestLogEntry=function() error('observer selected quest') end
    local result=Client442ObserveQuestLog()
    assert(result.count==1 and result.total_quests==1 and result.selection==1 and result.visible==false)
    assert(result.rows[1].header and result.rows[1].collapsed and result.rows[1].quest_id==0)
    assert(result.fixture.active and result.fixture.link=='quest:28825:80')
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)
