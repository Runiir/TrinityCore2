#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotMeleeAutoAttackIntent.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Creature.h"
#include "Map.h"
#include "MotionMaster.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "Unit.h"

#include <algorithm>
#include <limits>

namespace BotWorldPopulationMgrValidationRoute
{
DrudgeLaneContext::PhaseResult DrudgeLaneContext::EnforceFutureBossBoundary()
{
    bool const exactDrudgeAlive = std::any_of(Sources.begin(), Sources.end(),
        [](Creature const* source)
        {
            return source && source->IsAlive();
        });
    auto const& route = Manager.Party().ValidationRouteManifest;
    size_t const nextIndex = Manager.Party().ValidationRouteManifestIndex + 1;
    if (!exactDrudgeAlive || nextIndex >= route.size())
        return PhaseResult::Continue;

    auto const& future = route[nextIndex];
    if (future.Kind != "boss" || future.MapId != Bot->GetMapId()
        || !future.TargetEntry || !future.TargetSpawnId)
        return PhaseResult::Continue;

    Creature* futureBoss = Bot->GetMap()->GetCreatureBySpawnId(
        future.TargetSpawnId);
    if (!futureBoss || futureBoss->GetEntry() != future.TargetEntry
        || futureBoss->GetMap() != Bot->GetMap())
        return PhaseResult::Continue;

    auto isFutureBoss = [futureBoss](Unit const* unit)
    {
        return unit && unit->GetGUID() == futureBoss->GetGUID();
    };

    bool cleared = false;
    for (CurrentSpellTypes spellType : {
            CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
        if (Spell* current = Bot->GetCurrentSpell(spellType))
            if (isFutureBoss(current->m_targets.GetUnitTarget()))
            {
                Bot->InterruptSpell(spellType, false);
                cleared = true;
            }

    if (isFutureBoss(Bot->GetVictim()))
    {
        Bot->AttackStop();
        Manager.SubmitMeleeAutoAttackIntent(State,
            BotMeleeAutoAttack::Kind::Stop, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "drudge_future_boss_target_cleared");
        cleared = true;
    }
    if (isFutureBoss(Target))
    {
        Target = nullptr;
        cleared = true;
    }
    if (State.TargetGuid == futureBoss->GetGUID())
    {
        State.TargetGuid.Clear();
        cleared = true;
    }

    for (Unit* controlled : Bot->m_Controlled)
        if (controlled && isFutureBoss(controlled->GetVictim()))
        {
            controlled->AttackStop();
            cleared = true;
        }

    float futureClearance = std::numeric_limits<float>::max();
    for (MemberAnchor const& anchor :
        Manager.Cohort().Config.ValidationRouteSplitTankCombatAnchors)
        futureClearance = std::min(futureClearance,
            BotWorldPopulationMgrNativeHelpers::Distance2d(
                anchor.X, anchor.Y, future.X, future.Y));
    bool const routeMoveTargetsBoss = State.ActivePathTargetGuid
        == futureBoss->GetGUID();
    bool const routeMoveEntersBossEnvelope = State.ActivePathValid
        && futureClearance < std::numeric_limits<float>::max()
        && BotWorldPopulationMgrNativeHelpers::Distance2d(
            State.ActivePathToX, State.ActivePathToY, future.X, future.Y)
            + 0.01f < futureClearance;
    if (State.MovementLease.MovementOwner
            == BotMovementArbitration::Owner::Route
        && (routeMoveTargetsBoss || routeMoveEntersBossEnvelope))
    {
        Bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        State.MovementLease = {};
        State.ActivePathValid = false;
        State.ActivePathSegmentValid = false;
        State.ActivePathTargetGuid.Clear();
        State.IsMoving = false;
        cleared = true;
    }

    if (cleared)
        Record(futureBoss, "drudge_future_boss_target_cleared");
    return PhaseResult::Continue;
}
}
