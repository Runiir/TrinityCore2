#include "Bots/BotEncounterInterruptVeto.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <list>
#include <string>

// Kernel candidates for the adaptive Maloriak plan (BotAdaptiveMaloriakStrategy.h).
// Every candidate submits one ordinary native request (move, interrupt,
// dispel, taunt, raid haste, auto-attack suppression) and revalidates the
// observed fact at the native edge, so a stale plan never spends a cooldown
// on an ended cast, a removed buff or an admitted Release Aberrations. The
// route observation credits the native kill to the route, as adaptive
// Magmaw's observer does for Magmaw.
namespace
{
using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

// Pummel, Kick, Counterspell, Wind Shear, Rebuke, Mind Freeze, Skull Bash
// (bear, cat), Silence, Silencing Shot.
constexpr std::array<uint32, 10> MaloriakInterruptSpells = {
    6552u, 1766u, 2139u, 57994u, 96231u, 47528u, 80964u, 80965u, 15487u, 34490u };
// Spellsteal, Purge, Tranquilizing Shot, Dispel Magic (527, the offensive
// priest dispel; 528 is Cure Disease and allies only).
constexpr std::array<uint32, 4> MaloriakRemedyDispelSpells = {
    30449u, 370u, 19801u, 527u };
// Growl, Dark Command, Hand of Reckoning, Taunt.
constexpr std::array<uint32, 4> MaloriakTauntSpells = { 6795u, 56222u, 62124u, 355u };
// Chamber creatures and Vile Swills are released within this range of the
// boss (the laboratory is about 80 x 85 yards).
constexpr float MaloriakAddScanYards = 150.0f;

template <std::size_t N>
uint32 FirstKnownSpell(Player const* bot, std::array<uint32, N> const& spells)
{
    for (uint32 spellId : spells)
        if (bot->HasSpell(spellId))
            return spellId;
    return 0;
}

// Native counterpart of Maloriak::ReleaseAdmitted: loose (selectable) and
// reserve (still asleep) Aberrations, and live Vile Swills in the Dark phase.
bool NativeReleaseAdmitted(Unit* boss)
{
    std::list<Creature*> aberrations;
    boss->GetCreatureListWithEntryInGrid(aberrations,
        BotEncounter::Maloriak::AberrationEntry, MaloriakAddScanYards);
    std::size_t loose = 0;
    std::size_t reserve = 0;
    for (Creature const* aberration : aberrations)
    {
        if (!aberration->IsAlive())
            continue;
        if (aberration->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE))
            ++reserve;
        else
            ++loose;
    }
    bool darkWithSwills = false;
    if (boss->HasAura(BotEncounter::Maloriak::ShadowImbuedSpell))
    {
        std::list<Creature*> swills;
        boss->GetCreatureListWithEntryInGrid(swills,
            BotEncounter::Maloriak::VileSwillEntry, MaloriakAddScanYards);
        for (Creature const* swill : swills)
            darkWithSwills = darkWithSwills || swill->IsAlive();
    }
    return BotEncounter::Maloriak::ReleaseAdmittedCounts(loose, reserve,
        darkWithSwills);
}

bool HasRemedy(Unit const* unit)
{
    for (uint32 spellId : BotEncounter::Maloriak::RemedySpells)
        if (unit->HasAura(spellId))
            return true;
    return false;
}

// TryCastCombatSpell refuses while the bot is casting, and casters chain hard
// casts, so round 4's one Remedy (25000/s, 225000 healed) was never purged. A
// bot assigned an interrupt or purge stops its own cast first, as a player
// would, but only when that spell is off cooldown and the target is in range.
bool ClearOwnCastFor(Player* bot, Unit* target, uint32 spellId)
{
    if (!bot->HasUnitState(UNIT_STATE_CASTING))
        return true;
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo || !bot->GetSpellHistory()->IsReady(spellInfo)
        || !bot->IsWithinDistInMap(target,
            std::max(5.0f, spellInfo->GetMaxRange(false))))
        return false;
    bot->InterruptNonMeleeSpells(false);
    return true;
}
}

void BotWorldPopulationMgr::SubmitMaloriakKernelCandidates(
    BotUpdateContext& context)
{
    if (!context.Bot || !context.AdaptiveMaloriak
        || !context.AdaptiveMaloriak->OwnsNode)
        return;
    BotEncounter::AdaptiveMaloriakPlan const& plan = *context.AdaptiveMaloriak;

    // Publish (or withdraw) the Release Aberrations interrupt veto before the
    // cast starts, so a generic rotation interrupt cannot cut an admitted
    // release. The native recount confirms the blackboard's admission.
    if (!plan.Boss.IsEmpty())
    {
        Unit* boss = plan.ReleaseAdmitted
            ? ObjectAccessor::GetUnit(*context.Bot, plan.Boss) : nullptr;
        BotEncounterInterruptVeto::Set(plan.Boss.GetRawValue(),
            BotEncounter::Maloriak::ReleaseAberrationsSpell,
            boss && boss->IsAlive() && NativeReleaseAdmitted(boss));
    }

    if (plan.Movement && plan.Movement->ExpiresAtMs > context.DecisionNowMs)
    {
        bool const survival = plan.Movement->ActionPriority
            >= BotActionArbitration::Priority::Survival;
        // Round 4: after the runback the raid stood on the lower-wing
        // elevator landing (-219, -235, z 76.8). A mechanic-lane move to the
        // staging line (z 73.6, same nominal level) must keep every path
        // control on the actor's level, but the native path dips to z 66.9,
        // so all 152 staging moves were refused as
        // route_destination_path_control_level_gap and the pull gate never
        // opened. A move that starts outside the laboratory is travel and
        // takes the route lane (progressive native segments).
        bool const travel = !survival && !BotEncounter::Maloriak::InRoom(
            { context.Bot->GetPositionX(), context.Bot->GetPositionY(),
              context.Bot->GetPositionZ() });
        BotActionArbitration::Candidate movement;
        movement.Key = plan.Movement->Id.Key();
        movement.Source = plan.Movement->Id.Strategy;
        movement.ActionPriority = plan.Movement->ActionPriority;
        movement.UtilityScore = plan.Movement->Utility;
        movement.RequiredResources = plan.Movement->Resources();
        movement.ExpiresAtMs = plan.Movement->ExpiresAtMs;
        movement.Attempt = [this, &context, survival, travel,
            intent = BotNativeAction::WithMovementReason(
                plan.Movement->Action, plan.Movement->Id.Mechanic)]()
        {
            // Survival moves (sphere, jet fire, Magma Jets) take the hazard
            // lane; formation, staging and add-spot moves only the mechanic
            // lane, so native combat movement is not leased away.
            BotMovementArbitration::Owner const owner = survival
                ? BotMovementArbitration::Owner::Hazard
                : (travel ? BotMovementArbitration::Owner::Route
                          : BotMovementArbitration::Owner::Mechanic);
            BotMovementArbitration::Priority const priority = survival
                ? BotMovementArbitration::Priority::Hazard
                : (travel ? BotMovementArbitration::Priority::Route
                          : BotMovementArbitration::Priority::Mechanic);
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                context.State, context.Bot, intent, owner, priority);
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
            {
                context.Situation = "adaptive_maloriak";
                context.Action = "maloriak_mechanic_movement";
                context.State.LastDecisionHandler = "adaptive_maloriak";
            }
            return outcome;
        };
        context.State.DecisionKernel.Submit(std::move(movement));
    }

    if (plan.SuppressOffense)
    {
        std::string const reason(plan.SuppressReason);
        BotActionArbitration::Candidate suppress;
        suppress.Key = "adaptive_maloriak:" + reason + ":"
            + std::to_string(Party().ValidationRouteGeneration);
        suppress.Source = "adaptive_maloriak";
        suppress.ActionPriority = BotActionArbitration::Priority::Mechanic;
        suppress.UtilityScore = 100.0f;
        suppress.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Pet);
        if (Cohort().Raid.ValidationPrepullCheckpoint.Enabled())
            context.State.DecisionKernel.SetCandidateAdmission(suppress.Key,
                BotActionArbitration::AdmissionClass::OffenseSuppression,
                Cohort().Raid.ValidationPrepullCheckpoint.CurrentScope().Key());
        suppress.Attempt = [this, &context, reason]()
        {
            std::string const intentReason = "adaptive_maloriak_" + reason;
            bool const submitted = SubmitMeleeAutoAttackIntent(context.State,
                BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                BotMeleeAutoAttack::Owner::Mechanic,
                BotActionArbitration::Priority::Mechanic, intentReason.c_str());
            if (Pet* pet = context.Bot->GetPet(); pet && pet->GetCharmInfo())
                ExecuteNativeActionIntent(context.State, context.Bot,
                    BotNativeAction::PetCommand{ pet->GetGUID(),
                        context.Bot->GetGUID(), COMMAND_FOLLOW },
                    BotMovementArbitration::Owner::Mechanic,
                    BotMovementArbitration::Priority::Mechanic);
            context.State.TargetGuid.Clear();
            context.Target = nullptr;
            context.Situation = "adaptive_maloriak";
            context.Action = reason;
            context.State.LastDecisionHandler = "adaptive_maloriak";
            return submitted
                ? BotActionArbitration::Outcome::Committed(
                    "melee_autoattack_suppression_submitted")
                : BotActionArbitration::Outcome::Retryable(
                    "melee_autoattack_suppression_rejected");
        };
        context.State.DecisionKernel.Submit(std::move(suppress));
    }

    if (!plan.InterruptTarget.IsEmpty() && plan.InterruptSpellId)
    {
        std::string const lane(plan.InterruptLane);
        BotActionArbitration::Candidate interrupt;
        interrupt.Key = "adaptive_maloriak:interrupt:" + lane + ":"
            + std::to_string(plan.InterruptTarget.GetRawValue());
        interrupt.Source = "adaptive_maloriak";
        interrupt.ActionPriority = BotActionArbitration::Priority::Interrupt;
        interrupt.UtilityScore = 95.0f;
        interrupt.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target);
        interrupt.Attempt = [this, &context, lane,
            casterGuid = plan.InterruptTarget, castSpellId = plan.InterruptSpellId]()
        {
            Unit* caster = ObjectAccessor::GetUnit(*context.Bot, casterGuid);
            if (!caster || !caster->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "interrupt_caster_stale");
            // Never spend an interrupt on an ended or uninterruptible cast
            // (the script closes the window with MakeInterruptable).
            Spell* current = caster->FindCurrentSpellBySpellId(castSpellId);
            if (!current)
                return BotActionArbitration::Outcome::NotApplicable(
                    "interrupt_cast_already_ended");
            if (!current->GetSpellInfo()->CanBeInterrupted(caster))
                return BotActionArbitration::Outcome::NotApplicable(
                    "interrupt_cast_not_interruptible");
            if (castSpellId == BotEncounter::Maloriak::ReleaseAberrationsSpell
                && NativeReleaseAdmitted(caster))
                return BotActionArbitration::Outcome::NotApplicable(
                    "release_aberrations_admitted");
            uint32 const interruptSpell = FirstKnownSpell(context.Bot,
                MaloriakInterruptSpells);
            if (!interruptSpell)
                return BotActionArbitration::Outcome::NotApplicable(
                    "interrupt_spell_unknown");
            if (!ClearOwnCastFor(context.Bot, caster, interruptSpell))
                return BotActionArbitration::Outcome::Retryable(
                    "interrupt_not_ready_while_casting");
            if (!TryCastCombatSpell(context.Bot, caster, interruptSpell))
                return BotActionArbitration::Outcome::Retryable(
                    "native_interrupt_retryable");
            context.Situation = "adaptive_maloriak";
            context.Action = lane + "_interrupt";
            context.State.LastDecisionHandler = "adaptive_maloriak";
            return BotActionArbitration::Outcome::Started(
                "native_interrupt_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(interrupt));
    }

    if (!plan.DispelTarget.IsEmpty())
    {
        BotActionArbitration::Candidate dispel;
        dispel.Key = "adaptive_maloriak:remedy:"
            + std::to_string(plan.DispelTarget.GetRawValue());
        dispel.Source = "adaptive_maloriak";
        dispel.ActionPriority = BotActionArbitration::Priority::Interrupt;
        dispel.UtilityScore = 85.0f;
        dispel.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target);
        dispel.Attempt = [this, &context, targetGuid = plan.DispelTarget]()
        {
            Unit* target = ObjectAccessor::GetUnit(*context.Bot, targetGuid);
            if (!target || !target->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "dispel_target_stale");
            if (!HasRemedy(target))
                return BotActionArbitration::Outcome::NotApplicable(
                    "remedy_already_removed");
            uint32 const dispelSpell = FirstKnownSpell(context.Bot,
                MaloriakRemedyDispelSpells);
            if (!dispelSpell)
                return BotActionArbitration::Outcome::NotApplicable(
                    "dispel_spell_unknown");
            if (!ClearOwnCastFor(context.Bot, target, dispelSpell))
                return BotActionArbitration::Outcome::Retryable(
                    "dispel_not_ready_while_casting");
            // Purges share the GCD: hold the cast lanes through it so the
            // rotation cannot start another hard cast before the purge.
            if (SpellInfo const* dispelInfo = sSpellMgr->GetSpellInfo(dispelSpell);
                dispelInfo && context.Bot->GetSpellHistory()->HasGlobalCooldown(dispelInfo))
                return BotActionArbitration::Outcome::Submitted(
                    "native_dispel_wait_global_cooldown");
            if (!TryCastCombatSpell(context.Bot, target, dispelSpell))
                return BotActionArbitration::Outcome::Retryable(
                    "native_dispel_retryable");
            context.Situation = "adaptive_maloriak";
            context.Action = "remedy_native_dispel";
            context.State.LastDecisionHandler = "adaptive_maloriak";
            return BotActionArbitration::Outcome::Started(
                "native_dispel_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(dispel));
    }

    if (!plan.TauntTarget.IsEmpty())
    {
        BotActionArbitration::Candidate taunt;
        taunt.Key = "adaptive_maloriak:taunt:"
            + std::to_string(plan.TauntTarget.GetRawValue());
        taunt.Source = "adaptive_maloriak";
        taunt.ActionPriority = BotActionArbitration::Priority::ThreatControl;
        taunt.UtilityScore = 90.0f;
        taunt.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target);
        taunt.Attempt = [this, &context, targetGuid = plan.TauntTarget]()
        {
            Unit* target = ObjectAccessor::GetUnit(*context.Bot, targetGuid);
            if (!target || !target->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "taunt_target_stale");
            if (target->GetVictim() == context.Bot)
                return BotActionArbitration::Outcome::NotApplicable(
                    "taunt_target_already_held");
            uint32 const tauntSpell = FirstKnownSpell(context.Bot,
                MaloriakTauntSpells);
            if (!tauntSpell)
                return BotActionArbitration::Outcome::NotApplicable(
                    "taunt_spell_unknown");
            if (!TryCastCombatSpell(context.Bot, target, tauntSpell))
                return BotActionArbitration::Outcome::Retryable(
                    "native_taunt_retryable");
            context.Situation = "adaptive_maloriak";
            context.Action = "maloriak_taunt";
            context.State.LastDecisionHandler = "adaptive_maloriak";
            return BotActionArbitration::Outcome::Started(
                "native_taunt_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(taunt));
    }

    if (plan.LustWindow && Cohort().EncounterSnapshot)
    {
        BotActionArbitration::Candidate lust;
        lust.Key = "adaptive_maloriak:phase_two_raid_haste:"
            + std::to_string(Party().ValidationRouteGeneration);
        lust.Source = "adaptive_maloriak";
        lust.ActionPriority = BotActionArbitration::Priority::Support;
        lust.UtilityScore = 95.0f;
        lust.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast);
        lust.Attempt = [this, &context, snapshot = Cohort().EncounterSnapshot]()
        {
            using namespace BotEncounter::MagmawBloodlust;
            // Any active raid haste or Sated-style lockout ends the window,
            // so exactly one native cast lands per lockout period.
            if (FindRaidLockout(*snapshot))
                return BotActionArbitration::Outcome::NotApplicable(
                    "raid_haste_lockout");
            std::optional<uint32> spellId = SelectKnownBloodlustSpell(
                context.Bot->HasSpell(BloodlustSpell),
                context.Bot->HasSpell(HeroismSpell));
            if (!spellId && context.Bot->HasSpell(TimeWarpSpell))
                spellId = TimeWarpSpell;
            if (!spellId)
                return BotActionArbitration::Outcome::NotApplicable(
                    "raid_haste_spell_unknown");
            std::string failure;
            if (!TryCastFriendlySpell(context.Bot, context.Bot, *spellId, &failure))
                return BotActionArbitration::Outcome::Retryable(
                    "native_raid_haste_retryable");
            context.Situation = "adaptive_maloriak";
            context.Action = "phase_two_raid_haste";
            context.State.LastDecisionHandler = "adaptive_maloriak";
            return BotActionArbitration::Outcome::Started(
                "native_raid_haste_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(lust));
    }

    // Kill credit: adaptive owners skip the generic route objective, so this
    // observation records the native boss engagement the route needs
    // (RememberValidationRouteBossEngagement -> NotifyCreatureDeath). It
    // mirrors adaptive Magmaw's observer with Maloriak-specific strings and
    // never changes target or focus.
    auto observe = [this, &context]() -> BotActionArbitration::Outcome
    {
        if (!context.AdaptiveMaloriakOwnsNode
            || Cohort().Config.ValidationRouteKind != "boss"
            || Cohort().Config.ValidationRouteNodeId
                != BotEncounter::Maloriak::EncounterNode)
            return BotActionArbitration::Outcome::NotApplicable(
                "maloriak_route_observation_not_owned");

        Unit* target = context.Target;
        Creature const* creature = target ? target->ToCreature() : nullptr;
        if (!target || !creature || !target->IsAlive()
            || !context.Bot->IsValidAttackTarget(target)
            || !IsNativeCombatObserved(context.Bot, target))
            return BotActionArbitration::Outcome::NotApplicable(
                "maloriak_route_observation_wait_for_native_combat");
        if (!BotEncounter::Maloriak::IsDeclaredEncounterEntry(creature->GetEntry()))
            return BotActionArbitration::Outcome::NotApplicable(
                "maloriak_route_observation_target_not_declared");

        // Only the boss itself binds the engagement (the callee checks the
        // route target entry); adds count as route progress.
        RememberValidationRouteBossEngagement(creature);

        bool const targetChanged = context.State.LastDecisionTargetGuid
            != target->GetGUID();
        bool const firstEngagement = !context.State.WasInCombat;
        if (!targetChanged && !firstEngagement)
            return BotActionArbitration::Outcome::NotApplicable(
                "maloriak_route_observation_already_recorded");

        float const targetHealthPct = UnitHealthPct(target);
        RecordRouteProgress(context.State, context.Bot, target,
            "route_target_combat_progress", targetHealthPct, targetHealthPct,
            0, 20);
        Party().ValidationRouteObservedEngagement = true;
        std::string raw = BuildRawJson(context.Bot, target);
        std::string semantic = BuildSemanticJson(context.Bot, target,
            "adaptive_maloriak", &context.Power, context.Stage,
            context.ChosenActivity.Activity);
        RecordEvent(context.State, context.Bot, "validation_target_priority",
            target, "native_combat_observed", raw.c_str(), semantic.c_str(),
            context.Bot->GetExactDist(target),
            Cohort().Config.ValidationRouteTargetEntry, 0);
        RecordEvent(context.State, context.Bot, "boss_action", target,
            "native_combat_observed", raw.c_str(), semantic.c_str(),
            context.Bot->GetExactDist(target),
            Cohort().Config.ValidationRouteTargetEntry, 0);
        if (firstEngagement)
            RecordEvent(context.State, context.Bot, "boss_started", target,
                "native_combat_observed", raw.c_str(), semantic.c_str(),
                context.Bot->GetExactDist(target),
                Cohort().Config.ValidationRouteTargetEntry, 0);
        context.State.WasInCombat = true;
        return BotActionArbitration::Outcome::NotApplicable(
            "adaptive_maloriak_route_observation_recorded");
    };
    BotActionArbitration::Candidate observation;
    observation.Key = "world.validation_route_maloriak_observation";
    observation.Source = "validation_route_observer";
    observation.ActionPriority = BotActionArbitration::Priority::Mechanic;
    observation.UtilityScore = 0.0f;
    observation.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::None);
    observation.Attempt = std::move(observe);
    context.State.DecisionKernel.Submit(std::move(observation));
}
