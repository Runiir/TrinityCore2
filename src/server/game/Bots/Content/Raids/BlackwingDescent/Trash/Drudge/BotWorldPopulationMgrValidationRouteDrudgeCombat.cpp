#include "Bots/BotActionArbiter.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Creature.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

namespace BotWorldPopulationMgrValidationRoute
{
DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunEntranceCombat()
{
    Creature* combatTarget = LaneSource->IsAlive() ? LaneSource : OtherSource;
    if (!combatTarget || !combatTarget->IsAlive())
        return PhaseResult::Abort;

    SourceSeparation = Sources[0]->GetExactDist2d(Sources[1]);
    if (Role == "healer" && Callbacks.TryGroupHeal
        && Callbacks.TryGroupHeal(Bot, combatTarget, false, true))
    {
        Record(combatTarget, "drudge_entrance_combat_heal", SourceSeparation);
        Target = combatTarget;
        State.TargetGuid = combatTarget->GetGUID();
        return PhaseResult::Handled;
    }

    if (Bot->GetVictim() && Bot->GetVictim() != combatTarget)
        Manager.SubmitMeleeAutoAttackIntent(State,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "split_lane_target_switch");
    if (Pet* pet = Bot->GetPet();
        pet && pet->GetVictim() && pet->GetVictim() != combatTarget)
        pet->AttackStop();
    for (Unit* controlled : Bot->m_Controlled)
        if (controlled && controlled->GetVictim()
            && controlled->GetVictim() != combatTarget)
            controlled->AttackStop();
    BotRaidAreaAuthority::SetAllOffenseSuppressed(
        Bot->GetGUID().GetRawValue(), false);
    BotRaidAreaAuthority::Set(Bot->GetGUID().GetRawValue(), true);
    ResolvedCombatAction action = Manager.ResolveProfileCombatAction(
        Bot, combatTarget, 1, false, 0, false, false, true, false, false);
    BotActionResult const result = Manager.ExecuteProfileCombatAction(
        &State, Bot, combatTarget, &action,
        1, false, 0, false, false, true, false, false);
    bool const succeeded = action.Valid && action.Type == "cast"
        && action.SpellId && result == BotActionResult::Ok;
    if (succeeded)
        Manager.Party().ValidationRouteDrudgeProfileActionRosterGuids.insert(
            Bot->GetGUID().GetCounter());
    Record(combatTarget, succeeded ? "drudge_entrance_lane_action"
        : "drudge_entrance_lane_hold", SourceSeparation, action.SpellId);
    Target = combatTarget;
    State.TargetGuid = combatTarget->GetGUID();
    State.WasInCombat = combatTarget->IsInCombat();
    return PhaseResult::Handled;
}
}
