"""The captured Pet book uses packed PETACTION slots and omits native-hidden91702."""
import copy,json
from pathlib import Path
import pytest
from tools.client_compatibility.interaction_pet_spellbook_tab import book_checks


def sample():
    v=json.loads((Path(__file__).parent/'fixtures/public_pet_spellbook_ui120.json').read_text())
    return v['book'],v['native_catalog'],{int(k):r for k,r in v['spell_rows'].items()},v['book']['pet']['guid']


def test_real_public_pet_book_matches_native_visible_spells_commands_and_reactions():
    book,native,spells,guid=sample()
    assert spells[91702]['attributes']&0x80 and all(book_checks(book,native,spells,guid).values())
    # Disabled empty slots retain prior text internally; their API supplies no
    # pet action, so they cannot be counted as displayed pet spell contents.
    assert len([r for r in book['rows'] if r.get('api_kind')=='PETACTION'])==10


@pytest.mark.parametrize('change',['book_type','owner','missing_command','wrong_encoding','unknown_spell',
    'wrong_name','wrong_passivity','wrong_id','duplicate_slot','missing_hidden_flag','untrained','empty'])
def test_pet_book_rejects_incomplete_or_changed_native_contents(change):
    book,native,spells,guid=copy.deepcopy(sample())
    spell=next(r for r in book['rows'] if r.get('id')==3110)
    if change=='book_type':book['book_type']='spell'
    elif change=='owner':guid='Pet-0-1-0-0-416-00000000FF'
    elif change=='missing_command':book['rows'].pop(0)
    elif change=='wrong_encoding':book['rows'][0]['api_id']=native['buttons'][-3]
    elif change=='unknown_spell':spell['api_id']+=1
    elif change=='wrong_name':spell['name']='Other spell'
    elif change=='wrong_passivity':spell['passive']=True
    elif change=='wrong_id':spell['id']=123
    elif change=='duplicate_slot':book['rows'][0]['slot']=7
    elif change=='missing_hidden_flag':spells[91702]['attributes']&=~0x80
    elif change=='untrained':spell['known']=False
    elif change=='empty':book['rows']=[]
    assert not all(book_checks(book,native,spells,guid).values())
