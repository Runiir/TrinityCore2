import hashlib
import json
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PET_AI = ROOT/'src/server/game/AI/CoreAI/PetAI.cpp'
SPELL_ROW = Path(__file__).parent/'fixtures/furious_howl_spell_row.json'


@pytest.fixture(autouse=True)
def native_dbc_unavailable(monkeypatch):
    for name in ('read_bytes', 'read_text'):
        original = getattr(Path, name)
        def read(path, *args, original=original, **kwargs):
            if 'data/dbc' in path.as_posix():
                raise FileNotFoundError('native DBC unavailable in frozen checkout')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, name, read)


def pinned_howl_attributes():
    fixture = json.loads(SPELL_ROW.read_text())
    row = bytes.fromhex(fixture['row_hex'])
    assert hashlib.sha256(row).hexdigest() == fixture['row_sha256']
    assert fixture['source_sha256'] == '088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f'
    assert fixture['source_magic'] == 'WDBC'
    assert fixture['layout'] == 'little_endian_uint32_fields'
    assert len(row) == fixture['record_size'] == fixture['field_count'] * 4
    fields = struct.unpack(f"<{fixture['field_count']}I", row)
    assert fixture['spell_id_field_index'] == 0 and fields[0] == 24604
    assert fixture['attributes_ex5_field_index'] == 6
    return fields[6]


def test_actual_update_allies_includes_owner_and_reaches_native_buff_target_boundary(tmp_path):
    howl_attributes = pinned_howl_attributes()
    source = PET_AI.read_text()
    update = source[source.index('void PetAI::UpdateAllies()'):source.index('void PetAI::KilledUnit')]
    old = update.replace('PetAI::UpdateAllies()', 'PetAI::OldUpdateAllies()').replace(
        'GetMembersCount() + 1','GetMembersCount() + 2').replace(
        '    m_AllySet.insert(owner->GetGUID());\n','')
    old = old.replace('    m_AllySet.clear();',
        '    if (group && !group->isRaidGroup() && m_AllySet.size() == group->GetMembersCount()+2) return;\n    m_AllySet.clear();')
    old = old.rstrip()[:-1] + '    else m_AllySet.insert(owner->GetGUID());\n}\n'
    info = (ROOT/'src/server/game/Spells/SpellInfo.cpp').read_text()
    target_guard = info[info.index('    if (!unitTarget->IsPlayer())'):
                        info.index('    if (!IsAllowingDeadTarget()', info.index('    if (!unitTarget->IsPlayer())'))]
    spell = (ROOT/'src/server/game/Spells/Spell.cpp').read_text()
    begin = spell.index('        for (auto ihit = m_UniqueTargetInfo.begin()',spell.index('bool Spell::CanAutoCast'))
    membership = spell[begin:spell.index('\n    }',begin)]
    code = tmp_path/'pet.cpp'
    code.write_text('''
#include <set>
#include <vector>
#include <cassert>
using uint32=unsigned;
constexpr unsigned IN_MILLISECONDS=1000;
struct Player; struct Group;
struct Unit { unsigned guid; bool player=false; int map=0; Unit* owner=nullptr;
 virtual ~Unit()=default; virtual Player* ToPlayer(){return nullptr;}
 Unit* GetCharmerOrOwner(){return owner;} unsigned GetGUID(){return guid;}
 bool IsPlayer(){return player;} bool IsControlledByPlayer(){return !player;}
};
struct Player:Unit { Group* group=nullptr; int subgroup=0;
 Player* ToPlayer()override{return this;} Group* GetGroup(){return group;}
 bool IsInMap(Unit* other){return map==other->map;}
};
struct GroupReference { Player* source; GroupReference* following=nullptr;
 Player* GetSource(){return source;} GroupReference* next(){return following;}
};
struct Group { bool raid=false; unsigned size=1, scans=0; GroupReference* first=nullptr;
 bool isRaidGroup(){return raid;} unsigned GetMembersCount(){return size;}
 GroupReference* GetFirstMember(){++scans;return first;}
 bool SameSubGroup(Player* owner,Player* target){return owner->subgroup==target->subgroup;}
};
class PetAI {public: Unit* me; unsigned m_updateAlliesTimer=0; std::set<unsigned> m_AllySet;
 void UpdateAllies(); void OldUpdateAllies();};
''' + update + old + '''
constexpr int SPELL_CAST_OK=0, SPELL_FAILED_TARGET_NOT_PLAYER=1,
 SPELL_FAILED_TARGET_IS_PLAYER_CONTROLLED=2, SPELL_FAILED_TARGET_IS_PLAYER=3;
constexpr int SPELL_ATTR3_ONLY_ON_PLAYER=1, SPELL_ATTR5_NOT_ON_PLAYER_CONTROLLED_NPC=256,
 SPELL_ATTR5_NOT_ON_PLAYER=512;
bool HasAttribute(int flag){return (''' + str(howl_attributes) + ''' & flag)!=0;}
int CheckTargetBoundary(Unit* unitTarget){
''' + target_guard + '''return SPELL_CAST_OK;}
struct Hit { unsigned TargetGUID; };
bool SelectedTargetMembership(unsigned targetguid,std::vector<Hit> const& m_UniqueTargetInfo){
''' + membership + '''return false;}
unsigned eligible(PetAI& ai,Player& owner,Unit& pet){
 unsigned count=0;
 for(auto guid:ai.m_AllySet){Unit* target=guid==owner.guid ? static_cast<Unit*>(&owner) : &pet;
  if(CheckTargetBoundary(target)==SPELL_CAST_OK && SelectedTargetMembership(guid,{{owner.guid}})) ++count;
 } return count;
}
int main(){
 Player owner;owner.guid=11;owner.player=true; Unit pet;pet.guid=22;pet.owner=&owner;
 Group group;GroupReference own{&owner};group.first=&own;owner.group=&group;
 PetAI historical{&pet};historical.OldUpdateAllies();
 assert(historical.m_AllySet==std::set<unsigned>{22});assert(eligible(historical,owner,pet)==0);
 PetAI ai{&pet};ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22}));
 assert(eligible(ai,owner,pet)==1);unsigned scans=group.scans;ai.UpdateAllies();assert(group.scans==scans+1);
 Player peer;peer.guid=33;peer.player=true;GroupReference peerRef{&peer};own.following=&peerRef;group.size=2;
 ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22,33}));
 scans=group.scans;ai.UpdateAllies();assert(group.scans==scans+1);
 Player replacement;replacement.guid=44;replacement.player=true;peerRef.source=&replacement;
 ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22,44}));
 replacement.map=1;ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22}));
 replacement.map=0;replacement.subgroup=1;ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22}));
 replacement.subgroup=0;ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22,44}));
 peerRef.source=&peer;
 group.raid=true;peer.subgroup=1;ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22}));
 peer.subgroup=0;peer.map=1;ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22}));
 peer.map=0;ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22,33}));
 owner.group=nullptr;ai.UpdateAllies();assert((ai.m_AllySet==std::set<unsigned>{11,22}));
 ai.UpdateAllies();assert(ai.m_updateAlliesTimer==10000);
 assert(CheckTargetBoundary(&pet)==SPELL_FAILED_TARGET_IS_PLAYER_CONTROLLED);
 assert(CheckTargetBoundary(&owner)==SPELL_CAST_OK);
 assert(!SelectedTargetMembership(pet.guid,{{owner.guid}}));
}
''')
    binary=tmp_path/'pet'
    subprocess.run(['c++','-std=c++17',str(code),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)


def test_furious_howl_pinned_flag_rejects_player_controlled_npc():
    assert pinned_howl_attributes() == 0x100
    # Bind the fixture field to the native declared flag/layout, not a guessed bit.
    definitions=(ROOT/'src/server/shared/SharedDefines.h').read_text()
    assert 'SPELL_ATTR5_NOT_ON_PLAYER_CONTROLLED_NPC                        = 0x00000100' in definitions
    structure=(ROOT/'src/server/game/DataStores/DBCStructure.h').read_text()
    assert 'uint32  AttributesEx5;                                  // 6' in structure
    assert len(PET_AI.read_text().splitlines())<1000
