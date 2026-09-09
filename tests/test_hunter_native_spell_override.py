"""Native override resolution, real hostile preflight and final cast boundary."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/server/game/Bots"


def body(text, signature):
    start = text.index("{", text.index(signature))
    end, depth = start + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def test_native_override_admission_and_fresh_direct_submission(tmp_path):
    fixture = json.loads((ROOT / "tests/fixtures/hunter_aimed_native_override.json").read_text())
    effect = fixture["override_effect_row"]
    assert (effect[3], effect[5], effect[12], effect[18], effect[24]) == (333, 82928, 10, 131072, 82926)
    unit = (ROOT / "src/server/game/Entities/Unit/Unit.cpp").read_text()
    executor = (BOT / "BotActionExecutor.cpp").read_text()
    controller = (BOT / "BotControllerCombat.cpp").read_text()
    candidates = (BOT / "BotClassSpecActionProfileCandidates.cpp").read_text()
    source = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>
using uint32=uint32_t; using uint8=uint8_t; using int32=int32_t;
using TriggerCastFlags=uint32;
constexpr uint32 TRIGGERED_NONE=0, TRIGGERED_IGNORE_POWER_COST=0x00000004;
constexpr int SPELL_AURA_OVERRIDE_ACTIONBAR_SPELLS=332, SPELL_AURA_OVERRIDE_ACTIONBAR_SPELLS_TRIGGERED=333;
constexpr int SPELL_ATTR8_IGNORE_SPELLCAST_OVERRIDE_COST=1;
constexpr int SPELL_RANGE_MELEE=1,SPELL_RANGE_RANGED=2,UNIT_STATE_CONTROLLED=1,UNIT_STATE_CASTING=2,UNIT_STATE_MOVING=4;
constexpr int CURRENT_CHANNELED_SPELL=1,CURRENT_GENERIC_SPELL=2,MOTION_SLOT_ACTIVE=0;
constexpr uint32 TARGET_FLAG_DEST_LOCATION=64, ShadowfiendSpellId=34433;
struct Guid {uint32 id=1; bool IsEmpty() const{return !id;} bool operator!=(Guid b)const{return id!=b.id;}};
struct SpellInfo {
 uint32 Id=0; int32 castTime=0,cost=0; uint32 CasterAuraSpell=0; bool ignoreCost=false;
 uint32 CasterAuraState=0,CasterAuraStateNot=0,ExcludeCasterAuraSpell=0,TargetAuraState=0,TargetAuraStateNot=0,TargetAuraSpell=0,ExcludeTargetAuraSpell=0;
 struct Range {int Flags=0;} range; Range* RangeEntry=&range; uint32 destination=0;
 bool HasAttribute(int)const{return ignoreCost;} uint32 CalcCastTime(int)const{return castTime;}
 bool NeedsComboPoints()const{return false;} uint32 GetExplicitTargetMask()const{return destination;}
};
struct AuraEffect {
 SpellInfo const* info; uint32 amount=82928,mask=131072; int misc=10; int charges=1;
 int GetMiscValue()const{return misc;} bool IsAffectingSpell(SpellInfo const* s)const{return mask==131072 && s->Id==19434;}
 int GetAmount()const{return amount;} SpellInfo const* GetSpellInfo()const{return info;}
};
struct Manager {std::map<uint32,SpellInfo> spells; SpellInfo const* GetSpellInfo(uint32 id)const {
 auto it=spells.find(id);return it==spells.end()?nullptr:&it->second;
}} manager; Manager* sSpellMgr=&manager;
struct History {
 uint32 blockedGcd=0,blockedCooldown=0; mutable uint32 last=0;
 bool HasGlobalCooldown(SpellInfo const* s)const{last=s->Id;return s->Id==blockedGcd;}
 bool IsReady(SpellInfo const* s)const{last=s->Id;return s->Id!=blockedCooldown;}
};
struct Motion {void Clear(int){} void MoveIdle(){}};
struct Position {float x,y,z;};
struct CastSpellExtraArgs {TriggerCastFlags flags; explicit CastSpellExtraArgs(TriggerCastFlags f):flags(f){}};
enum SpellCastResult {SPELL_CAST_OK,SPELL_FAILED};
struct Unit {
 using AuraEffectList=std::vector<AuraEffect const*>;
 AuraEffectList swaps,swaps2; std::set<uint32> learned{19434}; History history;
 int power=0; bool alive=true,moving=false; uint32 state=0; float distance=10,maxRange=40;
 mutable uint32 resolveCalls=0; uint32 castId=0,castFlags=0,checkedId=0; int casts=0; Motion motion;
 AuraEffectList const& GetAuraEffectsByType(int type)const{return type==332?swaps:swaps2;}
 SpellInfo const* GetCastSpellInfo(SpellInfo const* spellInfo,TriggerCastFlags& triggerFlag)const;
 bool HasSpell(uint32 id)const{return learned.count(id);} bool IsAlive()const{return alive;}
 bool IsInWorld()const{return true;} bool IsValidAttackTarget(Unit*,SpellInfo const* s=nullptr){if(s)checkedId=s->Id;return true;}
 bool IsWithinLOSInMap(Unit*)const{return true;} float GetExactDist(Unit*)const{return distance;}
 float GetSpellMinRangeForTarget(Unit*,SpellInfo const*)const{return 0;}
 float GetSpellMaxRangeForTarget(Unit*,SpellInfo const*)const{return maxRange;}
 float GetMeleeRange(Unit*)const{return 5;} float GetCombatReach()const{return 0;}
 bool IsWithinDistInMap(Unit*,float range)const{return distance<=range;}
 bool HasUnitState(int mask)const{return state&mask;} void* GetCurrentSpell(int)const{return nullptr;}
 History const* GetSpellHistory()const{return &history;} int GetComboPoints()const{return 0;}
 Guid GetComboTarget()const{return {};} Guid GetGUID()const{return {};}
 void* GetMap()const{return nullptr;} int getLevel()const{return 85;}
 void ModSpellCastTime(SpellInfo const*,int32&,void*){} bool isMoving()const{return moving;}
 void StopMoving(){moving=false;} Motion* GetMotionMaster(){return &motion;}
 void SetTarget(Guid){} float GetPositionX()const{return 0;} float GetPositionY()const{return 0;} float GetPositionZ()const{return 0;}
 int GetHealth()const{return 100;}int GetMaxHealth()const{return 100;}
 Unit const* GetVictim()const{return nullptr;}bool IsWithinMeleeRange(Unit*)const{return true;}
 bool HasAuraState(uint32,SpellInfo const*,Unit const*)const{return false;}
 bool HasAura(uint32 id)const{for(auto a:swaps2)if(a->info->Id==id)return true;return false;}
 SpellCastResult CastSpell(Unit*,uint32 id,CastSpellExtraArgs args){
  auto info=manager.GetSpellInfo(id); if(!info || (info->CasterAuraSpell&&!HasAura(info->CasterAuraSpell)))return SPELL_FAILED;
  castId=id;castFlags=args.flags;++casts;return SPELL_CAST_OK;
 }
 SpellCastResult CastSpell(Position,uint32 id,CastSpellExtraArgs args){return CastSpell(this,id,args);}
};
using Player=Unit;
using AuraStateType=uint32;
'''
    source += "SpellInfo const* Unit::GetCastSpellInfo(SpellInfo const* spellInfo,TriggerCastFlags& triggerFlag)const" + body(unit, "SpellInfo const* Unit::GetCastSpellInfo(")
    # Compile the shared production helper against fixture native adapters.
    helper = (BOT / "BotSpellResolution.h").read_text()
    source += "\n" + "\n".join(line for line in helper.splitlines() if not line.startswith("#include"))
    source += r'''
enum class BotActionResult {Ok,BadSpell,InvalidTarget,DeadTarget,NoLineOfSight,OutOfRange,Throttled,Casting,GlobalCooldown,Cooldown,NoMana,NoOwner,CastFailed,NoAction};
bool HasEnoughPowerForSpell(Player const* bot,SpellInfo const* info){return bot->power>=info->cost;}
bool HasNearbyProtectedEncounterTarget(Player*,Unit*){return false;}
bool SpellHasHostileMultiTargetSemantics(SpellInfo const*){return false;}
bool IsSchedulingResult(BotActionResult){return true;}
namespace BotCastWhileMoving {template<class F>bool StopUncoveredMovingCast(Player*,SpellInfo const*,F){return false;}}
struct Action {uint32 SpellId=19434;Guid TargetGuid,Target;bool InterruptCurrentChanneledSpell=false,SuppressAreaDamage=false;};
struct BotActionExecutor {
 uint32 _lastSpellCastResult=0;
 bool IsThrottled(Guid,uint32,Guid){return false;}void RecordFailure(Guid,uint32,Guid){}void RecordSuccess(Guid){}
 BotActionResult CheckHostileSpell(Player* owner,Player* bot,Unit* target,BotSpellResolution::Resolved const& resolved,bool interruptCurrentChanneledSpell)const;
 BotActionResult Submit(Player* owner,Player* bot,Unit* target,Action const& action);
};
'''
    source += "BotActionResult BotActionExecutor::CheckHostileSpell(Player* owner,Player* bot,Unit* target,BotSpellResolution::Resolved const& resolved,bool interruptCurrentChanneledSpell)const" + body(executor, "BotActionResult BotActionExecutor::CheckHostileSpell(")
    suffix = body(executor, "BotActionResult BotActionExecutor::ExecuteCombat(")
    suffix = suffix[suffix.index("    // Auto Shot/pet startup above"):]
    source += "\nBotActionResult BotActionExecutor::Submit(Player* owner,Player* bot,Unit* target,Action const& action) {\n" + suffix
    source += "\nuint32 CastTimeMs(Player const* bot, SpellInfo const* spellInfo)" + body(controller,"uint32 CastTimeMs(")
    source += "\nuint32 ProfileSpellCastTimeMs(Player const* bot, SpellInfo const* spellInfo)" + body(candidates,"uint32 ProfileSpellCastTimeMs(")
    source += "\nstruct BotActionProfileSpell{bool RequiresInstantCast=false;uint32 MaxCastTimeMs=1000;};\n"
    source += "bool MeetsCastDirectives(Player const* bot,BotActionProfileSpell const& spell,SpellInfo const* spellInfo)" + body(controller,"bool MeetsCastDirectives(")
    admission = candidates[candidates.index("        if (!selfTarget && !actionTarget)"):]
    admission = admission[:admission.index("\n        if (candidate.RejectReason.empty()")]
    source += r'''
enum class BotCombatActionCategory {Defensive,DispelCleanse,ExternalDefensive,HealAoe,HealEfficient,HealFast,Mitigation,UseItem,Damage};
struct ProfileSpell : BotActionProfileSpell {
 uint32 SpellId=19434;BotCombatActionCategory Category=BotCombatActionCategory::Damage;
 std::string CooldownGroup;float DamageWeight=1;int MinInjuredPlayers=0,MaxInjuredPlayers=0;
 bool RequiresInterruptibleTarget=false,RequiresMeleeRange=false,RequiresRangedRange=false,RequiresTargetNotVictim=false,RequiresTargetVictim=false;
};
struct Candidate {uint32 SpellId=19434,ResolvedSpellId=0,ResolvedTriggerFlags=0,CastTimeMs=0;std::string RejectReason;};
void* FindOnUseItemForSpell(Player*,uint32){return nullptr;}
bool MeetsHostileTargetHealthGate(ProfileSpell const&,float,bool){return true;}
float ProfileSpellMaximumRange(Player*,Unit*,SpellInfo const* info){return 40;}
bool HasEnoughPowerForProfileSpell(Player const* bot,SpellInfo const* info){return bot->power>=info->cost;}
Candidate Admit(Player* bot,Unit* target,ProfileSpell const& spell){
 Candidate candidate; candidate.SpellId=spell.SpellId;
 bool selfTarget=false,allyTarget=false,interruptsCurrentChanneledSpell=false;
 Unit* actionTarget=target;Unit* comboTarget=target;std::string conditionRejection;
 struct {std::string Role="dps";} profile;int healerTriageInjuredPlayers=0;
 std::map<std::string,bool> cooldownGroupsReady;
'''
    start=candidates.index("        auto const resolved = BotSpellResolution::Resolve(bot, spell.SpellId,")
    end=candidates.index("        Unit const* comboTarget",start)
    source += candidates[start:end] + admission + "\nreturn candidate;}\n"
    native=(BOT / "BotWorldPopulationMgrNativeAction.cpp").read_text()
    typed=body(native,"else if constexpr (std::is_same_v<T, BotNativeAction::CastSpell>)")
    source += r'''
Unit* typedTarget=nullptr;
namespace ObjectAccessor {Unit* GetUnit(Player&,Guid){return typedTarget;}}
namespace BotActionArbitration {struct Outcome {bool submitted;static Outcome Retryable(char const*){return {false};}static Outcome Submitted(char const*){return {true};}};}
BotActionArbitration::Outcome Typed(Player* bot,Action const& action)
''' + typed
    source += r'''
int main(){
 manager.spells[19434].Id=19434;manager.spells[19434].castTime=2900;manager.spells[19434].cost=50;
 manager.spells[82928].Id=82928;manager.spells[82928].CasterAuraSpell=82926;
 manager.spells[82926].Id=82926;manager.spells[777].Id=777;
 Player bot,owner;Unit target;AuraEffect aura{&manager.spells[82926]};BotActionExecutor executor;Action action;
 BotActionProfileSpell gate;ProfileSpell profile;typedTarget=&target;
 auto base=BotSpellResolution::Resolve(&bot,19434);assert(base.Effective->Id==19434&&base.Flags==TRIGGERED_NONE);
 assert(Admit(&bot,&target,profile).RejectReason=="cast_time_too_long");
 assert(!MeetsCastDirectives(&bot,gate,base.Effective));assert(ProfileSpellCastTimeMs(&bot,base.Effective)==2900);
 bot.swaps2={&aura};auto instant=BotSpellResolution::Resolve(&bot,19434);
 assert(instant.Requested->Id==19434&&instant.Effective->Id==82928&&instant.Flags==TRIGGERED_NONE);
 auto candidate=Admit(&bot,&target,profile);assert(candidate.RejectReason.empty()&&candidate.SpellId==19434&&candidate.ResolvedSpellId==82928);
 assert(Typed(&bot,action).submitted&&bot.castId==82928);
 assert(!bot.HasSpell(82928)&&MeetsCastDirectives(&bot,gate,instant.Effective));
 assert(ProfileSpellCastTimeMs(&bot,instant.Effective)==0&&aura.charges==1);
 assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::Ok);
 assert(bot.castId==82928&&bot.castFlags==TRIGGERED_NONE&&bot.checkedId==82928&&aura.charges==1);
 bot.learned.clear();assert(!Typed(&bot,action).submitted);assert(Admit(&bot,&target,profile).RejectReason=="unknown_requested_spell");assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::BadSpell);bot.learned.insert(19434);
 // A pure early safety preview must not be reused after intervening aura loss.
 auto early=BotSpellResolution::Resolve(&bot,19434);bot.swaps2.clear();int casts=bot.casts;
 assert(early.Effective->Id==82928);assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::NoMana);assert(bot.casts==casts);
 bot.power=50;assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::Ok&&bot.castId==19434);
 bot.swaps2={&aura};bot.history.blockedGcd=82928;assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::GlobalCooldown);
 assert(Admit(&bot,&target,profile).RejectReason=="global_cooldown");
 bot.history.blockedGcd=0;bot.history.blockedCooldown=82928;assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::Cooldown);
 assert(Admit(&bot,&target,profile).RejectReason=="cooldown_not_ready");
 bot.history.blockedCooldown=0;
 manager.spells[82928].CasterAuraSpell=999;assert(Admit(&bot,&target,profile).RejectReason=="missing_caster_aura");manager.spells[82928].CasterAuraSpell=82926;
 bot.distance=60;assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::OutOfRange);bot.distance=10;
 manager.spells[82928].cost=99;bot.power=0;assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::NoMana);
 assert(Admit(&bot,&target,profile).RejectReason=="insufficient_resource");
 manager.spells[82926].ignoreCost=true;assert(Admit(&bot,&target,profile).RejectReason.empty());assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::Ok&&bot.castFlags==TRIGGERED_IGNORE_POWER_COST);
 TriggerCastFlags flags=64|TRIGGERED_IGNORE_POWER_COST;manager.spells[82926].ignoreCost=false;
 assert(bot.GetCastSpellInfo(base.Requested,flags)->Id==82928&&flags==64);
 aura.mask=0;assert(BotSpellResolution::Resolve(&bot,19434).Effective->Id==19434);aura.mask=131072;
 bot.swaps=bot.swaps2;bot.swaps2.clear();assert(BotSpellResolution::Resolve(&bot,19434).Effective->Id==82928);
 assert(BotSpellResolution::Resolve(&bot,777).Effective->Id==777);
 action.SpellId=777;assert(!bot.HasSpell(777));
 assert(Typed(&bot,action).submitted&&bot.castId==777);
 assert(executor.Submit(&owner,&bot,&target,action)==BotActionResult::Ok&&bot.castId==777);
 assert(BotSpellResolution::Resolve(&bot,19434,true).Effective->Id==19434); // items unchanged
}
'''
    # Populate the replay from the literal captured DBC rows, not a successful
    # hand-authored instant-spell approximation.
    source=source.replace("uint32 amount=82928,mask=131072; int misc=10; int charges=1;",
        f"uint32 amount={effect[5]},mask={effect[18]}; int misc={effect[12]}; int charges={fixture['aura_options_row'][3]};")
    source=source.replace("manager.spells[19434].castTime=2900;manager.spells[19434].cost=50;",
        f"manager.spells[19434].castTime={fixture['base_cast_time_row'][1]};manager.spells[19434].cost={fixture['base_power_row'][1]};")
    source=source.replace("manager.spells[82928].CasterAuraSpell=82926;",
        f"manager.spells[82928].CasterAuraSpell={fixture['override_aura_restrictions_row'][5]};"
        f"manager.spells[82928].castTime={fixture['override_cast_time_row'][1]};")
    assert fixture["effective_power_entry"] == 0
    path=tmp_path/"override.cpp";path.write_text(source);binary=tmp_path/"override"
    subprocess.run(["c++","-std=c++17",str(path),"-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True)


def test_effective_identity_is_retained_and_execution_safety_order_preserved():
    candidates=(BOT / "BotClassSpecActionProfileCandidates.cpp").read_text()
    resolver=(BOT / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    controller=(BOT / "BotControllerCombat.cpp").read_text()
    executor=(BOT / "BotActionExecutor.cpp").read_text()
    assert 'candidate.SpellId = spell.SpellId;' in candidates
    assert 'candidate.ResolvedSpellId = spellInfo ? spellInfo->Id : 0;' in candidates
    assert 'candidate.ResolvedTriggerFlags = uint32(resolved.Flags);' in candidates
    assert '\\"resolved_spell_id\\\":' in candidates
    assert 'candidate.ResolvedTriggerFlags & TRIGGERED_IGNORE_POWER_COST' in controller
    for source in (controller,resolver):
        assert 'GetSpellInfo(candidate.ResolvedSpellId)' in source
        assert 'GetSpellInfo(best->ResolvedSpellId)' in source
        assert 'GetSpellInfo(candidate.SpellId)' not in source
        assert 'GetSpellInfo(best->SpellId)' not in source
    start=executor.index('auto const preview = BotSpellResolution::Resolve')
    early=executor.index('SpellHasHostileMultiTargetSemantics(preview.Effective)',start)
    startup=executor.index('// White swings, Auto Shot, and pet attacks',early)
    fresh=executor.index('auto const resolved = BotSpellResolution::Resolve',startup)
    recheck=executor.index('SpellHasHostileMultiTargetSemantics(resolved.Effective)',fresh)
    check=executor.index('CheckHostileSpell(owner, bot, target, resolved',recheck)
    movement=executor.index('BotCastWhileMoving::StopUncoveredMovingCast',check)
    cast=executor.index('bot->CastSpell(target, spellInfo->Id, castArgs)',movement)
    assert start < early < startup < fresh < recheck < check < movement < cast
    suffix=executor[fresh:cast]
    assert suffix.count('BotSpellResolution::Resolve(')==1
    assert 'CastSpellExtraArgs castArgs(resolved.Flags)' in suffix
    assert 'RecordFailure(bot->GetGUID(), action.SpellId, action.TargetGuid)' in suffix
