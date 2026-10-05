"""An owned reply must not be submitted to a different or stale destination."""
import pytest
from tools.client_compatibility.interaction_reply_chat import pending


@pytest.mark.parametrize('changed',[
    {'chat_edit_open':False},
    {'chat_edit_focused':False},
    {'chat_edit_target':'Anotherplayer'},
    {'chat_edit_type':'SAY'},
    {'chat_edit_text':'TC442UI:reply_1234567'},
    {'chat_edit_text':'TC442UI:reply_12345678 extra'},
])
def test_reply_rejects_changed_focus_recipient_type_or_text(changed):
    state={'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'WHISPER',
        'chat_edit_target':'Harnesstwo','chat_edit_text':'TC442UI:reply_12345678'}
    assert pending(state,'Harnesstwo','TC442UI:reply_12345678')
    state.update(changed)
    assert not pending(state,'Harnesstwo','TC442UI:reply_12345678')


def test_seed_accepts_the_exact_selected_slash_command_before_stock_consumes_it():
    command='/w Harnessone TC442UI:reply_seed_12345678'
    state={'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'SAY','chat_edit_text':command}
    assert pending(state,'Harnessone','TC442UI:reply_seed_12345678',command)
    state['chat_edit_text']=command.replace('Harnessone','Anotherplayer')
    assert not pending(state,'Harnessone','TC442UI:reply_seed_12345678',command)
