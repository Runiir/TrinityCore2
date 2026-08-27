#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeEntranceMovement.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Creature.h"
#include "Player.h"

#include <string>

namespace BotWorldPopulationMgrValidationRoute
{
DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunEntranceMovement(
    MemberAnchor const* anchor, char const* moveResult,
    char const* waitResult, bool packLinked, bool arrived)
{
    using namespace BotRaidDrudgeEntranceMovement;

    float const distance = Bot->GetExactDist(anchor->X, anchor->Y, anchor->Z);
    bool moved = false;
    bool nativeAttempted = false;
    std::string rejection;
    bool const shouldSubmit = ShouldSubmitNativeMovement(
        arrived, false, distance);
    if (shouldSubmit && StrictNativePath(anchor->X, anchor->Y, anchor->Z,
            true, false, &rejection))
    {
        nativeAttempted = true;
        moved = Manager.MoveBotToPointWithReferenceFloor(State, Bot,
            anchor->X, anchor->Y, anchor->Z, anchor->Z, false,
            BotMovementArbitration::Owner::Mechanic,
            BotMovementArbitration::Priority::Mechanic);
    }

    bool const higherPriority = nativeAttempted && !moved
        && State.LastRecoveryResult == Name(Outcome::HigherPriorityPending);
    bool const retained = moved
        && State.LastRecoveryResult == "native_movement_retained";
    Outcome const outcome = Classify({
        arrived,
        retained,
        moved && !retained,
        higherPriority,
        shouldSubmit,
        !arrived && !shouldSubmit,
    });
    if (outcome == Outcome::Rejected)
    {
        State.LastPathRejectReason = rejection.empty()
            ? "drudge_entrance_native_path_rejected" : rejection;
        State.LastRecoveryResult = State.LastPathRejectReason;
    }
    else if (outcome == Outcome::NoProgress)
    {
        State.LastNoProgressReason = "drudge_entrance_native_path_no_progress";
        State.LastRecoveryResult = State.LastNoProgressReason;
    }

    bool const continueCombat = ContinuePackCombat(outcome, packLinked);
    if (!continueCombat)
        HoldOffense();

    Record(Sources[0], TraceResult(outcome, moveResult, waitResult), distance);
    Target = Sources[0];
    State.TargetGuid = Sources[0]->GetGUID();
    return continueCombat ? PhaseResult::Continue : PhaseResult::Handled;
}
}
