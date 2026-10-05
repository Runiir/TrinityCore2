from tools.client_compatibility.interaction_chat_link_delivery import pending_item_link

TEXT='|cffffffff|Hitem:49778::::::::85:::::::::|h[Worn Greatsword]|h|r'


def state(**change):
    return dict(chat_edit_open=True,chat_edit_focused=True,chat_edit_type='SAY',chat_edit_text=TEXT)|change


def test_stock_owned_say_link_is_admitted():
    assert pending_item_link(state(),TEXT,49778)


def test_wrong_header_focus_partial_or_foreign_text_is_rejected():
    for change in [{'chat_edit_open':False},{'chat_edit_focused':False},{'chat_edit_type':'WHISPER'},
                   {'chat_edit_text':TEXT[:-1]},{'chat_edit_text':TEXT+' extra'}]:
        assert not pending_item_link(state(**change),TEXT,49778)
    assert not pending_item_link(state(),TEXT,78478)
    for invalid in [TEXT.replace('49778','78478'),TEXT.replace('Worn Greatsword','other'),TEXT+'\n/s extra',
                    'prefix '+TEXT,TEXT.replace('item:','spell:')]:
        assert not pending_item_link(state(chat_edit_text=invalid),invalid,49778)
