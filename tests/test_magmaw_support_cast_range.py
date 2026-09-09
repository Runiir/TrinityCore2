"""Execute the production observation and ordinary formation producers with value stubs."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
MAGMAW = BOTS / "Content/Raids/BlackwingDescent/Encounters/Magmaw"


def function(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def test_configured_filler_and_formation_converge(tmp_path: Path) -> None:
    observer = function((BOTS / "BotWorldPopulationMgrEncounterBlackboard.cpp").read_text(),
                        "std::optional<BotEncounter::ConfiguredCombatRange> ObserveConfiguredCombatRange(")
    support = function((MAGMAW / "BotAdaptiveMagmawStrategySupport.h").read_text(),
                       "    static std::optional<Vector3> OrdinarySupportDestination(")
    restore = function((MAGMAW / "BotAdaptiveMagmawStrategyHazard.h").read_text(),
                       "    static std::optional<BotNativeAction::Candidate>\n    ProposeRangedFormationRestore(")
    safety = function((MAGMAW / "BotAdaptiveMagmawParasitePolicy.h").read_text(),
                      "    static bool FullLaneCorridorSafe(")
    segment = function((MAGMAW / "BotAdaptiveMagmawParasitePolicy.h").read_text(),
                       "    static float DistanceToSegment(")
    anchors = function((MAGMAW / "BotAdaptiveMagmawStrategySupport.h").read_text(),
                       "    static std::optional<MagmawRangedAnchors> ResolveRangedAnchors(")
    fact = function((BOTS / "BotEncounterBlackboard.h").read_text(), "struct ConfiguredCombatRange") + ";"
    mover = (BOTS / "BotWorldPopulationMgrCombatMovement.cpp").read_text()
    preference = mover[mover.index("    float desiredRange = preciseMaximumRangeApproach"):
                       mover.index("    float distance = bot->GetExactDist(reference);")]
    source = tmp_path / "support.cpp"
    source.write_text(r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <vector>
using uint32 = uint32_t; using uint64 = uint64_t;
struct ObjectGuid {
 uint64 value=0; uint64 GetRawValue() const { return value; }
 bool operator==(ObjectGuid const& x) const { return value==x.value; }
 bool operator!=(ObjectGuid const& x) const { return !(*this==x); }
};
namespace BotEncounter {
''' + fact + r'''
struct Vector3 { float X=0,Y=0,Z=0; };
struct ActorSnapshot { ObjectGuid Guid; uint32 Entry=0; Vector3 Position; bool Baiter=false;
 std::optional<ConfiguredCombatRange> PreferredCombatRange; };
struct Blackboard { uint64 ProfileGeneration=1; std::string ProfileContentHash="pinned";
 struct {std::vector<Vector3> NavigationHints;} Route; };
}
using namespace BotEncounter;
struct Creature;
struct Unit {
 ObjectGuid Guid{39}; uint32 Entry=41570; bool Alive=true, InWorld=true, Attackable=true;
 int Map=1, Instance=2;
 bool IsInWorld() const{return InWorld;} bool IsAlive() const{return Alive;}
 int GetMap() const{return Map;} int GetInstanceId() const{return Instance;}
 ObjectGuid GetGUID() const{return Guid;} uint32 GetEntry() const{return Entry;}
 Creature const* ToCreature() const{return nullptr;}
};
struct Creature:Unit {uint32 GetSpawnId()const{return 1;}};
struct Player:Unit {
 bool Known=true; bool HasSpell(uint32)const{return Known;}
 bool IsValidAttackTarget(Unit const* u)const{return u->Attackable;}
};
struct BotActionProfileSpell {uint32 SpellId=403; std::string TargetSelector="enemy";
 bool RequiresRangedRange=false, RequiresMeleeRange=false,RequiresGroundTarget=false,RequiresInterruptibleTarget=false;
 float DamageWeight=1,MinRange=12,MaxRange=35; std::string MechanicTags="lightning_bolt,filler";};
struct BotClassSpecActionProfile {bool MissingProfile=false; uint64 SnapshotGeneration=1;
 std::string SnapshotContentHash="pinned"; float MinRange=0,MaxRange=35;
 std::vector<BotActionProfileSpell> Spells{BotActionProfileSpell{}};};
namespace BotRaidAreaAuthority { bool Suppressed=false;
 bool IsAllOffenseSuppressed(uint64){return Suppressed;}
 bool IsProtectedEncounterTarget(uint64,uint32,uint32,uint64){return false;} }
namespace BotRaidCooldownReservation {
''' + function((BOTS / "BotWorldPopulationMgrRaidCooldownReservation.h").read_text(),
               "inline bool HasTag(") + "\n}\n" + observer + r'''
bool Finite(Vector3 const&p){return std::isfinite(p.X)&&std::isfinite(p.Y)&&std::isfinite(p.Z);}
float GenericPreferred(ConfiguredCombatRange const& range) {
 float minRange=range.MinRange,maxRange=range.MaxRange;
 bool preciseMaximumRangeApproach=false; float maximumRangeSafetyMargin=1;
''' + preference + r'''
 return desiredRange;
}
float Distance2d(Vector3 const& a,Vector3 const& b){return std::hypot(a.X-b.X,a.Y-b.Y);}
struct MagmawRangedAnchors {Vector3 Support,Left,Right;};
namespace BotActionArbitration {enum class Priority{Mechanic};}
namespace BotNativeAction {struct Candidate {Vector3 Destination;};}
struct MagmawParasitePolicy {
 using FormationAnchors=MagmawRangedAnchors;
 static constexpr float StackSeparation=20;
''' + segment + "\n" + safety + r'''
};
struct Geometry {
 static constexpr float RangedStackDistance=30,SupportStackDistance=8,RangedStackLateralOffset=24;
''' + anchors + r'''
};
struct Policy {
 static constexpr uint32 BossEntry=41570;
 static constexpr float RangedStackTolerance=4;
 static inline MagmawRangedAnchors Anchors{{8,0,0},{30,24,0},{30,-24,0}};
 static std::optional<MagmawRangedAnchors> ResolveRangedAnchors(Blackboard const&,ActorSnapshot const&){return Anchors;}
 static bool IsPillarBaiter(Blackboard const&,ObjectGuid id){return id.value==9 || id.value==6;}
 static Vector3 FormationAnchor(Blackboard const&,MagmawRangedAnchors const&a,ObjectGuid id){return id.value==9?a.Left:a.Right;}
 static BotNativeAction::Candidate BuildPointMovement(Blackboard const&,Vector3 p,char const*,BotActionArbitration::Priority,float){return {p};}
''' + support + "\n" + restore + r'''
};
int main(){
 Player player; Unit target; BotClassSpecActionProfile profile;
 auto fact=ObserveConfiguredCombatRange(&player,&target,profile);
 assert(fact && fact->SourceSpellId==403 && fact->MinRange==12 && fact->PreferredRange==16);
 assert(GenericPreferred(*fact)==fact->PreferredRange);
 assert(fact->TargetGuid==target.Guid && fact->TargetEntry==41570);
 profile.Spells[0].MinRange=0; profile.MinRange=14;
 assert(ObserveConfiguredCombatRange(&player,&target,profile)->MinRange==14);
 assert(ObserveConfiguredCombatRange(&player,&target,profile)->PreferredRange==18);
 profile.MinRange=0; profile.Spells[0].MinRange=12;
 profile.Spells.push_back(profile.Spells[0]); assert(ObserveConfiguredCombatRange(&player,&target,profile));
 profile.Spells.back().RequiresRangedRange=true; assert(!ObserveConfiguredCombatRange(&player,&target,profile));
 profile.Spells.back().RequiresRangedRange=false;
 profile.Spells.back().MaxRange=34; assert(!ObserveConfiguredCombatRange(&player,&target,profile));
 profile.Spells.back().MaxRange=35; profile.Spells.back().SpellId=421;
 assert(!ObserveConfiguredCombatRange(&player,&target,profile));
 profile.Spells.back()=profile.Spells.front();
 profile.Spells[0].SpellId=56641; profile.Spells[1].SpellId=56641;
 profile.Spells[0].MechanicTags="steady_shot,focus_builder,apl_inactive";
 profile.Spells[1].MechanicTags="steady_shot,focus_builder,apl_expiring";
 assert(ObserveConfiguredCombatRange(&player,&target,profile)->SourceSpellId==56641);
 profile.Spells[0].SpellId=403; profile.Spells[1].SpellId=403;
 profile.Spells.pop_back(); profile.Spells[0].MechanicTags="not_filler";
 assert(!ObserveConfiguredCombatRange(&player,&target,profile));
 profile.Spells[0].MechanicTags="lightning_bolt,filler";
 player.Known=false; assert(!ObserveConfiguredCombatRange(&player,&target,profile)); player.Known=true;
 target.Instance=3; assert(!ObserveConfiguredCombatRange(&player,&target,profile)); target.Instance=2;
 target.Attackable=false; assert(!ObserveConfiguredCombatRange(&player,&target,profile)); target.Attackable=true;
 BotRaidAreaAuthority::Suppressed=true; assert(!ObserveConfiguredCombatRange(&player,&target,profile)); BotRaidAreaAuthority::Suppressed=false;
 profile.Spells[0].MaxRange=10; assert(!ObserveConfiguredCombatRange(&player,&target,profile)); profile.Spells[0].MaxRange=35;
 Blackboard board; ActorSnapshot boss{{39},41570,{0,0,0}}, bot{{10},0,{8,0,0}};
 bot.PreferredCombatRange=fact;
 // Real 30/24 bait chord cannot admit preferred16 shoulders with separation20.
 // Old formation emits a return to8 after the range mover; new one abstains.
 bot.Position={GenericPreferred(*fact),0,0};
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 bot.Position={18,0,0}; // actual first native outward overshoot also stays free of restore.
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 // Exact run88 points, with tracked route boss/room-side coordinates.
 boss.Position={-302.467f,-31.7101f,210.8483f};
 board.Route.NavigationHints={{-307.531f,-35.4375f,211.815f}};
 Policy::Anchors=*Geometry::ResolveRangedAnchors(board,boss);
 bot.Position={-308.909851f,-36.4524231f,211.580536f};
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 bot.Position={-316.936462f,-42.3605042f,211.84967f};
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 boss.Position={0,0,0}; Policy::Anchors.Support={8,0,0};
 // A wider existing geometry admits a preferred16 shoulder and settles there.
 Policy::Anchors.Left={40,24,0}; Policy::Anchors.Right={40,-24,0};
 bot.Position={8,0,0}; auto move=Policy::ProposeRangedFormationRestore(board,bot,boss,"dps");
 assert(move); bot.Position=move->Destination;
 assert(std::hypot(bot.Position.X,bot.Position.Y)>=15);
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 // Formation tolerance cannot declare a below-preference position settled.
 bot.PreferredCombatRange->MinRange=14;
 bot.Position.X*=0.8f; bot.Position.Y*=0.8f;
 assert(Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 bot.PreferredCombatRange->ProfileGeneration=2;
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 bot.PreferredCombatRange=fact; bot.PreferredCombatRange->TargetGuid={40};
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 // Baiter and tank ownership never consumes the configured support fact.
 for(uint64 id:{6,9}) {
  bot.Guid={id}; auto withFact=Policy::ProposeRangedFormationRestore(board,bot,boss,"dps");
  auto saved=bot.PreferredCombatRange; bot.PreferredCombatRange.reset();
  auto withoutFact=Policy::ProposeRangedFormationRestore(board,bot,boss,"dps");
  assert(withFact && withoutFact);
  assert(withFact->Destination.X==withoutFact->Destination.X && withFact->Destination.Y==withoutFact->Destination.Y);
  bot.PreferredCombatRange=saved;
 }
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"tank"));
 bot.Guid={10}; bot.PreferredCombatRange.reset(); bot.Position={8,0,0};
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"healer"));
 // A legal nominal8 anchor with min5/pref12 settles without repeated same-point restore.
 bot.PreferredCombatRange=fact; bot.PreferredCombatRange->MinRange=5;
 bot.PreferredCombatRange->PreferredRange=12; bot.Position={8,0,0};
 assert(!Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"));
 // No filler fact preserves existing healer/support ordinary formation.
 bot.PreferredCombatRange.reset(); bot.Position={20,0,0};
 assert(Policy::ProposeRangedFormationRestore(board,bot,boss,"healer"));
 // Nonzero vertical distance uses the same full-3D envelope, without changing floor input.
 bot.PreferredCombatRange=fact; boss.Position.Z=5; bot.Position={8,0,0};
 move=Policy::ProposeRangedFormationRestore(board,bot,boss,"dps"); assert(move && move->Destination.Z==0);
 assert(std::abs(std::sqrt(move->Destination.X*move->Destination.X+move->Destination.Y*move->Destination.Y+25)-16)<0.001f);
}
''')
    binary = tmp_path / "support"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_live_observation_wiring_and_real_elemental_action_override() -> None:
    source = (BOTS / "BotWorldPopulationMgrEncounterBlackboard.cpp").read_text()
    assert "ObjectAccessor::GetUnit(*bot, state.TargetGuid)" in source
    assert "BotClassSpecActionProfileStore::Build(bot, player.Role.c_str())" in source
    assert "snapshot->ProfileGeneration = Cohort().PinnedProfileGeneration" in source
    assert "profile.SnapshotGeneration == snapshot->ProfileGeneration" in source
    body = function(source, "std::optional<BotEncounter::ConfiguredCombatRange> ObserveConfiguredCombatRange(")
    assert "41570" not in body and "403" not in body and "elemental" not in body
    seed = (ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql").read_text()
    row = next(line for line in seed.splitlines() if "elemental_shaman" in line and "40, 403," in line)
    assert "lightning_bolt,filler" in row and "12, 35" in row
    canonical = (ROOT / "sql/custom/world/2026_07_18_00_all_spec_rotation_profile_coverage.sql").read_text()
    assert "'elemental_shaman', 'dps', 'mana', 'ranged', 'ranged', 'none', 0, 35" in canonical
