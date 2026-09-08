"""Native getter/crit-consumer replay; objects and eligible spellmods are stubs."""
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def function_source(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def test_fire_elemental_native_owner_and_spell_crit_consumer(tmp_path):
    owners = list((ROOT / 'src/server/game/Entities/Object').glob('*.cpp'))
    signature = 'Player* WorldObject::GetSpellModOwner() const'
    sources = [p.read_text() for p in owners if signature in p.read_text()]
    assert len(sources) == 1
    getter = function_source(sources[0], signature)
    crit = function_source(
        (ROOT / 'src/server/game/Entities/Unit/Unit.cpp').read_text(),
        'float Unit::SpellCritChanceDone(',
    )
    code = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
using uint32 = std::uint32_t;
enum { TYPEID_UNIT, TYPEID_PLAYER, TYPEID_GAMEOBJECT, TYPEID_OTHER };
enum { UNIT_MASK_PET=1, UNIT_MASK_TOTEM=2, UNIT_MASK_GUARDIAN=4,
       UNIT_MASK_HUNTER_PET=8, UNIT_MASK_MINION=16 };
enum { SPELL_DAMAGE_CLASS_MAGIC, SPELL_DAMAGE_CLASS_MELEE,
       SPELL_DAMAGE_CLASS_RANGED, SPELL_DAMAGE_CLASS_NONE };
using SpellSchoolMask = int;
using WeaponAttackType = int;
constexpr int SPELL_SCHOOL_MASK_NORMAL=1, SPELL_SCHOOL_MASK_FIRE=4;
constexpr int SPELL_ATTR0_CU_CAN_CRIT=1, PLAYER_SPELL_CRIT_PERCENTAGE1=0;
constexpr int SPELL_AURA_MOD_SPELL_CRIT_CHANCE_SCHOOL=0;
enum class SpellModOp { CritChance };
int GetFirstSchoolInMask(int) { return 0; }
struct SpellInfo {
    int DmgClass=SPELL_DAMAGE_CLASS_MAGIC;
    bool CanCrit=true, EligibleMod=true;
    bool HasAttribute(int) const { return CanCrit; }
};
struct Player; struct Creature; struct GameObject; struct Totem;
struct WorldObject {
    int Type=TYPEID_OTHER;
    virtual ~WorldObject()=default;
    int GetTypeId() const { return Type; }
    virtual Player* ToPlayer() { return nullptr; }
    virtual Creature const* ToCreature() const { return nullptr; }
    virtual GameObject const* ToGameObject() const { return nullptr; }
    Player* GetSpellModOwner() const;
};
struct Unit : WorldObject {
    Unit* Owner=nullptr;
    float m_baseSpellCritChance=5, LocalCrit=2, PlayerCrit=37;
    Unit* GetOwner() const { return Owner; }
    virtual Totem* ToTotem() { return nullptr; }
    float GetFloatValue(int) const { return PlayerCrit; }
    float GetTotalAuraModifierByMiscMask(int,int) const { return LocalCrit; }
    float GetUnitCriticalChanceDone(int) const { return 11; }
    float SpellCritChanceDone(SpellInfo const*,SpellSchoolMask,WeaponAttackType,bool) const;
};
struct Player : Unit {
    Player() { Type=TYPEID_PLAYER; }
    Player* ToPlayer() override { return this; }
    int ModCalls=0;
    void ApplySpellMod(SpellInfo const* spell,SpellModOp,float& value) {
        ++ModCalls;
        if (spell->EligibleMod) value += 3;
    }
};
struct Creature : Unit {
    uint32 Entry=15438, Mask=UNIT_MASK_GUARDIAN;
    Creature() { Type=TYPEID_UNIT; }
    Creature const* ToCreature() const override { return this; }
    bool HasUnitTypeMask(uint32 mask) const { return (Mask&mask)!=0; }
    bool IsGuardian() const { return (Mask&UNIT_MASK_GUARDIAN)!=0; }
    uint32 GetEntry() const { return Entry; }
};
struct Totem : Creature {
    Totem() { Entry=15439; Mask=UNIT_MASK_TOTEM; }
    Totem* ToTotem() override { return this; }
};
struct GameObject : WorldObject {
    Unit* Owner=nullptr;
    GameObject() { Type=TYPEID_GAMEOBJECT; }
    GameObject const* ToGameObject() const override { return this; }
    Unit* GetOwner() const { return Owner; }
};
'''
    code += getter + '\n' + crit
    code += r'''
int main() {
    Player player; Totem totem; Creature fire;
    totem.Owner=&player; fire.Owner=&totem;
    assert(fire.GetOwner()==&totem && totem.GetOwner()==&player);
    assert(totem.ToPlayer()==nullptr);
    assert(fire.GetSpellModOwner()==&player);
    SpellInfo spell;
    // Native creature base + its local aura + eligible owner spellmod.
    // The player's 37% crit value must never become the guardian's base.
    assert(fire.SpellCritChanceDone(&spell,SPELL_SCHOOL_MASK_FIRE,0,false)==10);
    assert(player.ModCalls==1);
    spell.EligibleMod=false;
    assert(fire.SpellCritChanceDone(&spell,SPELL_SCHOOL_MASK_FIRE,0,false)==7);
    fire.LocalCrit=0;
    assert(fire.SpellCritChanceDone(&spell,SPELL_SCHOOL_MASK_FIRE,0,false)==5);
    fire.LocalCrit=2;
    spell.CanCrit=false;
    assert(fire.SpellCritChanceDone(&spell,SPELL_SCHOOL_MASK_FIRE,0,false)==0);
    spell.CanCrit=true; spell.EligibleMod=true;
    assert(player.GetSpellModOwner()==&player);
    assert(player.SpellCritChanceDone(&spell,SPELL_SCHOOL_MASK_FIRE,0,false)==40);
    assert(totem.GetSpellModOwner()==&player);
    GameObject gameObject; gameObject.Owner=&player;
    assert(gameObject.GetSpellModOwner()==&player);
    gameObject.Owner=&totem;
    assert(gameObject.GetSpellModOwner()==nullptr);
    Creature direct; direct.Entry=999; direct.Owner=&player;
    assert(direct.GetSpellModOwner()==&player);
    assert(direct.SpellCritChanceDone(&spell,SPELL_SCHOOL_MASK_FIRE,0,false)==10);
    auto rejected = [&] {
        assert(fire.GetSpellModOwner()==nullptr);
        int calls=player.ModCalls;
        assert(fire.SpellCritChanceDone(&spell,SPELL_SCHOOL_MASK_FIRE,0,false)==0);
        assert(player.ModCalls==calls);
    };
    fire.Entry=999; rejected(); fire.Entry=15438;
    fire.Mask=UNIT_MASK_MINION; rejected(); fire.Mask=UNIT_MASK_GUARDIAN;
    totem.Entry=999; rejected(); totem.Entry=15439;
    fire.Owner=nullptr; rejected(); fire.Owner=&totem;
    totem.Owner=nullptr; rejected();
    Creature nonPlayer; totem.Owner=&nonPlayer; rejected();
    // Identical entry on an ordinary creature is not a typed Totem owner.
    nonPlayer.Entry=15439; nonPlayer.Owner=&player;
    fire.Owner=&nonPlayer; rejected();
    // No traversal through an arbitrary extra owner hop.
    Totem extra; extra.Owner=&player; totem.Owner=&extra;
    fire.Owner=&totem; rejected();
    // A plain creature's direct player owner stays outside original masks.
    fire.Mask=0; fire.Owner=&player; rejected();
}
'''
    source = tmp_path / 'owner.cpp'
    source.write_text(code)
    executable = tmp_path / 'owner'
    subprocess.run(['c++', '-std=c++17', str(source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
