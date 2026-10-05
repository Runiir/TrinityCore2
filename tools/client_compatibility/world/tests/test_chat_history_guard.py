import pytest
from tools.client_compatibility.interaction_chat_history import pending_say

TOKEN='TC442UI:scroll_1234abcd_00'
COMMAND='/s '+TOKEN


@pytest.mark.parametrize('text',[TOKEN,COMMAND])
def test_exact_focused_say(text):
    assert pending_say({'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'SAY',
        'chat_edit_text':text},TOKEN,COMMAND)


@pytest.mark.parametrize('change',[
    {'chat_edit_open':False},{'chat_edit_focused':False},{'chat_edit_type':'WHISPER'},
    {'chat_edit_type':'PARTY','chat_edit_text':COMMAND},{'chat_edit_text':TOKEN[:-1]},
    {'chat_edit_text':TOKEN+' unrelated'},{'chat_edit_text':'TC442UI:scroll_1234abcd_01'}])
def test_unsafe_pending_input_is_rejected(change):
    state={'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'SAY','chat_edit_text':TOKEN}
    state.update(change)
    assert not pending_say(state,TOKEN,COMMAND)
