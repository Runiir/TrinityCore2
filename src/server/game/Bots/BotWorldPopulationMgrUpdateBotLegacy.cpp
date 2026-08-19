#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/BotActionExecutor.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "Creature.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"

#include <string>

using BotWorldPopulationMgrSpellSemantics::NowMs;

bool BotWorldPopulationMgr::RunLegacyBotDecision(
    BotUpdateContext& context)
{
    if (context.HpPct < 0.35f && !context.Bot->IsInCombat())
    {
        context.Bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        context.Bot->GetMotionMaster()->MoveIdle();
        // Remaining idle lets the core's ordinary regeneration proceed.  A
        // future food/drink candidate may accelerate this using normal item
        // spells, but autonomous runtime never writes health or context.Power.
        context.State.RestTimer = 0;
        context.Situation = "idle";
        context.Action = "native_regeneration";
        context.State.LastDecisionHandler = "rest";
    }
    else if (TryValidationRouteObjective(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action, context.Target))
    {
        context.State.LastDecisionHandler = "validation_route";
    }
    else if (context.CanInterleaveHubProfession && TryProfessionMemoryAction(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action))
    {
        context.Target = nullptr;
        context.State.LastDecisionHandler = "profession_memory";
    }
    else if (Cohort().Config.AllowQuesting
        && !(context.Target && !context.Target->IsAlive())
        && (context.ChosenActivity.Activity == BotProgressionActivity::Questing || context.HasActiveQuestObjective || Cohort().Config.QuestFirst || context.State.NewlyAcceptedQuestId || context.HasNearbyQuestGiver)
        && [&]() { context.QuestAction = TryQuesting(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity); return context.QuestAction.Handled; }())
    {
        context.Situation = context.QuestAction.Situation;
        context.Action = context.QuestAction.Action;
        context.Target = context.QuestAction.Target;
        context.State.LastDecisionHandler = "questing";
        context.State.LastDecisionQuestId = context.QuestAction.QuestId;
    }
    else if (!context.Bot->IsInCombat() && TrySmartGearDecision(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action))
    {
        context.Target = nullptr;
        context.State.LastDecisionHandler = "smart_loot";
    }
    else if (!context.Bot->IsInCombat() && TryProfessionMemoryAction(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity, context.Situation, context.Action))
    {
        context.Target = nullptr;
        context.State.LastDecisionHandler = "profession_memory";
    }
    else if (!context.Bot->IsInCombat() && context.ChosenActivity.Activity == BotProgressionActivity::VendorRepairTrain)
    {
        context.Bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        context.Bot->GetMotionMaster()->MoveIdle();
        context.Situation = "vendor_repair_train";
        context.Action = "vendor_repair_train";
        context.State.LastDecisionHandler = "vendor_repair_train";
    }
    else if (IsBossContext(context.Bot, context.Target)
        && [&]() { context.BossAction = TryBossMechanics(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity); return context.BossAction.Handled; }())
    {
        context.Situation = context.BossAction.Situation;
        context.Action = context.BossAction.Action;
        context.Target = context.BossAction.Target;
        context.State.LastDecisionHandler = "boss_mechanics";
    }
    else if (IsDungeonTrashContext(context.Bot, context.Target)
        && [&]() { context.TrashAction = TryDungeonTrash(context.State, context.Bot, context.Power, context.Stage, context.ChosenActivity.Activity); return context.TrashAction.Handled; }())
    {
        context.Situation = context.TrashAction.Situation;
        context.Action = context.TrashAction.Action;
        context.Target = context.TrashAction.Target;
        context.State.LastDecisionHandler = "dungeon_trash";
    }
    else if (context.Target && context.Target->IsAlive())
    {
        char const* rejectReason = nullptr;
        if (!context.Bot->IsInCombat() && !IsQuestRelevantTarget(context.Bot, context.Target) && !IsProgressionCombatTarget(context.Bot, context.Target, &rejectReason))
        {
            context.State.LastRejectedTargetReason = rejectReason ? rejectReason : "not_progression_relevant";
            std::string raw = BuildRawJson(context.Bot, context.Target);
            std::string semantic = BuildSemanticJson(context.Bot, context.Target, "target_rejected", &context.Power, context.Stage, context.ChosenActivity.Activity);
            RecordEvent(context.State, context.Bot, "target_rejected", context.Target, context.State.LastRejectedTargetReason.c_str(), raw.c_str(), semantic.c_str());
            SubmitMeleeAutoAttackIntent(context.State,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Safety,
                BotActionArbitration::Priority::Terminal,
                "target_rejected");
            context.State.TargetGuid.Clear();
            context.Target = nullptr;
            context.Situation = "target_rejected";
            context.Action = "clear_non_progression_target";
            context.State.LastDecisionHandler = "target_filter";
        }
        else
        {
        context.State.TargetGuid = context.Target->GetGUID();
        ResolvedCombatAction profileAction;
        BotActionResult result = ExecuteProfileCombatAction(&context.State, context.Bot, context.Target, &profileAction);
        uint32 spellId = profileAction.SpellId;
        context.Situation = "open_world_combat";
        context.Action = spellId ? "cast_combat_spell" : "attack";
        if (result == BotActionResult::Ok && spellId)
        {
            std::string raw = BuildRawJson(context.Bot, context.Target);
            std::string semantic = BuildSemanticJson(context.Bot, context.Target, context.Situation.c_str(), &context.Power, context.Stage, context.ChosenActivity.Activity);
            RecordEvent(context.State, context.Bot, "spell_cast", context.Target, "ok", raw.c_str(), semantic.c_str(), 0.0f, 0, spellId);
        }
        if (!context.State.WasInCombat)
        {
            std::string raw = BuildRawJson(context.Bot, context.Target);
            std::string semantic = BuildSemanticJson(context.Bot, context.Target, context.Situation.c_str(), &context.Power, context.Stage, context.ChosenActivity.Activity);
            RecordEvent(context.State, context.Bot, "combat_started", context.Target, "ok", raw.c_str(), semantic.c_str());
        }
        context.State.WasInCombat = true;
        context.State.LastDecisionHandler = "combat";
        }
    }
    else if (context.Target && !context.Target->IsAlive())
    {
        BotActionExecutor executor;
        if (Creature const* creature = context.Target->ToCreature())
            context.Situation = (creature->IsDungeonBoss() || creature->isWorldBoss()) ? (context.Bot->GetMap() && context.Bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss") : "open_world_combat";
        else
            context.Situation = "open_world_combat";

        if (!context.Bot->IsWithinDistInMap(context.Target, INTERACTION_DISTANCE))
        {
            MoveBotToPoint(context.State, context.Bot, context.Target->GetPositionX(), context.Target->GetPositionY(), context.Target->GetPositionZ());
            context.Action = "move_to_loot";
            context.State.LastDecisionHandler = "loot";
            SetQuestWorkPhase(context.State, "move_to_loot");
        }
        else if (context.State.NextLootAttemptMs > NowMs())
        {
            context.Action = "loot_cooldown";
            context.State.LastDecisionHandler = "loot";
        }
        else
        {
            context.Action = "loot_target";
            context.State.LastDecisionHandler = "loot";
            SetQuestWorkPhase(context.State, "loot_target");
            if (context.State.LastKilledTargetGuid != context.Target->GetGUID())
            {
                ++Cohort().Metrics.Kills;
                context.State.LastKilledTargetGuid = context.Target->GetGUID();
            }

            ++context.State.LootAttemptCount;
            context.State.LootStartedMs = NowMs();
            uint32 progressBefore = context.State.LastQuestProgressBefore ? context.State.LastQuestProgressBefore : context.State.QuestWork.ProgressBefore;
            BotActionExecutor::LootResult loot = executor.AutoLoot(context.Bot, context.Target);
            context.State.LootCompletedMs = NowMs();
            context.State.LastLootTargetGuid = context.Target->GetGUID();
            context.State.LastLootResult = loot.Reason.empty() ? ToString(loot.Result) : loot.Reason;
            context.State.LastLootItemsCount = loot.ItemsCount;
            context.State.LastLootMoney = loot.Money;
            context.State.LastLootStateCleared = loot.LootStateCleared;
            context.State.NextLootAttemptMs = NowMs() + (loot.Result == BotActionResult::OutOfRange ? 0 : 2500);

            QuestObjectivePlan lootPlan;
            bool hadLootPlan = FindActiveQuestObjective(context.Bot, lootPlan);
            if (!hadLootPlan && context.State.QuestWork.ActiveQuestId)
                hadLootPlan = GetQuestObjectivePlan(context.Bot, context.State.QuestWork.ActiveQuestId, context.State.QuestWork.ObjectiveIndex,
                    context.State.QuestWork.ObjectiveType == "collect_item" ? QuestObjectiveType::CollectItem :
                    (context.State.QuestWork.ObjectiveType == "use_item_on_target" ? QuestObjectiveType::UseItemOnTarget :
                    (context.State.QuestWork.ObjectiveType == "use_ability_on_dummy" ? QuestObjectiveType::UseAbilityOnDummy :
                    (context.State.QuestWork.ObjectiveType == "cast_spell_on_target" ? QuestObjectiveType::CastSpellOnTarget :
                    (context.State.QuestWork.ObjectiveType == "interact_gameobject" ? QuestObjectiveType::InteractGameObject : QuestObjectiveType::Kill)))), lootPlan);
            if (!hadLootPlan && context.State.QuestWork.ActiveQuestId)
            {
                lootPlan.QuestId = context.State.QuestWork.ActiveQuestId;
                lootPlan.ObjectiveIndex = context.State.QuestWork.ObjectiveIndex;
                lootPlan.RequiredEntry = context.State.QuestWork.RequiredEntry;
                lootPlan.ItemId = context.State.QuestWork.RequiredItem;
                lootPlan.RequiredSpellId = context.State.QuestWork.RequiredSpell;
                lootPlan.RequiredCount = context.State.QuestWork.RequiredCount;
                lootPlan.CurrentCount = context.State.QuestWork.CurrentCount;
                lootPlan.IsItemObjective = context.State.QuestWork.ObjectiveType == "collect_item" || context.State.QuestWork.ObjectiveType == "use_item_on_target";
                lootPlan.IsGameObject = context.State.QuestWork.ObjectiveType == "interact_gameobject";
                lootPlan.ObjectiveType = context.State.QuestWork.ObjectiveType == "collect_item" ? QuestObjectiveType::CollectItem :
                    (context.State.QuestWork.ObjectiveType == "use_item_on_target" ? QuestObjectiveType::UseItemOnTarget :
                    (context.State.QuestWork.ObjectiveType == "use_ability_on_dummy" ? QuestObjectiveType::UseAbilityOnDummy :
                    (context.State.QuestWork.ObjectiveType == "cast_spell_on_target" ? QuestObjectiveType::CastSpellOnTarget :
                    (context.State.QuestWork.ObjectiveType == "interact_gameobject" ? QuestObjectiveType::InteractGameObject : QuestObjectiveType::Kill))));
                hadLootPlan = true;
            }
            if (!progressBefore && hadLootPlan)
                progressBefore = QuestObjectiveProgress(context.Bot, lootPlan);

            std::string raw = BuildRawJson(context.Bot, context.Target);
            std::string semantic = BuildSemanticJson(context.Bot, context.Target, context.Situation.c_str(), &context.Power, context.Stage, context.ChosenActivity.Activity);
            RecordEvent(context.State, context.Bot, (context.Situation == "dungeon_boss" || context.Situation == "raid_boss") ? "boss_killed" : "mob_killed", context.Target, "ok", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Metrics.Kills);
            if (context.Situation == "raid_boss")
            {
                ++context.State.RaidBossKills;
                ++Cohort().Metrics.RaidBossKills;
                if (context.Stage == BotProgressionStage::HeroicRaid)
                {
                    ++context.State.HeroicRaidBossKills;
                    ++Cohort().Metrics.HeroicRaidBossKills;
                }

                BossMechanicFeatures features = BuildBossMechanicFeatures(context.Bot, context.Target);
                RaidRoleAssignment assignment = BuildRaidRoleAssignment(context.Bot);
                RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(context.Bot, context.Target, assignment, features);
                RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(context.Bot, context.Target, assignment, features);
                RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(context.Bot, context.Power, context.Stage);
                HeroicRaidProgression progression = BuildHeroicRaidProgression(context.State, context.Bot, context.Power, context.Stage);
                RecordRaidTelemetry(context.State, context.Bot, context.Target, "raid_boss_killed", "ok", features, assignment, anchors, adapter, gearPlan, progression, raw.c_str(), semantic.c_str(), context.Power.Total, Cohort().Metrics.RaidBossKills);
            }

            if (loot.Result == BotActionResult::Ok && (loot.ItemsCount || loot.Money))
                RecordEvent(context.State, context.Bot, "loot_received", context.Target, loot.Reason.c_str(), raw.c_str(), semantic.c_str(), float(loot.Money), loot.ItemsCount);
            else if (loot.Result == BotActionResult::NoAction)
                RecordEvent(context.State, context.Bot, "loot_empty", context.Target, loot.Reason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, 0);
            else
            {
                RecordEvent(context.State, context.Bot, "loot_failed", context.Target, loot.Reason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, uint32(loot.Result));
                if (context.State.LootAttemptCount < 3)
                    return false;
            }

            if (hadLootPlan)
                VerifyQuestObjectiveProgress(context.State, context.Bot, lootPlan, context.Target, progressBefore, "kill_or_loot_verified", raw.c_str(), semantic.c_str());

            BotGearUpgradeEvaluation gear = BotLongTermProgressionBrain::EvaluateGearUpgrade(context.Bot);
            RecordGearEvaluation(context.State, context.Bot, gear, raw.c_str(), semantic.c_str());
            if (loot.Result == BotActionResult::Ok || loot.Result == BotActionResult::NoAction || context.State.LootAttemptCount >= 3)
            {
                context.State.TargetGuid.Clear();
                context.State.WasInCombat = false;
                context.State.LootAttemptCount = 0;
                SetQuestWorkPhase(context.State, "verify_progress");
            }
        }
    }
    else if (IsGenericGrindingAllowed(context.State, context.Bot, context.ChosenActivity.Activity, context.HasActiveQuestObjective) && (context.Target = SelectSafeTarget(context.State, context.Bot)))
    {
        context.State.TargetGuid = context.Target->GetGUID();
        ResolvedCombatAction profileAction;
        BotActionResult result = ExecuteProfileCombatAction(&context.State, context.Bot, context.Target, &profileAction);
        uint32 spellId = profileAction.SpellId;
        context.Situation = "open_world_combat";
        context.Action = spellId ? "profile_combat_action" : "attack";
        std::string raw = BuildRawJson(context.Bot, context.Target);
        std::string semantic = BuildSemanticJson(context.Bot, context.Target, context.Situation.c_str(), &context.Power, context.Stage, context.ChosenActivity.Activity);
        RecordEvent(context.State, context.Bot, "combat_started", context.Target, ToString(result), raw.c_str(), semantic.c_str());
        if (result == BotActionResult::Ok && spellId)
            RecordEvent(context.State, context.Bot, "spell_cast", context.Target, "ok", raw.c_str(), semantic.c_str(), 0.0f, 0, spellId);
        context.State.WasInCombat = true;
        context.State.LastDecisionHandler = "grinding";
    }
    else
    {
        MoveToWanderPoint(context.Bot, context.State);
        context.State.WasInCombat = false;
        context.State.LastDecisionHandler = "wander";
    }

    return true;
}
