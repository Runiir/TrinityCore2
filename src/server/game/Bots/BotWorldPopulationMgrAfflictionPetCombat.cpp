#include "Bots/BotWorldPopulationMgrUpdateContext.h"

#include "Bots/BotCanonicalRaidScope.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotRaidDemonologyHellfireLive.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <utility>

namespace
{
// Ends a canonical Demonology Hellfire channel once fewer than KeepEnemies
// engaged enemies remain in its radius (BotRaidDemonologyHellfire.h), as a
// player cancels a channel. It claims no lane, so the profile rotation picks
// the next spell in the same tick.
void SubmitCanonicalHellfireStopCandidate(Player* bot,
    BotActionArbitration::Kernel& kernel)
{
    if (BotRaidDemonologyHellfire::ChannelSpellId(bot)
        != BotRaidDemonologyHellfire::Hellfire)
        return;
    BotActionArbitration::Candidate stop;
    stop.Key = "raid.class.hellfire_stop";
    stop.Source = "canonical_raid_rotation";
    stop.ActionPriority = BotActionArbitration::Priority::Support;
    stop.UtilityScore = 1.0f;
    stop.Attempt = [bot]()
    {
        if (!BotRaidDemonologyHellfire::ShouldStop(
                BotRaidDemonologyHellfire::ChannelSpellId(bot),
                BotRaidDemonologyHellfire::CountEngagedEnemiesInRadius(bot)))
            return BotActionArbitration::Outcome::NotApplicable(
                "hellfire_radius_occupied");
        bot->InterruptSpell(CURRENT_CHANNELED_SPELL);
        return BotActionArbitration::Outcome::Committed(
            BotRaidDemonologyHellfire::StopReason);
    };
    kernel.Submit(std::move(stop));
}
}

// The warlock pet and channel candidates that run beside the owner's own
// rotation. Affliction: every scope. Demonology: canonical-composition raids
// only (BotCanonicalRaidScope.h), so the Phase 8 calibration and Stonecore
// warlocks keep their decisions.
//
// Demonology round 4 (label blackwing_descent_10n-r03-a3864fcf6d): the
// Felguard is commanded only when the owner executes a spell at a hostile
// (BotActionExecutor.cpp), so a self-cast Hellfire, a wait or a movement tick
// leaves it on its last victim. Maloriak cd3009: 146 Felguard swings in the
// 268 s window, none at all from 70 to 80 s. The candidate below keeps the
// Felguard on the warlock's combat target with the same native pet command.
// Encounter pet holds (Magmaw, Omnotron, Maloriak, Chimaeron) claim the pet
// lane at Mechanic priority and so still win.
void BotWorldPopulationMgr::SubmitAfflictionPetAttackCandidate(
    BotUpdateContext& context)
{
    BotClassSpecActionProfile const profile =
        BotClassSpecActionProfileStore::Build(context.Bot,
            GetDungeonRole(context.Bot));
    bool const canonicalDemonology = profile.SpecTag == "demonology_warlock"
        && context.Bot->GetMap() && context.Bot->GetMap()->IsRaid()
        && BotCanonicalRaidScope::IsCanonicalRaid(Cohort().Raid.RaidInstance,
            Cohort().Config.ValidationRouteScenarioId);
    if (canonicalDemonology)
        SubmitCanonicalHellfireStopCandidate(context.Bot,
            context.State.DecisionKernel);
    if ((profile.SpecTag != "affliction_warlock" && !canonicalDemonology)
        || !context.Target || !context.Target->IsAlive()
        || (!context.Target->IsInCombat() && !context.Target->GetVictim()))
        return;
    if (Creature const* creature = context.Target->ToCreature();
        canonicalDemonology && creature
        && (IsImmediateNextValidationRouteEncounterMember(creature)
            || BotRaidAreaAuthority::IsProtectedEncounterTarget(
                context.Bot->GetGUID().GetRawValue(), creature->GetEntry(),
                creature->GetSpawnId(), creature->GetGUID().GetRawValue())))
        return;

    ObjectGuid const petTargetGuid = context.Target->GetGUID();
    BotActionArbitration::Candidate petAttack;
    petAttack.Key = "world.profile_pet_attack:" + petTargetGuid.ToString();
    petAttack.Source = "db_class_spec_profile";
    petAttack.ActionPriority = BotActionArbitration::Priority::TrainedDamage;
    petAttack.UtilityScore = 0.95f;
    // Pet attack is a persistent native command and does not consume the
    // owner's GCD, cast, or target-selection lane.
    petAttack.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Pet);
    petAttack.Attempt = [this, &context, petTargetGuid]()
    {
        Pet* pet = context.Bot->GetPet();
        Unit* target = ObjectAccessor::GetUnit(*context.Bot, petTargetGuid);
        if (!pet || !pet->IsInWorld() || !pet->IsAlive()
            || pet->GetCharmerOrOwnerPlayerOrPlayerItself() != context.Bot
            || !pet->GetCharmInfo())
            return BotActionArbitration::Outcome::NotApplicable(
                "affliction_pet_unavailable");
        if (!target || !target->IsInWorld() || !target->IsAlive()
            || !context.Bot->IsValidAttackTarget(target)
            || !pet->IsValidAttackTarget(target))
            return BotActionArbitration::Outcome::Retryable(
                "affliction_pet_target_unavailable");
        if (pet->GetVictim() == target
            && pet->GetCharmInfo()->IsCommandAttack())
            return BotActionArbitration::Outcome::NotApplicable(
                "affliction_pet_already_attacking");

        return ExecuteNativeActionIntent(context.State, context.Bot,
            BotNativeAction::PetCommand{ pet->GetGUID(), target->GetGUID(),
                COMMAND_ATTACK });
    };
    context.State.DecisionKernel.Submit(std::move(petAttack));
}
