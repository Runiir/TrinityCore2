"""Execute both preview helpers with native cast-time/spell-mod calculations."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/server/game/Bots"


def _body(text, signature):
    start = text.index("{", text.index(signature))
    end, depth = start + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def test_both_preview_helpers_use_native_modifiers_without_spending_proc(tmp_path):
    controller = (BOT / "BotControllerCombat.cpp").read_text()
    candidates = (BOT / "BotClassSpecActionProfileCandidates.cpp").read_text()
    player = (ROOT / "src/server/game/Entities/Player/Player.cpp").read_text()
    world = (ROOT / "src/server/game/Entities/Object/WorldObjectSpells.cpp").read_text()
    functions = [
        "void Player::GetSpellModValues(SpellInfo const* spellInfo, SpellModOp op, Spell* spell, T base, int32* flat, float* pct) const",
        "void Player::ApplySpellMod(SpellInfo const* spellInfo, SpellModOp op, T& basevalue, Spell* spell /*= nullptr*/) const",
        "void Player::ApplyModToSpell(SpellModifier* mod, Spell* spell)",
    ]
    source = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <ranges>
#include <set>
#include <vector>
using int32=int32_t; using uint32=uint32_t;
#define ASSERT assert
namespace Trinity { template<class I, class S> struct IteratorPair {
 I first; S last; I begin() const {return first;} S end() const {return last;}
}; }
float CalculatePct(float base, int32 value) { return base*value/100; }
enum class SpellModOp {ChangeCastTime, CritChance};
enum SpellModType {SPELLMOD_FLAT, SPELLMOD_PCT};
enum {CHEAT_CASTTIME, SPELL_ATTR0_IS_ABILITY, SPELL_ATTR0_IS_TRADESKILL,
 SPELL_ATTR3_IGNORE_CASTER_MODIFIERS, SPELL_ATTR0_USES_RANGED_SLOT,
 SPELL_ATTR2_AUTO_REPEAT, TYPEID_PLAYER, TYPEID_UNIT, UNIT_MOD_CAST_SPEED,
 RANGED_ATTACK=0};
struct SpellInfo {
 int32 base=2900; int SpellFamilyName=9; int SpellVisual[1]={0};
 bool ranged=true; bool HasAttribute(int attr) const {
  return ranged && (attr==SPELL_ATTR0_IS_ABILITY || attr==SPELL_ATTR0_USES_RANGED_SLOT);
 }
 uint32 CalcCastTime(int) const {return std::max<int32>(0,base);}
};
struct Aura {int charges=1; bool IsUsingCharges(){return true;} int GetCharges(){return charges;}};
struct Spell {std::set<Aura*> m_appliedMods;};
struct SpellModifier {SpellModOp op=SpellModOp::ChangeCastTime; SpellModType type=SPELLMOD_PCT; Aura* ownerAura;};
struct SpellModifierByClassMask : SpellModifier {int32 value=-100;};
struct Player; using Unit=Player;
struct Player {
 std::vector<SpellModifier*> m_spellMods; Spell* m_spellModTakingSpell=nullptr;
 float m_modAttackSpeedPct[1]={1}; float castSpeed=1;
 int getLevel() const {return 85;}
 Player* GetSpellModOwner(){return this;} Player* ToUnit(){return this;}
 bool IsPlayer() const{return true;} Player const* ToPlayer() const{return this;}
 bool GetCommandStatus(int) const{return false;} int GetTypeId() const{return TYPEID_PLAYER;}
 float GetFloatValue(int) const{return castSpeed;} bool HasAura(int) const{return false;}
 bool IsAffectedBySpellmod(SpellInfo const*, SpellModifier*, Spell*) const{return true;}
 template<class T> void GetSpellModValues(SpellInfo const*, SpellModOp, Spell*, T, int32*, float*) const;
 template<class T> void ApplySpellMod(SpellInfo const*, SpellModOp, T&, Spell*) const;
 static void ApplyModToSpell(SpellModifier*, Spell*);
 void ModSpellCastTime(SpellInfo const* spellInfo, int32& castTime, Spell* spell)
''' + _body(world, "void WorldObject::ModSpellCastTime(") + "\n};\n"
    for signature in functions:
        source += ("template<class T>\n" if "T " in signature or "T&" in signature else "")
        source += signature + _body(player, signature) + "\n"
    source += "uint32 CastTimeMs(Player const* bot, SpellInfo const* spellInfo)" + _body(controller, "uint32 CastTimeMs(")
    source += "\nuint32 ProfileSpellCastTimeMs(Player const* bot, SpellInfo const* spellInfo)" + _body(candidates, "uint32 ProfileSpellCastTimeMs(")
    source += "\nstruct BotActionProfileSpell { bool RequiresInstantCast=false; uint32 MaxCastTimeMs=1000; };\n"
    source += "bool MeetsCastDirectives(Player const* bot, BotActionProfileSpell const& spell, SpellInfo const* spellInfo)" + _body(controller, "bool MeetsCastDirectives(")
    source += r'''
int main() {
 Player hunter; SpellInfo aimed; BotActionProfileSpell gate;
 auto check=[&](uint32 expected) {
  assert(CastTimeMs(&hunter,&aimed)==expected);
  assert(ProfileSpellCastTimeMs(&hunter,&aimed)==expected);
  assert(MeetsCastDirectives(&hunter,gate,&aimed)==(expected<=1000));
 };
 check(2900); hunter.m_modAttackSpeedPct[0]=0.8f; check(2320);
 Aura fire; SpellModifierByClassMask modifier; modifier.ownerAura=&fire;
 hunter.m_spellMods={&modifier};
 for(int i=0;i<10;++i) {check(0); assert(fire.charges==1); assert(!hunter.m_spellModTakingSpell);}
 assert(hunter.m_spellMods.size()==1 && hunter.m_spellMods[0]==&modifier && modifier.value==-100);
 gate.RequiresInstantCast=true; check(0); gate.RequiresInstantCast=false;
 modifier.value=-50; check(1160); // ordinary modifier plus ranged haste, still too slow
 modifier.type=SPELLMOD_FLAT; modifier.value=-2000; check(720);
 modifier.value=-4000; check(0); // retain nonnegative clamp
 modifier.type=SPELLMOD_FLAT; modifier.value=500; aimed.base=0; check(0);
 hunter.m_spellMods.clear();
 aimed.base=2900; aimed.ranged=false; hunter.castSpeed=0.5f; check(1450);
 assert(CastTimeMs(nullptr,&aimed)==0 && ProfileSpellCastTimeMs(nullptr,&aimed)==0);
 assert(CastTimeMs(&hunter,nullptr)==0 && ProfileSpellCastTimeMs(&hunter,nullptr)==0);
 // Native execution remains consuming: a real Spell registers the same aura.
 aimed.ranged=true; modifier.type=SPELLMOD_PCT; modifier.value=-100;
 hunter.m_spellMods={&modifier}; Spell execution; int32 cast=2900;
 hunter.ModSpellCastTime(&aimed,cast,&execution);
 assert(cast==0 && execution.m_appliedMods.count(&fire)==1 && fire.charges==1);
 // Null is not a universal API immunity: native active-taking scope redirects it.
 Spell active; hunter.m_spellModTakingSpell=&active; cast=2900;
 hunter.ModSpellCastTime(&aimed,cast,nullptr);
 assert(active.m_appliedMods.count(&fire)==1);
 hunter.m_spellModTakingSpell=nullptr;

}
'''
    # Consumer remains wired to the preview for evidence and both hard gates.
    assert "candidate.CastTimeMs = ProfileSpellCastTimeMs(bot, spellInfo);" in candidates
    assert "spell.MaxCastTimeMs && ProfileSpellCastTimeMs(bot, spellInfo) > spell.MaxCastTimeMs" in candidates
    assert "spell.RequiresInstantCast && ProfileSpellCastTimeMs(bot, spellInfo) > 0" in candidates
    path = tmp_path / "preview.cpp"
    path.write_text(source)
    binary = tmp_path / "preview"
    subprocess.run(["c++", "-std=c++20", str(path), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
