#include "Bots/BotWorldPopulationMgrValidationRouteContamination.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgrBotState.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Creature.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "Unit.h"

#include <algorithm>

using BotWorldPopulationMgrBotState::WorldBotState;
using BotWorldPopulationMgrSpellSemantics::HasNearbyProtectedEncounterTarget;
using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;

namespace BotWorldPopulationMgrValidationRoute
{
namespace
{
bool IsProtectedFutureTarget(Player* bot, Unit* candidate,
    std::function<bool(Creature const*)> const& isImmediateNextEncounterMember)
{
    Creature* creature = candidate ? candidate->ToCreature() : nullptr;
    if (!bot || !creature || !creature->IsAlive())
        return false;

    return isImmediateNextEncounterMember(creature)
        || BotRaidAreaAuthority::IsProtectedEncounterTarget(
            bot->GetGUID().GetRawValue(), creature->GetEntry(),
            creature->GetSpawnId(), creature->GetGUID().GetRawValue());
}

bool ShouldInterruptOffensiveSpell(Player* bot, Unit* caster, Spell* current,
    std::function<bool(Creature const*)> const& isImmediateNextEncounterMember)
{
    if (!current)
        return false;

    Unit* castTarget = current->m_targets.GetUnitTarget();
    return IsProtectedFutureTarget(bot, castTarget,
               isImmediateNextEncounterMember)
        || (SpellHasHostileMultiTargetSemantics(current->GetSpellInfo())
            && HasNearbyProtectedEncounterTarget(bot,
                castTarget ? castTarget : caster));
}

void GuardCurrentOffense(Player* bot, Unit* actor,
    std::function<bool(Creature const*)> const& isImmediateNextEncounterMember)
{
    if (!actor)
        return;

    for (CurrentSpellTypes spellType :
        { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
    {
        if (Spell* current = actor->GetCurrentSpell(spellType))
            if (ShouldInterruptOffensiveSpell(bot, actor, current,
                    isImmediateNextEncounterMember))
                actor->InterruptSpell(spellType, false);
    }

    if (Spell* current = actor->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
    {
        Unit* castTarget = current->m_targets.GetUnitTarget();
        if (IsProtectedFutureTarget(bot, castTarget ? castTarget : actor->GetVictim(),
                isImmediateNextEncounterMember))
            actor->InterruptSpell(CURRENT_AUTOREPEAT_SPELL, false);
    }
}
}

ContaminationResult ObserveAndGuard(WorldBotState& state, Player* bot,
    Unit*& target, ContaminationEvidenceSink const& evidence,
    ContaminationCallbacks const& callbacks)
{
    ContaminationResult result;
    if (!bot || !callbacks.ForEachActiveCombat
        || !callbacks.IsImmediateNextEncounterMember)
        return result;

    callbacks.ForEachActiveCombat([&result, &callbacks](Creature* creature)
    {
        if (!creature || !creature->IsAlive() || !creature->GetHealth()
            || !callbacks.IsImmediateNextEncounterMember(creature))
            return;

        // Combat references are stored in an unordered container. Pick the
        // lowest raw GUID so the receipt and guard target do not depend on
        // iteration order when several future members are already engaged.
        if (!result.FutureTarget
            || creature->GetGUID().GetRawValue()
                < result.FutureTarget->GetGUID().GetRawValue())
            result.FutureTarget = creature;
    });
    if (!result.FutureTarget)
        return result;

    result.Observed = true;
    bool const contaminationRecorded = std::any_of(
        evidence.Records.begin(), evidence.Records.end(),
        [&evidence, &result](
            BotWorldPopulationMgrRouteState::ValidationRouteEvidence const& row)
        {
            return row.Generation == evidence.Generation
                && row.TargetGuid == result.FutureTarget->GetGUID();
        });
    if (!contaminationRecorded)
        evidence.Records.push_back({
            evidence.NodeId,
            evidence.Generation,
            evidence.Kind,
            result.FutureTarget->GetGUID(),
            result.FutureTarget->GetEntry(),
            "validation_route_future_encounter_contamination"});

    auto const& isImmediateNextEncounterMember =
        callbacks.IsImmediateNextEncounterMember;
    auto isProtectedFutureTarget = [&bot,
        &isImmediateNextEncounterMember](Unit* candidate)
    {
        return IsProtectedFutureTarget(bot, candidate,
            isImmediateNextEncounterMember);
    };
    auto guardCurrentOffense = [&bot, &isImmediateNextEncounterMember](
        Unit* actor)
    {
        GuardCurrentOffense(bot, actor, isImmediateNextEncounterMember);
    };

    GuardCurrentOffense(bot, bot, isImmediateNextEncounterMember);
    if (isProtectedFutureTarget(bot->GetVictim())
        && callbacks.SuppressPlayerMelee)
        callbacks.SuppressPlayerMelee(state);

    if (Pet* pet = bot->GetPet())
    {
        guardCurrentOffense(pet);
        if (isProtectedFutureTarget(pet->GetVictim()))
            pet->AttackStop();
    }
    for (Unit* controlled : bot->m_Controlled)
        if (controlled)
        {
            guardCurrentOffense(controlled);
            if (isProtectedFutureTarget(controlled->GetVictim()))
                controlled->AttackStop();
        }

    if (isProtectedFutureTarget(target))
    {
        target = nullptr;
        state.TargetGuid.Clear();
        result.TargetCleared = true;
    }
    return result;
}
}
