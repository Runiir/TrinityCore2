#include "Bots/BotWorldPopulationMgrUpdateContext.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotNativeActionIntent.h"

#include "CharmInfo.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <utility>

void BotWorldPopulationMgr::SubmitAfflictionPetAttackCandidate(
    BotUpdateContext& context)
{
    BotClassSpecActionProfile const profile =
        BotClassSpecActionProfileStore::Build(context.Bot,
            GetDungeonRole(context.Bot));
    if (profile.SpecTag != "affliction_warlock"
        || !context.Target || !context.Target->IsAlive()
        || (!context.Target->IsInCombat() && !context.Target->GetVictim()))
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
