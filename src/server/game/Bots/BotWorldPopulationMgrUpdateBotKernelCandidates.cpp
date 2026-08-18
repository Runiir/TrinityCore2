#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotAdaptiveRaidTrashStrategy.h"

#include "ObjectAccessor.h"
#include "CharmInfo.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <optional>
#include <string>
#include <string_view>
#include <utility>

using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;

void BotWorldPopulationMgr::SubmitAdaptiveKernelCandidates(
    BotUpdateContext& context)
{
        if (context.AdaptiveDrudgeMovement && context.AdaptiveDrudgeMovement->ExpiresAtMs > context.DecisionNowMs)
        {
            BotActionArbitration::Candidate movement;
            movement.Key = context.AdaptiveDrudgeMovement->Id.Key();
            movement.Source = context.AdaptiveDrudgeMovement->Id.Strategy;
            movement.ActionPriority = context.AdaptiveDrudgeMovement->ActionPriority;
            movement.UtilityScore = context.AdaptiveDrudgeMovement->Utility;
            movement.RequiredResources = context.AdaptiveDrudgeMovement->Resources();
            movement.ExpiresAtMs = context.AdaptiveDrudgeMovement->ExpiresAtMs;
            movement.Attempt = [&, intent = context.AdaptiveDrudgeMovement->Action]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, intent, BotMovementArbitration::Owner::Mechanic,
                    BotMovementArbitration::Priority::Mechanic);
                if (outcome.Result == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "adaptive_drudge";
                    context.Action = "adaptive_drudge_movement";
                    context.State.LastDecisionHandler = "adaptive_drudge";
                }
                return outcome;
            };
            context.State.DecisionKernel.Submit(std::move(movement));
        }

        if (context.AdaptiveMagmawMovement && context.AdaptiveMagmawMovement->ExpiresAtMs > context.DecisionNowMs)
        {
            BotActionArbitration::Candidate movement;
            movement.Key = context.AdaptiveMagmawMovement->Id.Key();
            movement.Source = context.AdaptiveMagmawMovement->Id.Strategy;
            movement.ActionPriority = context.AdaptiveMagmawMovement->ActionPriority;
            movement.UtilityScore = context.AdaptiveMagmawMovement->Utility;
            movement.RequiredResources = context.AdaptiveMagmawMovement->Resources();
            movement.ExpiresAtMs = context.AdaptiveMagmawMovement->ExpiresAtMs;
            movement.Attempt = [&, intent = context.AdaptiveMagmawMovement->Action]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, intent, BotMovementArbitration::Owner::Hazard,
                    BotMovementArbitration::Priority::Hazard);
                if (outcome.Result == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "adaptive_magmaw";
                    context.Action = "pillar_evade";
                    context.State.LastDecisionHandler = "adaptive_magmaw";
                }
                return outcome;
            };
            context.State.DecisionKernel.Submit(std::move(movement));
        }

        if (context.AdaptiveMagmawInteraction
            && context.AdaptiveMagmawInteraction->ExpiresAtMs > context.DecisionNowMs)
        {
            BotActionArbitration::Candidate mechanic;
            mechanic.Key = context.AdaptiveMagmawInteraction->Id.Key();
            mechanic.Source = context.AdaptiveMagmawInteraction->Id.Strategy;
            mechanic.ActionPriority = context.AdaptiveMagmawInteraction->ActionPriority;
            mechanic.UtilityScore = context.AdaptiveMagmawInteraction->Utility;
            mechanic.RequiredResources = context.AdaptiveMagmawInteraction->Resources();
            mechanic.ExpiresAtMs = context.AdaptiveMagmawInteraction->ExpiresAtMs;
            mechanic.Attempt = [&, intent = context.AdaptiveMagmawInteraction->Action]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, intent, BotMovementArbitration::Owner::Mechanic,
                    BotMovementArbitration::Priority::Mechanic);
                if (outcome.Result == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "adaptive_magmaw";
                    context.Action = "native_pincer_interaction";
                    context.State.LastDecisionHandler = "adaptive_magmaw";
                }
                return outcome;
            };
            context.State.DecisionKernel.Submit(std::move(mechanic));
        }

        if (context.AdaptiveOmnotronMovement
            && context.AdaptiveOmnotronMovement->ExpiresAtMs > context.DecisionNowMs)
        {
            BotActionArbitration::Candidate movement;
            movement.Key = context.AdaptiveOmnotronMovement->Id.Key();
            movement.Source = context.AdaptiveOmnotronMovement->Id.Strategy;
            movement.ActionPriority = context.AdaptiveOmnotronMovement->ActionPriority;
            movement.UtilityScore = context.AdaptiveOmnotronMovement->Utility;
            movement.RequiredResources = context.AdaptiveOmnotronMovement->Resources();
            movement.ExpiresAtMs = context.AdaptiveOmnotronMovement->ExpiresAtMs;
            movement.Attempt = [&, intent = context.AdaptiveOmnotronMovement->Action]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, intent, BotMovementArbitration::Owner::Hazard,
                    BotMovementArbitration::Priority::Hazard);
                if (outcome.Result == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "adaptive_omnotron";
                    context.Action = "omnotron_hazard_movement";
                    context.State.LastDecisionHandler = "adaptive_omnotron";
                }
                return outcome;
            };
            context.State.DecisionKernel.Submit(std::move(movement));
        }

        if (context.AdaptiveOmnotronSuppressOffense)
        {
            BotActionArbitration::Candidate suppress;
            suppress.Key = "adaptive_omnotron:shield_suppress:"
                + std::to_string(Party().ValidationRouteGeneration);
            suppress.Source = "adaptive_omnotron";
            suppress.ActionPriority = BotActionArbitration::Priority::Mechanic;
            suppress.UtilityScore = 100.0f;
            suppress.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::Pet);
            suppress.Attempt = [&]()
            {
                bool const submitted = SubmitMeleeAutoAttackIntent(context.State,
                    BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
                    BotMeleeAutoAttack::Owner::Mechanic,
                    BotActionArbitration::Priority::Mechanic,
                    "adaptive_omnotron_shield_suppress");
                if (Pet* pet = context.Bot->GetPet(); pet && pet->GetCharmInfo())
                    ExecuteNativeActionIntent(context.State, context.Bot,
                        BotNativeAction::PetCommand{ pet->GetGUID(),
                            context.Bot->GetGUID(), COMMAND_FOLLOW },
                        BotMovementArbitration::Owner::Mechanic,
                        BotMovementArbitration::Priority::Mechanic);
                context.State.TargetGuid.Clear();
                context.Target = nullptr;
                context.Situation = "adaptive_omnotron";
                context.Action = "shield_damage_suppressed";
                context.State.LastDecisionHandler = "adaptive_omnotron";
                return submitted
                    ? BotActionArbitration::Outcome::Committed(
                        "melee_autoattack_suppression_submitted")
                    : BotActionArbitration::Outcome::Retryable(
                        "melee_autoattack_suppression_rejected");
            };
            context.State.DecisionKernel.Submit(std::move(suppress));
        }

        if (!context.AdaptiveOmnotronInterruptTargetGuid.IsEmpty())
        {
            BotActionArbitration::Candidate interrupt;
            interrupt.Key = "adaptive_omnotron:arcane_annihilator:"
                + std::to_string(context.AdaptiveOmnotronInterruptTargetGuid.GetRawValue());
            interrupt.Source = "adaptive_omnotron";
            interrupt.ActionPriority = BotActionArbitration::Priority::Interrupt;
            interrupt.UtilityScore = 90.0f;
            interrupt.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::GlobalCooldown,
                BotActionArbitration::Resource::Cast,
                BotActionArbitration::Resource::Target);
            interrupt.Attempt = [&, context.AdaptiveOmnotronInterruptTargetGuid]()
            {
                Unit* caster = ObjectAccessor::GetUnit(*context.Bot,
                    context.AdaptiveOmnotronInterruptTargetGuid);
                if (!caster || !caster->IsAlive())
                    return BotActionArbitration::Outcome::NotApplicable(
                        "interrupt_caster_stale");
                uint32 interruptSpell = 0;
                for (uint32 spellId : { 6552u, 1766u, 2139u, 57994u,
                        96231u, 47528u, 80964u, 80965u, 15487u, 34490u })
                    if (context.Bot->HasSpell(spellId))
                    {
                        interruptSpell = spellId;
                        break;
                    }
                if (!interruptSpell
                    || !TryCastCombatSpell(context.Bot, caster, interruptSpell))
                    return BotActionArbitration::Outcome::Retryable(
                        "native_interrupt_retryable");
                context.Situation = "adaptive_omnotron";
                context.Action = "arcane_annihilator_interrupt";
                context.State.LastDecisionHandler = "adaptive_omnotron";
                return BotActionArbitration::Outcome::Started(
                    "native_interrupt_submitted");
            };
            context.State.DecisionKernel.Submit(std::move(interrupt));
        }

        if (context.AdaptiveMaloriakMovement
            && context.AdaptiveMaloriakMovement->ExpiresAtMs > context.DecisionNowMs)
        {
            BotActionArbitration::Candidate movement;
            movement.Key = context.AdaptiveMaloriakMovement->Id.Key();
            movement.Source = context.AdaptiveMaloriakMovement->Id.Strategy;
            movement.ActionPriority = context.AdaptiveMaloriakMovement->ActionPriority;
            movement.UtilityScore = context.AdaptiveMaloriakMovement->Utility;
            movement.RequiredResources = context.AdaptiveMaloriakMovement->Resources();
            movement.ExpiresAtMs = context.AdaptiveMaloriakMovement->ExpiresAtMs;
            movement.Attempt = [&, intent = context.AdaptiveMaloriakMovement->Action]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, intent, BotMovementArbitration::Owner::Hazard,
                    BotMovementArbitration::Priority::Hazard);
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

        if (!context.AdaptiveMaloriakInterruptTargetGuid.IsEmpty())
        {
            BotActionArbitration::Candidate interrupt;
            interrupt.Key = "adaptive_maloriak:arcane_storm:"
                + std::to_string(context.AdaptiveMaloriakInterruptTargetGuid.GetRawValue());
            interrupt.Source = "adaptive_maloriak";
            interrupt.ActionPriority = BotActionArbitration::Priority::Interrupt;
            interrupt.UtilityScore = 95.0f;
            interrupt.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::GlobalCooldown,
                BotActionArbitration::Resource::Cast,
                BotActionArbitration::Resource::Target);
            interrupt.Attempt = [&, context.AdaptiveMaloriakInterruptTargetGuid]()
            {
                Unit* caster = ObjectAccessor::GetUnit(*context.Bot,
                    context.AdaptiveMaloriakInterruptTargetGuid);
                if (!caster || !caster->IsAlive())
                    return BotActionArbitration::Outcome::NotApplicable(
                        "interrupt_caster_stale");
                uint32 interruptSpell = 0;
                for (uint32 spellId : { 6552u, 1766u, 2139u, 57994u,
                        96231u, 47528u, 80964u, 80965u, 15487u, 34490u })
                    if (context.Bot->HasSpell(spellId))
                    {
                        interruptSpell = spellId;
                        break;
                    }
                if (!interruptSpell
                    || !TryCastCombatSpell(context.Bot, caster, interruptSpell))
                    return BotActionArbitration::Outcome::Retryable(
                        "native_interrupt_retryable");
                context.Situation = "adaptive_maloriak";
                context.Action = "arcane_storm_interrupt";
                context.State.LastDecisionHandler = "adaptive_maloriak";
                return BotActionArbitration::Outcome::Started(
                    "native_interrupt_submitted");
            };
            context.State.DecisionKernel.Submit(std::move(interrupt));
        }

        if (!context.AdaptiveMaloriakDispelTargetGuid.IsEmpty())
        {
            BotActionArbitration::Candidate dispel;
            dispel.Key = "adaptive_maloriak:remedy:"
                + std::to_string(context.AdaptiveMaloriakDispelTargetGuid.GetRawValue());
            dispel.Source = "adaptive_maloriak";
            dispel.ActionPriority = BotActionArbitration::Priority::Interrupt;
            dispel.UtilityScore = 85.0f;
            dispel.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::GlobalCooldown,
                BotActionArbitration::Resource::Cast,
                BotActionArbitration::Resource::Target);
            dispel.Attempt = [&, context.AdaptiveMaloriakDispelTargetGuid]()
            {
                Unit* auraTarget = ObjectAccessor::GetUnit(*context.Bot,
                    context.AdaptiveMaloriakDispelTargetGuid);
                if (!auraTarget || !auraTarget->IsAlive())
                    return BotActionArbitration::Outcome::NotApplicable(
                        "dispel_target_stale");
                uint32 dispelSpell = 0;
                for (uint32 spellId : { 370u, 30449u, 528u, 19801u })
                    if (context.Bot->HasSpell(spellId))
                    {
                        dispelSpell = spellId;
                        break;
                    }
                if (!dispelSpell
                    || !TryCastCombatSpell(context.Bot, auraTarget, dispelSpell))
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

        if (context.AdaptiveChimaeronMovement
            && context.AdaptiveChimaeronMovement->ExpiresAtMs > context.DecisionNowMs)
        {
            BotActionArbitration::Candidate movement;
            movement.Key = context.AdaptiveChimaeronMovement->Id.Key();
            movement.Source = context.AdaptiveChimaeronMovement->Id.Strategy;
            movement.ActionPriority = context.AdaptiveChimaeronMovement->ActionPriority;
            movement.UtilityScore = context.AdaptiveChimaeronMovement->Utility;
            movement.RequiredResources = context.AdaptiveChimaeronMovement->Resources();
            movement.ExpiresAtMs = context.AdaptiveChimaeronMovement->ExpiresAtMs;
            movement.Attempt = [&, intent = context.AdaptiveChimaeronMovement->Action]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, intent, BotMovementArbitration::Owner::Mechanic,
                    BotMovementArbitration::Priority::Mechanic);
                if (outcome.Result == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "adaptive_chimaeron";
                    context.Action = "chimaeron_formation_movement";
                    context.State.LastDecisionHandler = "adaptive_chimaeron";
                }
                return outcome;
            };
            context.State.DecisionKernel.Submit(std::move(movement));
        }

        auto submitAtramedesCandidate = [&](BotNativeAction::Candidate const& intent,
            char const* actionName, BotMovementArbitration::Owner movementOwner,
            BotMovementArbitration::Priority movementPriority)
        {
            if (intent.ExpiresAtMs <= context.DecisionNowMs)
                return;
            BotActionArbitration::Candidate candidate;
            candidate.Key = intent.Id.Key();
            candidate.Source = intent.Id.Strategy;
            candidate.ActionPriority = intent.ActionPriority;
            candidate.UtilityScore = intent.Utility;
            candidate.RequiredResources = intent.Resources();
            candidate.ExpiresAtMs = intent.ExpiresAtMs;
            candidate.Attempt = [&, nativeIntent = intent.Action, actionName,
                movementOwner, movementPriority]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, nativeIntent, movementOwner, movementPriority);
                if (outcome.Result == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "adaptive_atramedes";
                    context.Action = actionName;
                    context.State.LastDecisionHandler = "adaptive_atramedes";
                }
                return outcome;
            };
            context.State.DecisionKernel.Submit(std::move(candidate));
        };
        if (context.AdaptiveAtramedesMovement)
            submitAtramedesCandidate(*context.AdaptiveAtramedesMovement,
                "atramedes_hazard_movement",
                BotMovementArbitration::Owner::Hazard,
                BotMovementArbitration::Priority::Hazard);
        if (context.AdaptiveAtramedesInteraction)
            submitAtramedesCandidate(*context.AdaptiveAtramedesInteraction,
                "atramedes_native_gong",
                BotMovementArbitration::Owner::Mechanic,
                BotMovementArbitration::Priority::Mechanic);

        if (context.AdaptiveNefarianMovement
            && context.AdaptiveNefarianMovement->ExpiresAtMs > context.DecisionNowMs)
        {
            BotActionArbitration::Candidate movement;
            movement.Key = context.AdaptiveNefarianMovement->Id.Key();
            movement.Source = context.AdaptiveNefarianMovement->Id.Strategy;
            movement.ActionPriority = context.AdaptiveNefarianMovement->ActionPriority;
            movement.UtilityScore = context.AdaptiveNefarianMovement->Utility;
            movement.RequiredResources = context.AdaptiveNefarianMovement->Resources();
            movement.ExpiresAtMs = context.AdaptiveNefarianMovement->ExpiresAtMs;
            movement.Attempt = [&, intent = context.AdaptiveNefarianMovement->Action]()
            {
                BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                    context.State, context.Bot, intent, BotMovementArbitration::Owner::Hazard,
                    BotMovementArbitration::Priority::Hazard);
                if (outcome.Result == BotActionArbitration::Disposition::Committed)
                {
                    context.Situation = "adaptive_nefarian";
                    context.Action = "nefarian_mechanic_movement";
                    context.State.LastDecisionHandler = "adaptive_nefarian";
                }
                return outcome;
            };
            context.State.DecisionKernel.Submit(std::move(movement));
        }

        if (!context.AdaptiveNefarianInterruptTargetGuid.IsEmpty())
        {
            BotActionArbitration::Candidate interrupt;
            interrupt.Key = "adaptive_nefarian:blast_nova:"
                + std::to_string(context.AdaptiveNefarianInterruptTargetGuid.GetRawValue());
            interrupt.Source = "adaptive_nefarian";
            interrupt.ActionPriority = BotActionArbitration::Priority::Interrupt;
            interrupt.UtilityScore = 100.0f;
            interrupt.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::GlobalCooldown,
                BotActionArbitration::Resource::Cast,
                BotActionArbitration::Resource::Target);
            interrupt.Attempt = [&, context.AdaptiveNefarianInterruptTargetGuid]()
            {
                Unit* caster = ObjectAccessor::GetUnit(*context.Bot,
                    context.AdaptiveNefarianInterruptTargetGuid);
                if (!caster || !caster->IsAlive())
                    return BotActionArbitration::Outcome::NotApplicable(
                        "interrupt_caster_stale");
                uint32 interruptSpell = 0;
                for (uint32 spellId : { 6552u, 1766u, 2139u, 57994u,
                        96231u, 47528u, 80964u, 80965u, 15487u, 34490u })
                    if (context.Bot->HasSpell(spellId))
                    {
                        interruptSpell = spellId;
                        break;
                    }
                if (!interruptSpell
                    || !TryCastCombatSpell(context.Bot, caster, interruptSpell))
                    return BotActionArbitration::Outcome::Retryable(
                        "native_interrupt_retryable");
                context.Situation = "adaptive_nefarian";
                context.Action = "blast_nova_interrupt";
                context.State.LastDecisionHandler = "adaptive_nefarian";
                return BotActionArbitration::Outcome::Started(
                    "native_interrupt_submitted");
            };
            context.State.DecisionKernel.Submit(std::move(interrupt));
        }

        if (!context.AdaptiveDrudgeTankTargetGuid.IsEmpty())
        {
            BotActionArbitration::Candidate ownership;
            ownership.Key = "adaptive_drudge:taunt:"
                + std::to_string(context.AdaptiveDrudgeTankTargetGuid.GetRawValue());
            ownership.Source = "adaptive_drudge";
            ownership.ActionPriority = BotActionArbitration::Priority::ThreatControl;
            ownership.UtilityScore = 4.0f;
            ownership.RequiredResources = BotActionArbitration::Uses(
                BotActionArbitration::Resource::GlobalCooldown,
                BotActionArbitration::Resource::Cast,
                BotActionArbitration::Resource::Target);
            ownership.Attempt = [&, context.AdaptiveDrudgeTankTargetGuid]()
            {
                Unit* source = ObjectAccessor::GetUnit(*context.Bot,
                    context.AdaptiveDrudgeTankTargetGuid);
                if (!source || !source->IsAlive())
                    return BotActionArbitration::Outcome::Retryable(
                        "assigned_drudge_stale");
                if (source->GetVictim() == context.Bot)
                    return BotActionArbitration::Outcome::NotApplicable(
                        "native_ownership_established");
                uint32 tauntSpell = 0;
                switch (context.Bot->getClass())
                {
                    case CLASS_WARRIOR: tauntSpell = 355; break;
                    case CLASS_PALADIN: tauntSpell = 62124; break;
                    case CLASS_DEATH_KNIGHT: tauntSpell = 56222; break;
                    case CLASS_DRUID: tauntSpell = 6795; break;
                    default: break;
                }
                if (!tauntSpell || !context.Bot->HasSpell(tauntSpell))
                    return BotActionArbitration::Outcome::Retryable(
                        "native_taunt_unavailable");
                if (!TryCastCombatSpell(context.Bot, source, tauntSpell))
                    return BotActionArbitration::Outcome::Retryable(
                        "native_taunt_retryable");
                context.Situation = "adaptive_drudge";
                context.Action = "native_taunt";
                context.State.LastDecisionHandler = "adaptive_drudge";
                return BotActionArbitration::Outcome::Started(
                    "native_taunt_submitted");
            };
            context.State.DecisionKernel.Submit(std::move(ownership));
        }

        bool adaptiveHazardMovementProposed = false;
        if (Cohort().EncounterSnapshot)
        {
            BotEncounter::AdaptiveRaidTrashStrategy adaptiveTrash;
            std::optional<BotNativeAction::Candidate> hazard =
                adaptiveTrash.ProposeHazardExit(*Cohort().EncounterSnapshot, context.Bot->GetGUID());
            if (hazard && hazard->ExpiresAtMs > context.DecisionNowMs)
            {
                adaptiveHazardMovementProposed = true;
                BotActionArbitration::Candidate candidate;
                candidate.Key = hazard->Id.Key();
                candidate.Source = hazard->Id.Strategy;
                candidate.ActionPriority = hazard->ActionPriority;
                candidate.UtilityScore = hazard->Utility;
                candidate.RequiredResources = hazard->Resources();
                candidate.ExpiresAtMs = hazard->ExpiresAtMs;
                candidate.Attempt = [&, intent = hazard->Action]()
                {
                    BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                        context.State, context.Bot, intent, BotMovementArbitration::Owner::Hazard,
                        BotMovementArbitration::Priority::Hazard);
                    if (outcome.Result != BotActionArbitration::Disposition::Committed)
                        return outcome;
                    context.Situation = "raid_trash_hazard";
                    context.Action = "adaptive_hazard_exit";
                    context.State.LastDecisionHandler = "adaptive_raid_trash";
                    return outcome;
                };
                context.State.DecisionKernel.Submit(std::move(candidate));
            }
        }

        // Healing is an independent candidate. A route wait or movement
        // transition must never suppress ordinary trained healing. While a
        // survival movement is active, select only an instant heal so the
        // cast cannot cancel the player's dodge spline.
        if (Cohort().EncounterSnapshot && std::string(GetDungeonRole(context.Bot)) == "healer"
            && !context.AdaptiveChimaeronHealingDisabled)
        {
            ObjectGuid healTargetGuid = context.AdaptiveChimaeronPriorityHealTargetGuid;
            float lowestHealth = 94.0f;
            if (!healTargetGuid.IsEmpty())
                if (BotEncounter::ActorSnapshot const* priority =
                        Cohort().EncounterSnapshot->FindActor(healTargetGuid))
                    lowestHealth = priority->HealthPct;
            if (healTargetGuid.IsEmpty())
                for (BotEncounter::ActorSnapshot const& member : Cohort().EncounterSnapshot->Players)
                    if (member.Alive && member.HealthPct < lowestHealth)
                {
                    lowestHealth = member.HealthPct;
                    healTargetGuid = member.Guid;
                }

            if (!healTargetGuid.IsEmpty())
            {
                BotActionArbitration::Candidate support;
                support.Key = "raid.support.heal."
                    + std::to_string(healTargetGuid.GetRawValue());
                support.Source = "adaptive_raid_support";
                support.ActionPriority = lowestHealth < 50.0f
                    ? BotActionArbitration::Priority::Mechanic
                    : BotActionArbitration::Priority::Support;
                support.UtilityScore = (100.0f - lowestHealth) / 100.0f;
                support.RequiredResources = BotActionArbitration::Uses(
                    BotActionArbitration::Resource::GlobalCooldown,
                    BotActionArbitration::Resource::Cast);
                support.Attempt = [&, healTargetGuid, adaptiveHazardMovementProposed]()
                {
                    Unit* healTarget = ObjectAccessor::GetUnit(*context.Bot, healTargetGuid);
                    if (!healTarget || !healTarget->IsAlive()
                        || !context.Bot->IsValidAssistTarget(healTarget))
                        return BotActionArbitration::Outcome::Retryable(
                            "heal_target_stale");
                    uint32 const healSpell = SelectHealSpell(
                        context.Bot, healTarget, adaptiveHazardMovementProposed);
                    if (!healSpell)
                        return BotActionArbitration::Outcome::Retryable(
                            adaptiveHazardMovementProposed
                                ? "no_instant_heal_while_moving"
                                : "no_trained_heal");
                    std::string failureReason;
                    if (!TryCastFriendlySpell(
                            context.Bot, healTarget, healSpell, &failureReason))
                        return BotActionArbitration::Outcome::Retryable(
                            failureReason.empty()
                                ? std::string_view("heal_cast_retryable")
                                : std::string_view(failureReason));

                    std::string raw = BuildRawJson(context.Bot, healTarget);
                    std::string semantic = BuildSemanticJson(context.Bot, healTarget,
                        "adaptive_raid_support", &context.Power, context.Stage,
                        context.ChosenActivity.Activity);
                    RecordEvent(context.State, context.Bot, "raid_heal", healTarget, "ok",
                        raw.c_str(), semantic.c_str(),
                        UnitHealthPct(healTarget), 0.0f, healSpell);
                    context.Situation = "adaptive_raid_support";
                    context.Action = "trained_heal";
                    context.State.LastDecisionHandler = "adaptive_raid_support";
                    return BotActionArbitration::Outcome::Started(
                        "trained_heal_submitted");
                };
                context.State.DecisionKernel.Submit(std::move(support));
            }
        }


}
