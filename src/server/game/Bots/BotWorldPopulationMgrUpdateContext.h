#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_UPDATE_CONTEXT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_UPDATE_CONTEXT_H

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementIntents.h"

#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace BotEncounter
{
struct AdaptiveMaloriakPlan;
}

// The update context is deliberately limited to the state that already
// crossed the UpdateBot decision boundary.  It is not a second policy model;
// it only keeps preparation, arbitration, and finalization on the same local
// values and preserves the old lambda capture semantics while the code lives
// in bounded translation units.
struct BotWorldPopulationMgr::BotUpdateContext
{
    BotWorldPopulationMgr& Manager;
    WorldBotState& State;
    Player* Bot = nullptr;
    uint32 Diff = 0;

    BotRolePowerBreakdown Power;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    std::vector<BotActivityScore> ActivityScores;
    BotActivityScore ChosenActivity;
    bool ProgressionScored = false;

    Unit* Target = nullptr;
    float HpPct = 1.0f;
    std::string Situation = "travel";
    std::string Action = "wander";

    QuestActionResult QuestAction;
    BossMechanicActionResult BossAction;
    DungeonTrashActionResult TrashAction;
    QuestObjectivePlan ActivePlanForPriority;
    bool HasActiveQuestObjective = false;
    bool HasNearbyQuestGiver = false;
    bool CanInterleaveHubProfession = false;
    bool ValidationKernelOwnsTick = false;
    uint64 DecisionNowMs = 0;
    // Adaptive Maloriak proposal (Encounters/Maloriak), read by
    // SubmitMaloriakKernelCandidates; its spot-heal target feeds the shared
    // healer candidate.
    std::shared_ptr<BotEncounter::AdaptiveMaloriakPlan const> AdaptiveMaloriak;
    ObjectGuid AdaptiveMaloriakPriorityHealTargetGuid;

    bool AdaptiveDrudgeOwnsNode = false;
    // Exact typed Drudge lanes retain combat authority in the route adapter
    // until its scoped native evidence edge is complete. Generic profiles
    // outside that exact validation route remain unaffected.
    bool DrudgeCombatAuthorityAllowed = true;
    bool AdaptiveAtramedesOwnsNode = false;
    bool AdaptiveAtramedesSuppressOffense = false;
    std::string AdaptiveAtramedesSuppressReason;
    bool AdaptiveChimaeronOwnsNode = false;
    bool AdaptiveChimaeronHealingDisabled = false;
    bool AdaptiveChimaeronSuppressOffense = false;
    std::string AdaptiveChimaeronSuppressReason;
    bool AdaptiveMagmawOwnsNode = false;
    bool AdaptiveMagmawSuppressOffense = false;
    std::string AdaptiveMagmawSuppressReason = "prepull_offense_suppressed";
    bool AdaptiveMaloriakOwnsNode = false;
    bool AdaptiveNefarianOwnsNode = false;
    bool AdaptiveNefarianSuppressOffense = false;
    std::string AdaptiveNefarianSuppressReason;
    // Typed capability blocker (pillar_ascent_unsupported) and movement hold
    // (nefarian_elevator_unobserved, ...) of this decision, for the trace.
    std::string AdaptiveNefarianBlocked;
    std::string AdaptiveNefarianMovementHold;
    bool AdaptiveOmnotronOwnsNode = false;
    bool AdaptiveOmnotronSuppressOffense = false;
    bool AdaptiveNativeRouteOwnsNode = false;
    ObjectGuid AdaptiveDrudgeTankTargetGuid;
    ObjectGuid AdaptiveChimaeronPriorityHealTargetGuid;
    ObjectGuid AdaptiveMagmawPriorityHealTargetGuid;
    ObjectGuid AdaptiveNefarianInterruptTargetGuid;
    ObjectGuid AdaptiveOmnotronInterruptTargetGuid;
    ObjectGuid AdaptiveOmnotronTankTargetGuid;
    ObjectGuid AdaptiveOmnotronDispelTargetGuid;
    std::string AdaptiveOmnotronSuppressReason = "shield_damage_suppressed";
    std::vector<ObjectGuid> AdaptiveOmnotronOffenseAllowedGuids;
    uint64 AdaptiveOmnotronInterruptOrdinal = 0;
    std::optional<BotNativeAction::Candidate> AdaptiveDrudgeMovement;
    std::optional<BotNativeAction::Candidate> AdaptiveAtramedesMovement;
    std::optional<BotNativeAction::Candidate> AdaptiveAtramedesInteraction;
    std::optional<BotNativeAction::Candidate> AdaptiveChimaeronMovement;
    std::optional<BotNativeAction::Candidate> AdaptiveChimaeronAction;
    BotEncounter::MagmawMovementIntentCollection AdaptiveMagmawMovements;
    std::optional<BotEncounter::MagmawTransferLaneExecutionBinding>
        AdaptiveMagmawTransferLaneBinding;
    std::optional<BotNativeAction::Candidate> AdaptiveMagmawDirectionalMobility;
    std::optional<BotNativeAction::Candidate> AdaptiveMagmawInteraction;
    std::optional<BotNativeAction::Candidate> AdaptiveNefarianMovement;
    std::vector<BotNativeAction::Candidate> AdaptiveNefarianActions;
    std::optional<BotNativeAction::Candidate> AdaptiveOmnotronMovement;

    BotUpdateContext(BotWorldPopulationMgr& manager,
        WorldBotState& state, Player* bot, uint32 diff)
        : Manager(manager), State(state), Bot(bot), Diff(diff)
    {
    }

    void EnsureProgressionScored();
};

#endif
