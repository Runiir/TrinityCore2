"""DPS-041: execute the setup branch, caller ordering and profile gate/rank slices.

Native world/spell services are deterministic doubles. Production compiled
conditions, prepull/reservation gates and comparator remain verbatim; this is
not a whole-server or landed-damage test.
"""
from pathlib import Path
import subprocess
import csv
import json
import re

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src/server/game/Bots"


def body(text, signature):
    start = text.index("{", text.index(signature))
    end, depth = start + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def test_hunter_mark_obeys_combat_ranking_through_setup_consumer(tmp_path):
    setup = (BOT / "BotWorldPopulationMgrPersistentSetup.cpp").read_text()
    execution = (BOT / "BotWorldPopulationMgrCombatExecution.cpp").read_text()
    resolver = (BOT / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    candidates = (BOT / "BotClassSpecActionProfileCandidates.cpp").read_text()
    profile = (BOT / "BotClassSpecActionProfile.h").read_text()
    catalog = (BOT / "BotCombatActionCatalog.h").read_text()
    reservation = (BOT / "BotWorldPopulationMgrRaidCooldownReservation.h").read_text()
    mark_start = setup.find("    Creature const* const hunterMarkCreature")
    if mark_start < 0:  # Allows the one-time old-producer counterexample replay.
        mark_start = setup.index("    if (bot->getClass() == CLASS_HUNTER &&")
    mark_branch = setup[mark_start:setup.index("    TryResolveBotBlocker(state, bot,", mark_start)]
    call_start = execution.index("    if (!hostileTargetOnly && state && TryEnsurePersistentCombatSetup")
    call_end = execution.index("hostileTargetOnly, movementCompatibleOnly);", call_start)
    caller = execution[call_start:call_end + len("hostileTargetOnly, movementCompatibleOnly);")]
    tag_start = resolver.index("        if (hostileTargetOnly && candidate.Profile.TargetSelector")
    tag_end = resolver.index("        SpellInfo const* candidateSpellInfo", tag_start)
    tag_gates = resolver[tag_start:tag_end]
    native_start = candidates.index("        else if (bot->HasUnitState(UNIT_STATE_CASTING)")
    native_end = candidates.index("        else if (spellInfo && spellInfo->CasterAuraState", native_start)
    native_gates = candidates[native_start:native_end]
    # Bind the existing Mark row to its tracked declaration and liveness update.
    sql = (ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql").read_text()
    row_start = sql.index("((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 5, 1130,")
    declaration = sql[sql.rfind("INSERT INTO `bot_rotation_action`", 0, row_start):row_start]
    columns = re.findall(r"`([^`]+)`", declaration.split(" VALUES", 1)[0])[1:]
    row = sql[row_start:sql.index("\n", row_start)].split("'dps'), ", 1)[1].removesuffix("),")
    values = next(csv.reader([row], quotechar="'", skipinitialspace=True))
    mark_row = dict(zip(columns[1:], values, strict=True))
    liveness = (ROOT / "sql/custom/world/2026_07_15_02_stonecore_hunter_rotation_liveness.sql").read_text()
    mark_bucket = int(re.search(r"`priority_bucket` = (\d+)", liveness)[1])
    assert int(mark_row["spell_id"]) == 1130 and mark_bucket == 6
    creature_header = (ROOT / "src/server/game/Entities/Creature/Creature.h").read_text()
    creature_source = (ROOT / "src/server/game/Entities/Creature/Creature.cpp").read_text()
    creature_data = (ROOT / "src/server/game/Entities/Creature/CreatureData.h").read_text()
    shared = (ROOT / "src/server/shared/SharedDefines.h").read_text()
    source = r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <map>
#include <set>
#include <string>
#include <string_view>
#include <vector>
using uint8=uint8_t; using uint16=uint16_t; using uint32=uint32_t;
using uint64=uint64_t; using int32=int32_t;
"""
    source += "enum class BotCombatActionCategory : uint8" + body(catalog, "enum class BotCombatActionCategory") + ";\n"
    for name in ("BotActionProfileSpell", "BotActionCandidate"):
        source += "struct " + name + body(profile, "struct " + name) + ";\n"
    source += "namespace BotRaidCooldownReservation" + body(reservation, "namespace BotRaidCooldownReservation") + "\n"
    source += r"""
struct ObjectGuid {
 uint64 value=0; uint64 GetCounter()const{return value;} void Clear(){value=0;}
 bool operator==(ObjectGuid const&)const=default;
 static ObjectGuid const Empty;
}; ObjectGuid const ObjectGuid::Empty{};
struct Aura {int GetDuration()const{return -1;} int GetStackAmount()const{return 1;} int GetCharges()const{return 1;}};
enum {CLASS_HUNTER=3, UNIT_STATE_CASTING=1, POWER_HOLY_POWER, POWER_SOUL_SHARDS,
 POWER_MANA, EQUIPMENT_SLOT_MAINHAND, EQUIPMENT_SLOT_OFFHAND};
using Powers=int;
enum SpellCastResult {SPELL_CAST_OK,SPELL_FAILED};
enum class BotActionResult {Casting,Ok,CastFailed,NoAction};
struct SpellInfo {uint32 Id;};
struct SpellMgr {SpellInfo const* GetSpellInfo(uint32 id)const {static SpellInfo s; s.Id=id;return &s;}} spellMgr;
SpellMgr* sSpellMgr=&spellMgr;
struct History {bool gcd=false,ready=true; bool HasGlobalCooldown(SpellInfo const*)const{return gcd;} bool IsReady(SpellInfo const*)const{return ready;}};
struct Creature;
struct Unit {
 virtual Creature const* ToCreature()const{return nullptr;}
 ObjectGuid guid; bool alive=true,los=true,marked=false; float distance=20;
 bool IsAlive()const{return alive;} ObjectGuid GetGUID()const{return guid;}
 Aura const* GetAura(uint32 id,ObjectGuid={})const{static Aura a;return id==1130&&marked?&a:nullptr;}
 bool HasAura(uint32 id,ObjectGuid={})const{return GetAura(id)!=nullptr;}
 uint32 GetCreatureTypeMask()const{return 1;}
};
struct CreatureTemplate {uint32 flags_extra=0,type_flags=0,rank=0;};
struct Creature:Unit {
 CreatureTemplate data;bool pet=false;
 Creature const* ToCreature()const override{return this;}
 CreatureTemplate const* GetCreatureTemplate()const{return &data;}
 bool IsPet()const{return pet;}
 bool IsDungeonBoss()const;
 bool isWorldBoss()const;
};
struct Player:Unit {
 bool combat=true,casting=false,moving=false; int klass=CLASS_HUNTER,focus=100;
 mutable History history; std::vector<uint32> submitted; std::vector<uint64> targets;
 bool IsInCombat()const{return combat;} int getClass()const{return klass;}
 bool HasSpell(uint32)const{return true;} bool HasUnitState(int)const{return casting;}
 History* GetSpellHistory()const{return &history;}
 ObjectGuid GetComboTarget()const{return {};};uint8 GetComboPoints()const{return 0;}
 int GetShapeshiftForm()const{return 0;} Unit* GetPet()const{return nullptr;}
 int GetPower(int p)const{return p==POWER_MANA?0:focus;}
 int GetMaxPower(int p)const{return p==POWER_MANA?0:100;}
 Powers GetPowerType()const{return 100;} std::set<int> getAttackers()const{return {};}
 bool isMoving()const{return moving;}
 SpellCastResult CastSpell(Unit* target,uint32 id,bool){
  if(casting||history.gcd||!history.ready||!target->alive||!target->los||target->distance>40)
   return SPELL_FAILED;
  if(id==2643&&focus<40)return SPELL_FAILED;
  submitted.push_back(id);targets.push_back(target->guid.value);
  if(id==1130)target->marked=true;return SPELL_CAST_OK;
 }
};
uint8 ReadyRuneCount(Player const*){return 0;}
uint32 EquippedTemporaryEnchant(Player const*,uint8){return 0;}
"""
    for constant, declaration in (
        ("CREATURE_FLAG_EXTRA_DUNGEON_BOSS", creature_data),
        ("CREATURE_TYPE_FLAG_BOSS_MOB", shared),
        ("CREATURE_ELITE_WORLDBOSS", shared),
    ):
        value = re.search(r"\b" + constant + r"\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)", declaration)[1]
        source += f"constexpr uint32 {constant}={value};\n"
    source += "bool Creature::IsDungeonBoss()const" + body(creature_header, "bool IsDungeonBoss() const") + "\n"
    source += "bool Creature::isWorldBoss()const" + body(creature_source, "bool Creature::isWorldBoss() const") + "\n"
    for signature in (
        "bool MaintainedAuraBlocksRefresh(Unit const* target, uint32 auraId, uint32 refreshBelowMs)",
        "bool HasMechanicTag(std::string const& tags, char const* required)",
        "std::string EvaluateCompiledConditions(Player const* bot, Unit const* target, Unit const* comboTarget, BotActionProfileSpell const& spell)",
    ):
        source += signature + body(candidates, signature) + "\n"
    source += r"""
struct ResolvedCombatAction {
 bool Valid=false; std::string Type,DebugName; uint32 SpellId=0; ObjectGuid TargetGuid;
};
struct WorldBotState {
 std::map<std::string,uint64> ReadinessRetryUntilMs;
 uint32 ProfileCastSuppressedSpellId=0;ObjectGuid ProfileCastSuppressedTargetGuid;
 uint64 ProfileCastSuppressedUntilMs=0;
};
uint64 NowMs(){return 10000;}
void RecordCombatAttempt(WorldBotState&,Player*,Unit*,char const*,ResolvedCombatAction*,BotActionResult,char const*){}
bool TryEnsurePersistentCombatSetup(WorldBotState& state,Player* bot,Unit* target){
""" + mark_branch + "return false;\n}\n"
    source += r"""
bool TryEnsureCombatTotems(WorldBotState&,Player*,Unit*,uint32){return false;}
bool HasMovementCompatibleLease(WorldBotState*,Player*,uint64){return false;}
std::vector<BotActionCandidate> declared;
std::vector<BotActionCandidate> evaluated;
ResolvedCombatAction ResolveProfileCombatAction(Player* bot, Unit* target,
 uint32 hostileCount,bool densityOnly,uint32 excludedSpellId,bool areaOnly,
 bool selfCenteredOnly,bool forbidArea,bool,bool hostileTargetOnly,bool) {
"""
    source += "auto candidatePreferred=[](BotActionCandidate const& candidate,BotActionCandidate const* current)" + body(resolver, "auto candidatePreferred =") + ";\n"
    source += "auto hasMechanicTag=[](std::string const& tags,char const* required)" + body(resolver, "auto hasMechanicTag =") + ";\n"
    source += r"""
 bool exactSingleTargetCalibration=true; // prove prepull tag is not a combat Mark ban
 BotRaidCooldownReservation::RouteContext cooldownRoute{
 true,true,true,false,"boss","boss","combat"};
 evaluated=declared; BotActionCandidate* best=nullptr;
 for(auto& candidate:evaluated) {
  auto const& spell=candidate.Profile;auto const* spellInfo=sSpellMgr->GetSpellInfo(candidate.SpellId);
  bool interruptsCurrentChanneledSpell=false;
  candidate.RejectReason=EvaluateCompiledConditions(bot,target,target,spell);
  if(!candidate.RejectReason.empty()){}
""" + native_gates + r"""
  else if(candidate.SpellId==2643&&bot->focus<40)candidate.RejectReason="insufficient_resource";
""" + tag_gates + r"""
  if(candidate.Profile.MinEnemies>hostileCount)candidate.RejectReason="enemy_count_too_low";
  if(candidate.RejectReason.empty()&&candidatePreferred(candidate,best))best=&candidate;
 }
 ResolvedCombatAction action;
 if(best){action.Valid=true;action.SpellId=best->SpellId;action.TargetGuid=target->guid;}
 return action;
}
BotActionResult Execute(WorldBotState* state,Player* bot,Unit* target,
 uint32 hostileCount=3,bool densityOnly=false,uint32 excludedSpellId=0,bool areaOnly=false,
 bool selfCenteredOnly=false,bool forbidArea=false,bool allowMultidot=true,bool hostileTargetOnly=false) {
""" + caller + r"""
 if(!action.Valid)return BotActionResult::NoAction;
 return bot->CastSpell(target,action.SpellId,false)==SPELL_CAST_OK?BotActionResult::Ok:BotActionResult::CastFailed;
}
BotActionCandidate Candidate(uint32 spell,uint8 bucket,BotCombatActionCategory category){
 BotActionCandidate a;a.SpellId=spell;a.ResolvedSpellId=spell;a.Category=category;
 a.Profile.SpellId=spell;a.Profile.Category=category;a.Profile.PriorityBucket=bucket;
 a.Profile.TargetSelector="enemy";return a;
}
int main(){
 // Mark identity/gates from declared row1001130; offensive density candidate
 // represents a legal opportunity, not a claim it was legal at each old tick.
 auto mark=Candidate(1130,6,BotCombatActionCategory::Debuff);
 mark.ActionId=1001130;mark.Profile.MechanicTags="hunters_mark,target,prepull";
 mark.Profile.ForbiddenTargetAura=1130;
 auto multi=Candidate(2643,2,BotCombatActionCategory::Aoe);
 multi.Profile.MechanicTags="multi_shot,aoe";multi.Profile.MinEnemies=3;
 auto automatic=Candidate(75,7,BotCombatActionCategory::AutoAttack);
 declared={mark,multi,automatic};
 Player bot;WorldBotState state;
 for(uint64 guid:{180,182,186}){
  Creature target;target.guid.value=guid;
  target.data={1073750272U,0,0}; // observed41806 template; ordinary parasite
  assert(!target.IsDungeonBoss()&&!target.isWorldBoss());
  assert(Execute(&state,&bot,&target)==BotActionResult::Ok);
  assert(bot.submitted.back()==2643&&bot.targets.back()==guid);
  assert(!target.marked);
 }
 // Same native pre-pull branch and stable boss preserve marking and no recast.
 Creature boss;boss.guid.value=39;boss.data={1,262252,1};bot.combat=false;
 assert(boss.isWorldBoss()); // real native type_flags bit, not rank/DB extra1
 assert(Execute(&state,&bot,&boss)==BotActionResult::Casting);
 assert(boss.marked&&bot.submitted.back()==1130);
 bot.combat=true;
 assert(Execute(&state,&bot,&boss)==BotActionResult::Ok&&bot.submitted.back()==2643);
 // The real body/head template types preserve first in-combat Mark even
 // when normal shots are eligible, addressing the old +0.452 boss Mark.
 for(auto data: {CreatureTemplate{1,262252,1},CreatureTemplate{8192,16778316,3},
                CreatureTemplate{CREATURE_FLAG_EXTRA_DUNGEON_BOSS,0,0}}){
  boss.data=data;boss.marked=false;
  assert(Execute(&state,&bot,&boss)==BotActionResult::Casting);
  assert(boss.marked&&bot.submitted.back()==1130);
 }
 // Rank alone is NOT native worldboss classification; pets are excluded.
 boss.data={0,0,CREATURE_ELITE_WORLDBOSS};assert(!boss.isWorldBoss());
 boss.data={0,CREATURE_TYPE_FLAG_BOSS_MOB,3};boss.pet=true;assert(!boss.isWorldBoss());
 boss.pet=false;boss.data={1,262252,1};
 // Noncreature/player targets deliberately use combat ranking. The genuine
 // compiled/tag gates preserve Mark when higher-ranked offense is unavailable.
 Unit playerTarget;playerTarget.guid.value=90001;bot.focus=0;
 assert(Execute(&state,&bot,&playerTarget)==BotActionResult::Ok&&bot.submitted.back()==1130);
 assert(Execute(&state,&bot,&playerTarget)==BotActionResult::Ok&&bot.submitted.back()==75);
 // Count2 forbids declared AoE, but does not forbid existing Mark fallback.
 bot.focus=100;playerTarget.marked=false;
 assert(Execute(&state,&bot,&playerTarget,2)==BotActionResult::Ok&&bot.submitted.back()==1130);
 playerTarget.marked=false;
 assert(Execute(&state,&bot,&playerTarget)==BotActionResult::Ok&&bot.submitted.back()==2643);
 assert(!playerTarget.marked);
 bot.combat=false;
 assert(Execute(&state,&bot,&playerTarget)==BotActionResult::Casting);
 assert(playerTarget.marked&&bot.submitted.back()==1130);
 for(bool inCombat:{false,true}){
  bot.combat=inCombat;boss.marked=false;auto count=bot.submitted.size();
  bot.casting=true;Execute(&state,&bot,&boss);assert(bot.submitted.size()==count);
  bot.casting=false;bot.history.gcd=true;Execute(&state,&bot,&boss);assert(bot.submitted.size()==count);
  bot.history.gcd=false;bot.history.ready=false;Execute(&state,&bot,&boss);assert(bot.submitted.size()==count);
  bot.history.ready=true;
 }
 bot.combat=true;boss.marked=true;boss.los=false;auto count=bot.submitted.size();
 assert(Execute(&state,&bot,&boss)==BotActionResult::CastFailed&&bot.submitted.size()==count);
 boss.los=true;
 assert(Execute(&state,&bot,&boss)==BotActionResult::Ok&&bot.submitted.back()==2643);
 // No eligible actions: preserve no-action, never fabricate a Mark or cast.
 declared={};assert(Execute(&state,&bot,&boss)==BotActionResult::NoAction);
 // Other-class branch falls through unchanged; this fixture does not simulate
 // other persistent setup owners or claim their native effects are tested.
 bot.klass=8;bot.combat=false;
 assert(!TryEnsurePersistentCombatSetup(state,&bot,&boss));
}
"""
    source = source.replace(
        'mark.Profile.MechanicTags="hunters_mark,target,prepull";',
        "mark.Profile.MechanicTags=" + json.dumps(mark_row["mechanic_tags"]) + ";",
    ).replace(
        "mark.Profile.ForbiddenTargetAura=1130;",
        "mark.Profile.ForbiddenTargetAura=" + mark_row["forbidden_target_aura"] + ";",
    )
    cpp = tmp_path / "hunter_mark_setup_order.cpp"
    cpp.write_text(source)
    executable = tmp_path / "hunter_mark_setup_order"
    subprocess.run(["c++", "-std=c++20", "-O0", str(cpp), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
