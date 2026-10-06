"""Public catalogs must retain native ownership, modes, action semantics and cooldowns."""
import copy,json
from pathlib import Path
import pytest
from tools.client_compatibility.interaction_pet_spellbook_tab import catalog_checks,modern_catalog
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid


def sample():
    native=json.loads((Path(__file__).parent/'fixtures/native_control_pet_ui119.json').read_text())['decoded']
    modern={'guid':list(modern_guid(native['guid'],0)),'family':23,'spec':0,'duration':0,'command':1,'flags':0,'react':3,
        'buttons':[0x03800002,0x03800001,0x03800004,0xc0800c26,0xc08018a3,0x00800000,
            0x00800000,0x03000003,0x03000001,0x03000000],
        'actions':[0x00816636,0x00807de9,0xc08018a3,0xc0800c26],'cooldowns':[]}
    return native,modern


def test_captured_native_and_pinned_modern_catalog_semantics_agree():
    n,m=sample();assert all(catalog_checks(n,m,n['guid'],0).values())


@pytest.mark.parametrize('change',['guid','family','duration','command','flags','react','spec','lost_button',
    'wrong_type','wrong_spell','missing_spell','cooldown'])
def test_public_catalog_cannot_pass_lost_or_changed_native_authority(change):
    n,m=copy.deepcopy(sample())
    if change=='guid':m['guid'][0]+=1
    elif change in ['family','duration','command','flags','react','spec']:m[change]+=1
    elif change=='lost_button':m['buttons'].pop()
    elif change=='wrong_type':m['buttons'][0]=n['buttons'][0]
    elif change=='wrong_spell':m['actions'][0]+=1
    elif change=='missing_spell':m['actions'].pop()
    elif change=='cooldown':m['cooldowns']=[[3110,100,200,1.0,1]]
    assert not all(catalog_checks(n,m,n['guid'],0).values())


def test_modern_reader_consumes_the_complete_pinned_packet():
    n,m=sample();w=Writer().guid(*m['guid']).pack('HHIBBB',[23,0,0,1,0,3])
    body=w.pack('10I',m['buttons']).pack('3I',[4,0,0]).pack('4I',m['actions']).finish()
    assert modern_catalog(body.hex())==m
    with pytest.raises(ValueError):modern_catalog((body+b'x').hex())
