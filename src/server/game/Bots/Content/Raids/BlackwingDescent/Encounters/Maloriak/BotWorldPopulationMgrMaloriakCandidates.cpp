#include "Bots/BotEncounterCooldownHold.h"
#include "Bots/BotEncounterInterruptVeto.h"
#include "Bots/BotEncounterOffenseRestriction.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakAddSwitch.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "Group.h"
#include "Log.h"
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
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>

// Kernel candidates for the adaptive Maloriak plan (BotAdaptiveMaloriakStrategy.h).
// Every candidate submits one ordinary native request (move, interrupt,
// dispel, taunt, raid haste, auto-attack suppression) and revalidates the
// observed fact at the native edge, so a stale plan never spends a cooldown
// on an ended cast, a removed buff or an admitted Release Aberrations. The
// route observation credits the native kill to the route, as adaptive
// Magmaw's observer does for Magmaw.
namespace
{
using BotWorldPopulationMgrNativeHelpers::HasPowerForSpell;
using BotWorldPopulationMgrNativeHelpers::IsNativeCombatObserved;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotWorldPopulationMgrSpellSemantics::HasNearbyProtectedEncounterTarget;
using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;

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

// Loose (selectable) and reserve (still asleep) living Aberrations.
std::pair<std::size_t, std::size_t> NativeAberrationCounts(Unit* boss)
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
    return { loose, reserve };
}

bool HasRemedy(Unit const* unit)
{
    for (uint32 spellId : BotEncounter::Maloriak::RemedySpells)
        if (unit->HasAura(spellId))
            return true;
    return false;
}

// Every BotWorldPopulationMgr::TryCastCombatSpell gate except the bot's own
// casting state, in the same order, so a bot only stops its cast when the
// duty spell would then be submitted (r03 logged Wind Shear no_line_of_sight
// 24 times; an out-of-sight Shaman must keep its Lava Burst).
bool DutySpellCastable(Player* bot, Unit* target, uint32 spellId)
{
    if (!bot || !target || !spellId || !target->IsAlive()
        || !bot->IsValidAttackTarget(target))
        return false;
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
    if (!spellInfo || !bot->IsWithinLOSInMap(target))
        return false;
    uint64 const ownerGuid = bot->GetGUID().GetRawValue();
    if (BotRaidAreaAuthority::IsAllOffenseSuppressed(ownerGuid))
        return false;
    if (Creature const* creature = target->ToCreature();
        creature && BotRaidAreaAuthority::IsProtectedEncounterTarget(
            ownerGuid, creature->GetEntry(), creature->GetSpawnId(),
            creature->GetGUID().GetRawValue()))
        return false;
    if (HasNearbyProtectedEncounterTarget(bot, target, spellInfo)
        && SpellHasHostileMultiTargetSemantics(spellInfo))
        return false;
    if (bot->HasUnitState(UNIT_STATE_CONTROLLED)
        || (spellInfo->PreventionType == SPELL_PREVENTION_TYPE_SILENCE
            && bot->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_SILENCED))
        || (spellInfo->PreventionType == SPELL_PREVENTION_TYPE_PACIFY
            && bot->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PACIFIED)))
        return false;
    float const maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    if (!bot->IsWithinDistInMap(target, maxRange))
        return false;
    if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo)
        || !bot->GetSpellHistory()->IsReady(spellInfo))
        return false;
    return HasPowerForSpell(bot, spellInfo);
}

// A healer keeps a heal in progress while anyone in its raid is below
// Maloriak::HealerKeepsHealBelowPct; everyone else yields to the duty.
bool OwnCastYields(Player* bot, bool healer)
{
    Spell const* current = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL);
    if (!current)
        current = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
    bool const helpful = current && current->GetSpellInfo()->IsPositive();
    float lowest = 100.0f;
    if (healer && helpful)
        if (Group* group = bot->GetGroup())
            for (GroupReference* itr = group->GetFirstMember(); itr; itr = itr->next())
                if (Player* member = itr->GetSource();
                    member && member->IsAlive() && member->IsInMap(bot))
                    lowest = std::min(lowest, member->GetHealthPct());
    return BotEncounter::Maloriak::OwnCastYieldsToDuty(healer, helpful, lowest);
}

// TryCastCombatSpell refuses while the bot is casting, and casters chain hard
// casts, so r03's one Remedy (25000/s, 225000 healed) was never purged. A bot
// assigned an interrupt or purge stops its own cast first, as a player would,
// when the duty spell would then pass every cast gate and the cast it drops
// is not a needed heal.
bool ClearOwnCastFor(Player* bot, bool healer, Unit* target, uint32 spellId)
{
    if (!bot->HasUnitState(UNIT_STATE_CASTING))
        return true;
    if (!OwnCastYields(bot, healer) || !DutySpellCastable(bot, target, spellId))
        return false;
    bot->InterruptNonMeleeSpells(false);
    return true;
}

// Bosses whose add-switch cap was already reported (map, instance, boss
// GUID); the latched switch itself lives in the cohort latch store
// (BotMaloriakLatches.h).
std::mutex AddSwitchCapMutex;
std::set<std::tuple<uint32, uint32, uint64>> AddSwitchCapReported;

bool ClaimAddSwitchCapReport(Player const* bot, ObjectGuid boss)
{
    std::lock_guard<std::mutex> guard(AddSwitchCapMutex);
    return AddSwitchCapReported.emplace(bot->GetMapId(), bot->GetInstanceId(),
        boss.GetRawValue()).second;
}

// The largest area radius of a spell or the spells it triggers (Blizzard,
// Hurricane and Rain of Fire channel a periodic trigger with the area).
float HostileAreaRadius(Unit* caster, SpellInfo const* spellInfo, uint8 depth = 0)
{
    if (!spellInfo || depth > 3)
        return 0.0f;
    float radius = 0.0f;
    for (SpellEffectInfo const& effect : spellInfo->Effects)
    {
        if (!effect.IsEffect() && !effect.IsAura())
            continue;
        for (SpellTargetIndex index : { SpellTargetIndex::TargetA, SpellTargetIndex::TargetB })
            if (effect.HasRadius(index))
                radius = std::max(radius, effect.CalcRadius(caster, index));
        if (effect.TriggerSpell)
            radius = std::max(radius, HostileAreaRadius(caster,
                sSpellMgr->GetSpellInfo(effect.TriggerSpell), depth + 1));
    }
    return radius;
}

// The hook's stop of running casts that would still reach the boss (one
// aimed at him, or a hostile area spell such as a ground Blizzard or a
// self-centred Hellfire whose area covers him): each such slot is
// interrupted, whatever its explicit target (a self-cast Hellfire's is the
// bot). Helpful spells never; other slots untouched. A generic cast already
// launched (a projectile in flight) is not recalled (withDelayed false).
std::size_t StopCastsReachingBoss(Player* bot, Unit* boss)
{
    if (!bot || !boss)
        return 0;
    std::size_t stopped = 0;
    for (CurrentSpellTypes slot : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL,
             CURRENT_AUTOREPEAT_SPELL })
    {
        Spell const* spell = bot->GetCurrentSpell(slot);
        if (!spell || !spell->GetSpellInfo())
            continue;
        SpellInfo const* spellInfo = spell->GetSpellInfo();
        bool const aimedAtBoss = spell->m_targets.GetUnitTargetGUID() == boss->GetGUID();
        bool areaOverBoss = false;
        if (!aimedAtBoss && SpellHasHostileMultiTargetSemantics(spellInfo))
        {
            Position center = bot->GetPosition();
            if (spell->m_targets.HasDst())
                center = spell->m_targets.GetDstPos()->GetPosition();
            else if (Unit* target = ObjectAccessor::GetUnit(*bot,
                         spell->m_targets.GetUnitTargetGUID()))
                center = target->GetPosition();
            float const radius = std::max(HostileAreaRadius(bot, spellInfo), 8.0f);
            areaOverBoss = boss->GetExactDist2d(center.GetPositionX(), center.GetPositionY())
                <= radius + boss->GetCombatReach();
        }
        if (!BotEncounter::Maloriak::AddSwitchStopsCast(spellInfo->IsPositive(),
                aimedAtBoss, areaOverBoss))
            continue;
        bot->InterruptSpell(slot, slot == CURRENT_CHANNELED_SPELL, true);
        ++stopped;
    }
    return stopped;
}

// One Arcane Storm interrupt or taunt on the boss stays allowed for a restricted
// bot, for its native cast only; the destructor restores the hook's
// restriction.
void AllowOneCastOnBoss(std::optional<BotEncounterOffense::SingleCastAllowance>& allowance,
    Player const* bot, bool restricted, Unit const* target)
{
    if (target && BotEncounter::Maloriak::AddSwitchAllowanceApplies(restricted,
            target->GetEntry()))
        allowance.emplace(bot->GetGUID().GetRawValue(),
            BotEncounter::Maloriak::AddSwitchRestriction(), target->GetGUID());
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
    // cast starts, so a generic rotation interrupt cannot cut a release: the
    // user tactic lets every release through in phase one.
    if (!plan.Boss.IsEmpty())
    {
        Unit* boss = plan.ReleaseAdmitted
            ? ObjectAccessor::GetUnit(*context.Bot, plan.Boss) : nullptr;
        // Keyed by map and instance: creature GUIDs are generated per map,
        // so two concurrent instances of map 669 can share Maloriak's GUID.
        BotEncounterInterruptVeto::Set(context.Bot->GetMapId(),
            context.Bot->GetInstanceId(), plan.Boss.GetRawValue(),
            BotEncounter::Maloriak::ReleaseAberrationsSpell,
            boss && boss->IsAlive());
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
        // Every proposal, the main tank's hold of its spot included, goes
        // through the ordinary native request: only a submitted move renews
        // the mechanic movement lease that keeps combat-range movement from
        // chasing the boss back to the cauldron.
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

    // The add switch is the cohort latch (its cap included) the plan
    // resolved. Its restriction comes from the route-authority hook
    // (SubmitMaloriakRouteAuthority), which runs after the adaptive route
    // authority clears it and before the kernel resolves; the suppression
    // below only clears this bot's target, melee and pet while it waits for
    // the next release.
    bool const restricted = plan.AddSwitchRestricts;
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
        interrupt.Attempt = [this, &context, lane, restricted,
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
            if (castSpellId == BotEncounter::Maloriak::ReleaseAberrationsSpell)
                return BotActionArbitration::Outcome::NotApplicable(
                    "release_aberrations_never_interrupted");
            uint32 const interruptSpell = FirstKnownSpell(context.Bot,
                MaloriakInterruptSpells);
            if (!interruptSpell)
                return BotActionArbitration::Outcome::NotApplicable(
                    "interrupt_spell_unknown");
            bool const healer = std::string_view(
                GetDungeonRole(context.Bot)) == "healer";
            std::optional<BotEncounterOffense::SingleCastAllowance> allowance;
            AllowOneCastOnBoss(allowance, context.Bot, restricted, caster);
            if (!ClearOwnCastFor(context.Bot, healer, caster, interruptSpell))
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
            bool const healer = std::string_view(
                GetDungeonRole(context.Bot)) == "healer";
            // The plan assigns Remedy only outside the add switch; there is
            // no allowance, so the switch restriction refuses a stale purge.
            if (!ClearOwnCastFor(context.Bot, healer, target, dispelSpell))
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
        taunt.Attempt = [this, &context, restricted, targetGuid = plan.TauntTarget]()
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
            std::optional<BotEncounterOffense::SingleCastAllowance> allowance;
            AllowOneCastOnBoss(allowance, context.Bot, restricted, target);
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

    // Misdirection or Tricks of the Trade onto the off-tank for a release
    // (user tactic): an ordinary native friendly cast, skipped while the
    // redirect from the last one is still pending on the caster.
    if (!plan.ThreatRedirectTarget.IsEmpty() && plan.ThreatRedirectSpellId)
    {
        BotActionArbitration::Candidate redirect;
        redirect.Key = "adaptive_maloriak:threat_redirect:"
            + std::to_string(plan.ThreatRedirectSpellId);
        redirect.Source = "adaptive_maloriak";
        redirect.ActionPriority = BotActionArbitration::Priority::ThreatControl;
        redirect.UtilityScore = 85.0f;
        redirect.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast);
        redirect.Attempt = [this, &context, spellId = plan.ThreatRedirectSpellId,
            targetGuid = plan.ThreatRedirectTarget]()
        {
            Player* tank = ObjectAccessor::GetPlayer(*context.Bot, targetGuid);
            if (!tank || !tank->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "threat_redirect_tank_unavailable");
            if (!context.Bot->HasSpell(spellId))
                return BotActionArbitration::Outcome::NotApplicable(
                    "threat_redirect_spell_unknown");
            if (context.Bot->HasAura(spellId))
                return BotActionArbitration::Outcome::NotApplicable(
                    "threat_redirect_pending");
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            if (!spellInfo || !context.Bot->GetSpellHistory()->IsReady(spellInfo))
                return BotActionArbitration::Outcome::NotApplicable(
                    "threat_redirect_cooldown");
            std::string failure;
            if (!TryCastFriendlySpell(context.Bot, tank, spellId, &failure))
                return BotActionArbitration::Outcome::Retryable(
                    "native_threat_redirect_retryable");
            context.Situation = "adaptive_maloriak";
            context.Action = "off_tank_threat_redirect";
            context.State.LastDecisionHandler = "adaptive_maloriak";
            return BotActionArbitration::Outcome::Started(
                "native_threat_redirect_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(redirect));
    }

    // Frost Shock on a loose Aberration the off-tank has not picked up yet.
    if (!plan.SlowTarget.IsEmpty())
    {
        BotActionArbitration::Candidate slow;
        slow.Key = "adaptive_maloriak:slow:" + std::to_string(plan.SlowTarget.GetRawValue());
        slow.Source = "adaptive_maloriak";
        slow.ActionPriority = BotActionArbitration::Priority::ThreatControl;
        slow.UtilityScore = 80.0f;
        slow.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target);
        slow.Attempt = [this, &context, targetGuid = plan.SlowTarget]()
        {
            Unit* target = ObjectAccessor::GetUnit(*context.Bot, targetGuid);
            uint32 const spellId = BotEncounter::Maloriak::FrostShockSpell;
            if (!target || !target->IsAlive() || target->HasAura(spellId))
                return BotActionArbitration::Outcome::NotApplicable(
                    "slow_target_stale");
            if (!context.Bot->HasSpell(spellId))
                return BotActionArbitration::Outcome::NotApplicable(
                    "slow_spell_unknown");
            if (!TryCastCombatSpell(context.Bot, target, spellId))
                return BotActionArbitration::Outcome::Retryable(
                    "native_slow_retryable");
            context.Situation = "adaptive_maloriak";
            context.Action = "aberration_frost_shock";
            context.State.LastDecisionHandler = "adaptive_maloriak";
            return BotActionArbitration::Outcome::Started(
                "native_slow_submitted");
        };
        context.State.DecisionKernel.Submit(std::move(slow));
    }

    // A trap laid at the hunter's feet (Freeze Trap 1499 and Ice Trap 13809
    // have a self range: they are placed where the hunter stands, the way a
    // player without Trap Launcher lays them), once the hunter is on the
    // plan's trap point. The Aberration is only the tactical condition.
    if (!plan.TrapTarget.IsEmpty() && plan.TrapSpellId)
    {
        BotActionArbitration::Candidate trap;
        trap.Key = "adaptive_maloriak:trap:" + std::to_string(plan.TrapTarget.GetRawValue());
        trap.Source = "adaptive_maloriak";
        trap.ActionPriority = BotActionArbitration::Priority::ThreatControl;
        trap.UtilityScore = 82.0f;
        trap.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast);
        trap.Attempt = [this, &context, targetGuid = plan.TrapTarget,
            wanted = plan.TrapSpellId, point = plan.TrapPoint]()
        {
            Unit* target = ObjectAccessor::GetUnit(*context.Bot, targetGuid);
            if (!target || !target->IsAlive())
                return BotActionArbitration::Outcome::NotApplicable(
                    "trap_target_stale");
            if (context.Bot->GetExactDist2d(point.X, point.Y)
                > BotEncounter::Maloriak::KiteTrapTolerance)
                return BotActionArbitration::Outcome::NotApplicable(
                    "trap_point_not_reached");
            uint32 spellId = wanted;
            if (!context.Bot->HasSpell(spellId))
                spellId = BotEncounter::Maloriak::IceTrapSpell;
            if (!context.Bot->HasSpell(spellId))
                return BotActionArbitration::Outcome::NotApplicable(
                    "trap_spell_unknown");
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            if (!spellInfo || !context.Bot->GetSpellHistory()->IsReady(spellInfo))
                return BotActionArbitration::Outcome::NotApplicable(
                    "trap_cooldown");
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                context.State, context.Bot,
                BotNativeAction::CastSpell{ ObjectGuid::Empty, spellId },
                BotMovementArbitration::Owner::Mechanic,
                BotMovementArbitration::Priority::Mechanic);
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
            {
                context.Situation = "adaptive_maloriak";
                context.Action = spellId == BotEncounter::Maloriak::FreezeTrapSpell
                    ? "aberration_freeze_trap" : "aberration_ice_trap";
                context.State.LastDecisionHandler = "adaptive_maloriak";
            }
            return outcome;
        };
        context.State.DecisionKernel.Submit(std::move(trap));
    }

    // Nature's Grasp on the off-tank while it holds Aberrations (a self
    // buff: an Aberration striking it is rooted), if the druid knows it.
    if (plan.NaturesGrasp)
    {
        BotActionArbitration::Candidate grasp;
        grasp.Key = "adaptive_maloriak:natures_grasp";
        grasp.Source = "adaptive_maloriak";
        grasp.ActionPriority = BotActionArbitration::Priority::ThreatControl;
        grasp.UtilityScore = 70.0f;
        grasp.RequiredResources = BotActionArbitration::Uses(
            BotActionArbitration::Resource::GlobalCooldown,
            BotActionArbitration::Resource::Cast);
        grasp.Attempt = [this, &context]()
        {
            uint32 const spellId = BotEncounter::Maloriak::NaturesGraspSpell;
            if (!context.Bot->HasSpell(spellId))
                return BotActionArbitration::Outcome::NotApplicable(
                    "natures_grasp_unknown");
            if (context.Bot->HasAura(spellId))
                return BotActionArbitration::Outcome::NotApplicable(
                    "natures_grasp_active");
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            if (!spellInfo || !context.Bot->GetSpellHistory()->IsReady(spellInfo))
                return BotActionArbitration::Outcome::NotApplicable(
                    "natures_grasp_cooldown");
            return ExecuteNativeActionIntent(context.State, context.Bot,
                BotNativeAction::CastSpell{ ObjectGuid::Empty, spellId },
                BotMovementArbitration::Owner::Mechanic,
                BotMovementArbitration::Priority::Mechanic);
        };
        context.State.DecisionKernel.Submit(std::move(grasp));
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

// Route-authority hook (BotMaloriakAddSwitch.h), called by
// SubmitValidationKernelFallbackCandidates right after
// ConfigureValidationRouteCombatAuthority clears the bot's current-encounter
// restriction, as Omnotron's is: the add switch's restriction, cooldown hold
// and guardian area sparing hold every tick of the latched switch, whichever
// candidate the kernel resolves. The leases lapse by themselves once the hook
// stops renewing them.
void BotWorldPopulationMgr::SubmitMaloriakRouteAuthority(
    BotUpdateContext& context)
{
    if (!context.Bot || !context.AdaptiveMaloriak
        || !context.AdaptiveMaloriak->OwnsNode)
        return;
    BotEncounter::AdaptiveMaloriakPlan const& plan = *context.AdaptiveMaloriak;
    uint64 const ownerGuid = context.Bot->GetGUID().GetRawValue();
    Unit* boss = plan.Boss.IsEmpty() ? nullptr
        : ObjectAccessor::GetUnit(*context.Bot, plan.Boss);
    if (plan.AddSwitchCapReleased && ClaimAddSwitchCapReport(context.Bot, plan.Boss))
    {
        // The switch ran long (the reserve stopped draining or the adds are
        // not dying): report the boss health, the chamber reserve and the
        // loose Aberrations it released at (once per boss).
        float const bossHealthPct = boss ? boss->GetHealthPct() : 0.0f;
        std::pair<std::size_t, std::size_t> const counts = boss
            ? NativeAberrationCounts(boss) : std::pair<std::size_t, std::size_t>{};
        TC_LOG_INFO("server", "Maloriak add switch cap released: boss %.1f%%, "
            "%u Aberrations in reserve, %u loose (map %u instance %u, cap %u ms)",
            bossHealthPct, uint32(counts.second), uint32(counts.first),
            context.Bot->GetMapId(), context.Bot->GetInstanceId(),
            uint32(BotEncounter::Maloriak::AddSwitchCapMs));
        std::string raw = BuildRawJson(context.Bot, boss);
        std::string semantic = BuildSemanticJson(context.Bot, boss,
            "adaptive_maloriak", &context.Power, context.Stage,
            context.ChosenActivity.Activity);
        RecordEvent(context.State, context.Bot, "boss_action", boss,
            "maloriak_add_switch_cap_released", raw.c_str(), semantic.c_str(),
            bossHealthPct, uint32(counts.second));
    }

    bool const restricted = plan.AddSwitchRestricts;
    BotEncounterCooldownHold::Set(ownerGuid, restricted);
    BotEncounterOffense::SetGuardianAreaSparing(ownerGuid, restricted);
    if (!restricted)
        return;
    BotEncounterOffense::ApplyOffenseRestriction(ownerGuid,
        BotEncounter::Maloriak::AddSwitchRestriction());
    // The restriction refuses new casts; one already running that would
    // still reach Maloriak (aimed at him, or a hostile area over him, a
    // self-cast Hellfire included) stops, slot by slot, auto-repeat
    // included; a heal never does. A projectile already launched lands, as
    // it would for a player (like a DoT already ticking).
    StopCastsReachingBoss(context.Bot, boss);
    // The pet stops and returns (the native Follow command: AttackStop, then
    // follow); PetAI then skips the restricted boss and picks up the owner's
    // Aberration.
    if (Pet* pet = context.Bot->GetPet(); pet && pet->GetCharmInfo()
        && pet->GetVictim() && pet->GetVictim()->GetGUID() == plan.Boss)
        ExecuteNativeActionIntent(context.State, context.Bot,
            BotNativeAction::PetCommand{ pet->GetGUID(),
                context.Bot->GetGUID(), COMMAND_FOLLOW },
            BotMovementArbitration::Owner::Mechanic,
            BotMovementArbitration::Priority::Mechanic);
}
