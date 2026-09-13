"""DPS056: compile target-purpose ownership and actual preview/execution exclusion boundaries.

The fixture supplies already legal ranked actions; it does not simulate spell
outcomes or bypass native legality in production. Both production exclusion blocks
and the actual transient-backoff consumer execute, with the real kernel call sites.
"""
from pathlib import Path
import subprocess
from test_magmaw_support_target_admission import compile_probe

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"


def section(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def test_actual_optional_purpose_preview_execute_and_dual_exclusions(tmp_path):
    fallback = (BOTS / "BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text()
    resolver = (BOTS / "BotWorldPopulationMgrCombatResolver.cpp").read_text()
    execution = (BOTS / "BotWorldPopulationMgrCombatExecution.cpp").read_text()
    header = (BOTS / "BotWorldPopulationMgr.h").read_text()
    purpose = section(fallback, "            uint32 const policyExcludedSpellId =", "            bool const hazardRetained")
    preview = section(fallback, "                ResolvedCombatAction const preview =", "                bool const outsideLegalMaxRange")
    call = section(fallback, "            BotActionResult const result = ExecuteProfileCombatAction(\n                &context.State", "            uint32 const spellId")
    gates = section(resolver, "        if (excludedSpellId && candidate.SpellId", "        if (exactSingleTargetCalibration && candidate.SpellId == 42650")
    suppression = section(execution[execution.index("BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState*"):], "    uint64 const nowMs = NowMs();", "    action.MeleeAutoAttackExternallyReconciled")
    prototypes = "\n".join(line.strip().replace(" const;", ";") for line in header.splitlines()
        if "ResolvedCombatAction ResolveProfileCombatAction(" in line
        or "BotActionResult ExecuteProfileCombatAction(WorldBotState*" in line)
    resolve_signature = section(resolver, "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction(", "\n{").replace("BotWorldPopulationMgr::", "").removesuffix(" const")
    execute_signature = section(execution, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState*", "\n{").replace("BotWorldPopulationMgr::", "")
    program = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawLaneTransition.h"
#include <cassert>
#include <vector>
using BotEncounter::MagmawParasiteCombatContract;
struct Unit { ObjectGuid guid; ObjectGuid GetGUID() const {return guid;} };
struct Player:Unit {};
struct WorldBotState {uint32 ProfileCastSuppressedSpellId=0;ObjectGuid ProfileCastSuppressedTargetGuid;uint64 ProfileCastSuppressedUntilMs=0;};
struct ResolvedCombatAction {uint32 SpellId=0;ObjectGuid TargetGuid;};
using BotActionResult=ResolvedCombatAction;
uint64 NowMs(){return 100;}
bool HasMovementCompatibleLease(WorldBotState*,Player*,uint64){return false;}
struct Candidate {uint32 SpellId;std::string RejectReason;};
std::vector<Candidate> observed;
''' + prototypes + '\n' + resolve_signature + r'''
{
 observed={{603,""},{172,""},{980,""}};
 for(auto& candidate:observed) {
''' + gates + r'''
 }
 for(auto const& candidate:observed) if(candidate.RejectReason.empty()) return {candidate.SpellId,target->GetGUID()};
 return {};
}
''' + execute_signature + '\n{\n' + suppression + r'''
 if(actionOut)*actionOut=action;
 return action;
}
struct Pair {ResolvedCombatAction preview,actual;};
Pair Run(MagmawParasiteCombatContract const& magmawContract, Player* bot,Unit* target,WorldBotState& state) {
 struct Context {WorldBotState& State;Player* Bot;Unit* Target;} context{state,bot,target};
 auto magmawProfile=magmawContract.ResolveProfileParameters(bot->GetGUID(),target->GetGUID(),41806,false,false,false);
''' + purpose + preview + '\nResolvedCombatAction profileAction;\n' + call + r'''
 assert(result.SpellId==profileAction.SpellId);
 return {preview,result};
}
int main(){
 Player actor;actor.guid=ObjectGuid(HighGuid::Player,30008u);
 Unit body,head,support,threat;
 body.guid=ObjectGuid(HighGuid::Unit,41570u,39u);head.guid=ObjectGuid(HighGuid::Unit,42347u,76u);
 support.guid=ObjectGuid(HighGuid::Unit,41806u,192u);threat.guid=ObjectGuid(HighGuid::Unit,41806u,193u);
 MagmawParasiteCombatContract contract;contract.Active=true;contract.ActorGuid=actor.guid;contract.SupportTargetGuid=support.guid;
 WorldBotState state;
 auto optional=Run(contract,&actor,&support,state);
 assert(optional.preview.SpellId==172 && optional.actual.SpellId==172);
 assert(optional.actual.TargetGuid==support.guid);
 assert(observed[0].RejectReason=="target_purpose_excluded" && observed[2].RejectReason.empty());
 state.ProfileCastSuppressedSpellId=172;state.ProfileCastSuppressedTargetGuid=support.guid;state.ProfileCastSuppressedUntilMs=200;
 auto dual=Run(contract,&actor,&support,state);
 assert(dual.preview.SpellId==172 && dual.actual.SpellId==980);
 assert(observed[0].RejectReason=="target_purpose_excluded" && observed[1].RejectReason=="temporarily_suppressed");
 assert(dual.actual.TargetGuid==support.guid);
 state.ProfileCastSuppressedUntilMs=99;
 assert(Run(contract,&actor,&support,state).actual.SpellId==172);
 assert(!state.ProfileCastSuppressedSpellId);
 contract.PersonalThreatGuid=support.guid;
 assert(!contract.IsOptionalSupportTarget(actor.guid,support.guid));
 auto overlap=Run(contract,&actor,&support,state);assert(overlap.preview.SpellId==603 && overlap.actual.SpellId==603);
 contract.PersonalThreatGuid=threat.guid;
 assert(Run(contract,&actor,&threat,state).actual.SpellId==603);
 contract.MarksmanshipHunterGuid=actor.guid;
 assert(Run(contract,&actor,&support,state).actual.SpellId==603);
 contract.MarksmanshipHunterGuid.Clear();contract.FireMageGuid=actor.guid;
 assert(Run(contract,&actor,&support,state).actual.SpellId==603);
 contract.FireMageGuid.Clear();
 for(Unit* target:{&body,&head,&body}) {
  auto mandatory=Run(contract,&actor,target,state);
  assert(mandatory.preview.SpellId==603 && mandatory.actual.SpellId==603);
 }
 contract.Active=false;assert(Run(contract,&actor,&support,state).actual.SpellId==603);
 contract.Active=true;contract.ActorGuid=ObjectGuid(HighGuid::Player,30001u);
 assert(!contract.IsOptionalSupportTarget(actor.guid,support.guid));
}
'''
    # Warnings for unrelated resolver parameters are expected in this bounded
    # extracted boundary; production signatures are retained to catch wiring drift.
    program = '#pragma GCC diagnostic ignored "-Wunused-parameter"\n' + program
    binary = compile_probe(tmp_path, program)
    subprocess.run([str(binary)], check=True)
    old = program.replace('        if (policyExcludedSpellId && candidate.SpellId == policyExcludedSpellId)',
                          '        if (false && policyExcludedSpellId && candidate.SpellId == policyExcludedSpellId)')
    assert old != program
    binary = compile_probe(tmp_path, old)
    assert subprocess.run([str(binary)], capture_output=True).returncode != 0
