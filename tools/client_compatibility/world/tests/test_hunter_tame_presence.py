"""Tame creates level9 before late owner links and the native level10 update."""
import copy
import pytest
from tools.client_compatibility import interaction_hunter_tame_capture as tame
from tools.client_compatibility import interaction_pet_dismiss as base
from tools.client_compatibility.world.objects import INDEX as I

PET=17383895845845336071


def sample():
    return [
        {'guid':PET,'kind':3,'map':0,'update_type':2,'fields':{
            I['UNIT_FIELD_CREATEDBY']:6,I['UNIT_FIELD_CREATEDBY']+1:0,
            I['UNIT_FIELD_PETNUMBER']:6,I['OBJECT_FIELD_ENTRY']:299,I['UNIT_FIELD_LEVEL']:9}},
        {'guid':PET,'update_type':0,'fields':{I['UNIT_FIELD_SUMMONEDBY']:6,I['UNIT_FIELD_SUMMONEDBY']+1:0}},
        {'guid':PET,'update_type':0,'fields':{I['UNIT_FIELD_LEVEL']:10}},
        {'guid':6,'update_type':0,'fields':{I['UNIT_FIELD_SUMMON']:PET&0xffffffff,I['UNIT_FIELD_SUMMON']+1:PET>>32}}]


def oracle(monkeypatch,rows):
    class Cursor:
        queued=[]
        def __init__(self,*args):self.queued=[]
        def poll(self):
            queued,self.queued=self.queued,[];return iter(queued)
    parse=lambda body:[copy.deepcopy(rows[body[0]])]
    monkeypatch.setattr(base,'Cursor',Cursor);monkeypatch.setattr(base,'records',parse)
    monkeypatch.setattr(tame,'records',parse)
    return tame.TamePresence('owned',6,1)


def send(o,index):
    o.cursor.queued.append({'time':2+index,'session':'owned','direction':'from_native',
        'name':'SMSG_UPDATE_OBJECT','body':bytes([index]).hex()});o.poll()


def test_ui153_creation_requires_both_late_native_ownership_links(monkeypatch):
    o=oracle(monkeypatch,sample())
    for i in range(3):
        send(o,i);assert not o.present()
    send(o,3)
    assert o.present() and o.pet['guid']==PET and o.pet['fields'][I['UNIT_FIELD_LEVEL']]==10
    o.removed.add(PET);assert not o.poll().present()


@pytest.mark.parametrize('fault',['foreign_creator','foreign_owner','no_pet_number','wrong_summon','removed'])
def test_late_link_cannot_admit_a_foreign_unlinked_or_removed_pet(monkeypatch,fault):
    r=sample()
    if fault=='foreign_creator':r[0]['fields'][I['UNIT_FIELD_CREATEDBY']]=2
    elif fault=='foreign_owner':r[1]['fields'][I['UNIT_FIELD_SUMMONEDBY']]=2
    elif fault=='no_pet_number':r[0]['fields'].pop(I['UNIT_FIELD_PETNUMBER'])
    elif fault=='wrong_summon':r[3]['fields'][I['UNIT_FIELD_SUMMON']]+=1
    o=oracle(monkeypatch,r)
    if fault=='removed':o.removed.add(PET)
    for i in range(4):send(o,i)
    assert not o.present()
