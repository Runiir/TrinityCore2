#include "Bots/BotSpellMinimumRange.h"
#include "Bots/BotBloodDecisionObservation.h"
#include "Bots/BotFireCombustionObservation.h"
#include "Bots/BotRaidCombatPotionHealthOwner.h"
#include "Bots/BotCanonicalRaidScope.h"
#include "Bots/BotRaidDemonologyHellfireLive.h"
#include "Bots/BotRaidRotationOverrides.h"
#include "Bots/BotSpellResolution.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrCombatResolverAdmission.h"
#include "Bots/BotCombatMaskEvaluation.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotWorldPopulationMgrCombatRange.h"
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"
#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace
{
using BotWorldPopulationMgrSpellSemantics::HasNearbyProtectedEncounterTarget;
}

ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction(Player* bot, Unit* target, uint32 hostileCount, bool densityOnly, uint32 excludedSpellId, bool areaOnly, bool selfCenteredOnly, bool forbidArea, bool allowMultidot, bool hostileTargetOnly, bool movementCompatibleOnly, char const* specTagOverride, bool publishDiagnostics, uint32 policyExcludedSpellId, uint32 scopedAreaSpellId, uint32 scopedAreaTargetEntry) const
{
    ResolvedCombatAction action;
    action.Valid = false;
    action.Type = "wait";
    action.DebugName = "no_valid_profile_action";
    if (!bot || !target || !target->IsAlive())
        return action;
    if (Creature const* creature = target->ToCreature();
        IsImmediateNextValidationRouteEncounterMember(creature))
    {
        action.TargetGuid = target->GetGUID();
        action.DebugName = "future_encounter_target_forbidden";
        return action;
    }

    std::string role = GetDungeonRole(bot);
    BotClassSpecActionProfile profile = specTagOverride && *specTagOverride
        ? BotClassSpecActionProfileStore::BuildForSpec(
            bot, role.c_str(), specTagOverride)
        : BotClassSpecActionProfileStore::Build(bot, role.c_str());
    // Round 3 raid-only class fixes (BotRaidRotationOverrides.h); dungeon and
    // calibration cohorts keep the world DB rows and decisions exactly.
    bool const raidRotationScope = Cohort().Raid.RaidInstance
        && bot->GetMap() && bot->GetMap()->IsRaid();
    if (raidRotationScope)
        BotRaidRotationOverrides::Apply(profile);
    // Round 4 Survival fixes: canonical-composition cohorts only, because the
    // legacy accepted Magmaw hunter is the same Orc Survival spec.
    if (raidRotationScope && BotCanonicalRaidScope::IsCanonicalCompositionScenario(
            Cohort().Config.ValidationRouteScenarioId))
        BotRaidRotationOverrides::ApplyCanonical(profile);
    action.MovementDirective = profile.MovementDirective;
    action.AutoAttackMode = profile.AutoAttackMode;
    action.MinRange = profile.MinRange;
    action.MaxRange = profile.MaxRange;

    Creature const* targetCreature = target->ToCreature();
    uint32 const targetEntry = targetCreature ? targetCreature->GetEntry() : 0;
    bool const solarEclipse = bot->HasAura(48517);
    BotEncounter::MagmawBalanceMushroomState const mushroomState =
        BotEncounter::ObserveMagmawBalanceMushroomState(
            bot, Cohort().Config.ValidationRouteEnable,
            Cohort().Config.ValidationRouteNodeId, profile.SpecTag,
            targetEntry, solarEclipse);

    RoleSaturationState saturation = BuildRoleSaturationState(bot, target, role.c_str());
    std::string roleGoal = BotProgressionGoalPolicy::RoleGoal(role);
    uint64 const maskEvaluatedAtMs = BotWorldPopulationMgrSpellSemantics::NowMs();
    std::string const maskEvaluation = BotCombatMaskEvaluation::Context(
        maskEvaluatedAtMs, bot, target, Cohort(), Party(),
        "ResolveProfileCombatAction");
    uint32 const requestedHostileCount = hostileCount;
    auto const potionHealthOwner = BotRaidCombatPotionHealthOwner::Resolve(bot, Cohort(), Party());
    std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile, potionHealthOwner);
    BotRaidCooldownReservation::RouteContext const cooldownRoute{
        Cohort().Config.ValidationRouteEnable,
        Cohort().Raid.RaidInstance,
        Cohort().Raid.EncounterInProgress,
        false,
        Cohort().Config.ValidationRouteKind,
        Cohort().Config.ValidationRouteNodeKind,
        Cohort().Raid.EncounterPhase};
    // Canonical raids: Hellfire starts on the enemies around the warlock, not
    // the target (BotRaidDemonologyHellfire.h).
    if (profile.SpecTag == "demonology_warlock" && bot->GetMap() && bot->GetMap()->IsRaid()
        && BotCanonicalRaidScope::IsCanonicalRaid(Cohort().Raid.RaidInstance,
            Cohort().Config.ValidationRouteScenarioId))
        BotRaidDemonologyHellfire::RejectStartsWithoutPack(bot, candidates);
    auto engagedWithBotParty = [bot](Unit* unit) -> bool
    {
        auto belongsToBotParty = [bot](Unit* participant) -> bool
        {
            Player* player = participant ? participant->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;
            return player && (player == bot || (bot->GetGroup() && player->GetGroup() == bot->GetGroup()));
        };
        if (!unit || (!unit->IsInCombat() && !unit->GetVictim()))
            return false;
        if (belongsToBotParty(unit->GetVictim()))
            return true;
        for (Unit* attacker : unit->getAttackers())
            if (belongsToBotParty(attacker))
                return true;
        return false;
    };
    auto effectiveSpellMinRange = [bot, target](BotActionCandidate const& candidate, float configuredMinRange) -> float
    {
        return BotSpellMinimumRange::Effective(bot, target,
            sSpellMgr->GetSpellInfo(candidate.ResolvedSpellId), configuredMinRange);
    };
    auto effectiveSpellMaxRange = [bot, target, raidRotationScope](BotActionCandidate const& candidate,
        float configuredMaxRange) -> float
    {
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.ResolvedSpellId);
        if (!spellInfo)
            return configuredMaxRange;

        float nativeMaxRange = bot->GetSpellMaxRangeForTarget(target, spellInfo);
        if (spellInfo->RangeEntry
            && (spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE))
            nativeMaxRange = std::max(nativeMaxRange,
                bot->GetMeleeRange(target));
        else
            nativeMaxRange += bot->GetCombatReach() + target->GetCombatReach();
        // An unset melee action maximum inherits native reach. The profile
        // range and raw DBC melee range are approach defaults, not explicit
        // action caps; clipping to them rejects legal large-hitbox attacks.
        // In raid scope only, a declared maximum of exactly the nominal 5 yd
        // (the DB float 5) is the same approach default: r02-b1 rejected
        // Assassination Mutilate as max_range_exceeded at 5.4-7.5 yd (Magmaw
        // 1,831x; zero Mutilate on the Maloriak lab patrol) while melee swings
        // landed there. Dungeon and calibration rows keep the intersection.
        if (spellInfo->RangeEntry && (spellInfo->RangeEntry->Flags & SPELL_RANGE_MELEE)
            && (candidate.Profile.MaxRange <= 0.0f
                || (raidRotationScope
                    && candidate.Profile.MaxRange == NOMINAL_MELEE_RANGE)))
            return nativeMaxRange;
        // A profile maximum is a policy cap, never permission to extend the
        // native spell envelope.  Shadowflame exposed the distinction: its
        // profile allowed a 15-yard approach while the core rejected that
        // point.  Intersect the configured and native limits so movement and
        // final Spell::CheckRange agree.
        return configuredMaxRange > 0.0f
            ? std::min(configuredMaxRange, nativeMaxRange)
            : nativeMaxRange;
    };

    if (!hostileCount)
    {
        hostileCount = 1;
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(target, 12.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(target, objects, check);
        Cell::VisitAllObjects(target, searcher, 12.0f);
        for (WorldObject* object : objects)
        {
            Unit* unit = object ? object->ToUnit() : nullptr;
            if (unit && unit != target && unit->IsAlive() && bot->IsValidAttackTarget(unit)
                && engagedWithBotParty(unit)
                && !IsImmediateNextValidationRouteEncounterMember(unit->ToCreature()))
                ++hostileCount;
        }
    }

    // Fire AoE is multi-DoT first. Select up to three engaged enemies that do
    // not already carry this mage's Living Bomb, while preserving the normal
    // priority target for every other action.
    if (allowMultidot
        && !HasNearbyProtectedEncounterTarget(bot, target)
        && bot->getClass() == CLASS_MAGE && hostileCount >= 3 && bot->HasSpell(44457))
    {
        std::vector<Unit*> spreadTargets = { target };
        std::vector<WorldObject*> nearbyObjects;
        Trinity::AllWorldObjectsInRange spreadCheck(target, 12.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> spreadSearcher(
            target, nearbyObjects, spreadCheck);
        Cell::VisitAllObjects(target, spreadSearcher, 12.0f);
        for (WorldObject* object : nearbyObjects)
        {
            Unit* unit = object ? object->ToUnit() : nullptr;
            Creature* creature = unit ? unit->ToCreature() : nullptr;
            if (!unit || unit == target || !unit->IsAlive() || !bot->IsValidAttackTarget(unit))
                continue;
            if (IsImmediateNextValidationRouteEncounterMember(creature))
                continue;
            if (!engagedWithBotParty(unit) && (!creature || !IsTrainingDummy(creature)))
                continue;
            spreadTargets.push_back(unit);
        }
        std::sort(spreadTargets.begin(), spreadTargets.end(), [bot](Unit const* left, Unit const* right)
        {
            return bot->GetExactDist(left) < bot->GetExactDist(right);
        });

        uint32 activeLivingBombs = 0;
        for (Unit* spreadTarget : spreadTargets)
            if (spreadTarget->HasAura(44457, bot->GetGUID()))
                ++activeLivingBombs;
        if (activeLivingBombs < 3)
        {
            for (Unit* spreadTarget : spreadTargets)
            {
                if (spreadTarget->HasAura(44457, bot->GetGUID()))
                    continue;
                std::vector<BotActionCandidate> spreadCandidates =
                    BotClassSpecActionProfileStore::BuildCandidates(bot, spreadTarget, profile, potionHealthOwner);
                auto livingBomb = std::find_if(spreadCandidates.begin(), spreadCandidates.end(), [excludedSpellId](BotActionCandidate const& candidate)
                {
                    return candidate.SpellId == 44457 && candidate.SpellId != excludedSpellId
                        && candidate.RejectReason.empty();
                });
                if (livingBomb == spreadCandidates.end())
                    break;

                action.Valid = true;
                action.Type = "cast";
                action.SpellId = 44457;
                action.TargetGuid = spreadTarget->GetGUID();
                action.DebugName = "living_bomb_spread";
                action.MovementDirective = livingBomb->Profile.MovementDirective.empty()
                    ? profile.MovementDirective : livingBomb->Profile.MovementDirective;
                action.AutoAttackMode = livingBomb->Profile.AutoAttackMode.empty()
                    ? profile.AutoAttackMode : livingBomb->Profile.AutoAttackMode;
                action.MinRange = livingBomb->Profile.MinRange > 0.0f
                    ? livingBomb->Profile.MinRange : profile.MinRange;
                action.MaxRange = livingBomb->Profile.MaxRange > 0.0f
                    ? livingBomb->Profile.MaxRange : profile.MaxRange;
                action.InterruptCurrentChanneledSpell = livingBomb->InterruptCurrentChanneledSpell;
                return action;
            }
        }
    }

    BotActionCandidate* best = nullptr;
    BotActionCandidate* bestInterrupt = nullptr;
    BotActionCandidate* bestDensityRecovery = nullptr;
    BotActionCandidate* bestDensityResourceFallback = nullptr;
    BotActionCandidate* bestDensityGenerator = nullptr;
    BotActionCandidate* bestDensityFallback = nullptr;
    BotActionCandidate* bestRangeRecovery = nullptr;
    BotActionCandidate* bestMagmawMushroomPlacement = nullptr;
    BotActionCandidate* bestMagmawMushroomDetonation = nullptr;
    auto candidatePreferred = [](BotActionCandidate const& candidate, BotActionCandidate const* current) -> bool
    {
        return !current || candidate.Profile.PriorityBucket < current->Profile.PriorityBucket
            || (candidate.Profile.PriorityBucket == current->Profile.PriorityBucket
                && (candidate.Score > current->Score
                    || (candidate.Score == current->Score && candidate.Profile.SortOrder < current->Profile.SortOrder)
                    || (candidate.Score == current->Score && candidate.Profile.SortOrder == current->Profile.SortOrder
                        && candidate.ActionId < current->ActionId)));
    };
    // The per-candidate admission gates and ranking live in
    // BotWorldPopulationMgrCombatResolverAdmission.cpp.
    ProfileCombatAdmission admission{
        .Bot = bot,
        .Target = target,
        .Role = role,
        .Profile = profile,
        .RaidRotationScope = raidRotationScope,
        .TargetEntry = targetEntry,
        .SolarEclipse = solarEclipse,
        .MushroomState = mushroomState,
        .Saturation = saturation,
        .PotionHealthOwner = potionHealthOwner,
        .CooldownRoute = cooldownRoute,
        .HostileCount = hostileCount,
        .DensityOnly = densityOnly,
        .ExcludedSpellId = excludedSpellId,
        .AreaOnly = areaOnly,
        .SelfCenteredOnly = selfCenteredOnly,
        .ForbidArea = forbidArea,
        .HostileTargetOnly = hostileTargetOnly,
        .MovementCompatibleOnly = movementCompatibleOnly,
        .PolicyExcludedSpellId = policyExcludedSpellId,
        .ScopedAreaSpellId = scopedAreaSpellId,
        .ScopedAreaTargetEntry = scopedAreaTargetEntry,
        .EffectiveSpellMinRange = std::ref(effectiveSpellMinRange),
        .EffectiveSpellMaxRange = std::ref(effectiveSpellMaxRange),
        .CandidatePreferred = candidatePreferred,
        .Candidates = candidates,
        .Action = action,
        .Best = best,
        .BestInterrupt = bestInterrupt,
        .BestDensityRecovery = bestDensityRecovery,
        .BestDensityResourceFallback = bestDensityResourceFallback,
        .BestDensityGenerator = bestDensityGenerator,
        .BestDensityFallback = bestDensityFallback,
        .BestRangeRecovery = bestRangeRecovery,
        .BestMagmawMushroomPlacement = bestMagmawMushroomPlacement,
        .BestMagmawMushroomDetonation = bestMagmawMushroomDetonation};
    AdmitProfileCombatCandidates(admission);

    // A real, profile-declared interrupt must preempt ordinary rotation choices
    // only while the selected target is actively casting. The candidate has
    // already passed resource, cooldown, range, and all other profile gates.
    if (bestInterrupt)
        best = bestInterrupt;
    else if (bestMagmawMushroomDetonation)
        best = bestMagmawMushroomDetonation;
    else if (bestMagmawMushroomPlacement)
        best = bestMagmawMushroomPlacement;
    else if (!densityOnly && bestRangeRecovery
        && candidatePreferred(*bestRangeRecovery, best))
        best = bestRangeRecovery;
    else if (densityOnly)
    {
        Powers primaryPowerType = bot->GetPowerType();
        uint32 maxPrimaryPower = bot->GetMaxPower(primaryPowerType);
        float primaryPowerPct = maxPrimaryPower
            ? float(bot->GetPower(primaryPowerType)) / float(maxPrimaryPower) : 1.0f;
        bool resourcePressure = primaryPowerPct <= 0.25f;
        if (bot->GetMaxPower(POWER_MANA))
            resourcePressure = float(bot->GetPower(POWER_MANA)) / float(bot->GetMaxPower(POWER_MANA)) <= 0.25f;
        best = bestDensityRecovery
            ? bestDensityRecovery
            : (bestDensityResourceFallback
                ? bestDensityResourceFallback
                : (resourcePressure && bestDensityGenerator
                    ? bestDensityGenerator
                : (bestDensityFallback ? bestDensityFallback : bestDensityGenerator)));
    }

    if (!best || !best->SpellId)
        RecordNoProfileActionRejections(bot, candidates);

    if (publishDiagnostics)
    {
        if (bot->getClass() == CLASS_MAGE && profile.SpecTag == "fire"
            && target && target != bot && bot->IsValidAttackTarget(target)
            && std::any_of(candidates.begin(), candidates.end(), [](BotActionCandidate const& candidate) { return candidate.SpellId == 11129; }))
        {
            auto const observation = BotFireCombustionObservation::Capture(bot, target, maskEvaluatedAtMs,
                BotWorldPopulationMgrSpellSemantics::NowMs());
            candidates.front().ObservationJson = BotFireCombustionObservation::ToJson(observation);
        }
        uint32 botKey = bot->GetGUID().GetCounter();
        BotBloodDecisionObservation::Attach(bot, candidates, best, profile.SpecTag, maskEvaluatedAtMs, BotRoleSaturationPolicy::ToString(saturation.RecommendedBalanceMode), action.ObservationJson);
        std::ostringstream rejectionJson;
        rejectionJson << '[';
        bool firstReject = true;
        for (BotActionCandidate const& candidate : candidates)
        {
            if (!candidate.SpellId || candidate.RejectReason.empty())
                continue;
            if (!firstReject)
                rejectionJson << ',';
            firstReject = false;
            rejectionJson << "{\"spell_id\":" << candidate.SpellId
                          << ",\"reason\":\"" << JsonEscape(candidate.RejectReason) << "\"}";
        }
        rejectionJson << ']';
        Party().LastCombatRejectsByBot[botKey] = rejectionJson.str();
        Party().LastSaturationByBot[botKey] = saturation;
        std::ostringstream maskFilters;
        maskFilters << std::boolalpha << "{\"hostile_count\":" << requestedHostileCount
            << ",\"effective_hostile_count\":" << hostileCount
            << ",\"density_only\":" << densityOnly
            << ",\"excluded_spell_id\":" << excludedSpellId
            << ",\"policy_excluded_spell_id\":" << policyExcludedSpellId
            << ",\"area_only\":" << areaOnly
            << ",\"self_centered_only\":" << selfCenteredOnly
            << ",\"forbid_area\":" << forbidArea
            << ",\"allow_multidot\":" << allowMultidot
            << ",\"hostile_target_only\":" << hostileTargetOnly
            << ",\"movement_compatible_only\":" << movementCompatibleOnly
            << ",\"spec_tag_override\":" << BotCombatMaskEvaluation::Quote(specTagOverride ? specTagOverride : "") << "}";
        Party().LastCombatMaskByBot[botKey] = BotCombatMaskEvaluation::Append(
            BotClassSpecActionProfileStore::CandidateMaskJson(candidates, profile,
                roleGoal.c_str(), saturation.ToJson().c_str()), maskEvaluation,
            maskFilters.str());
        Party().LastChosenCombatByBot[botKey] = BotClassSpecActionProfileStore::ChosenActionJson(best, profile, roleGoal.c_str(), BotRoleSaturationPolicy::ToString(saturation.RecommendedBalanceMode), saturation.ExperimentConfidence);
        Party().LastActionCategoryByBot[botKey] = best ? BotCombatActionCatalog::ToString(best->Category) : "wait";
    }

    if (!best || !best->SpellId)
        return ResolveNoProfileAction(bot, target, profile, candidates,
            areaOnly, action);

    action.Valid = true;
    action.Type = best->Category == BotCombatActionCategory::UseItem ? "use_item" : "cast";
    action.SpellId = best->SpellId;
    bool selfTarget = best->Profile.TargetSelector == "self";
    action.TargetGuid = selfTarget ? bot->GetGUID() : target->GetGUID();
    bool const selectedMagmawMushroomPlacement =
        BotEncounter::IsMagmawBalanceMushroomPlacement(mushroomState, *best);
    bool const selectedMagmawMushroomDetonation =
        BotEncounter::IsMagmawBalanceMushroomDetonation(mushroomState, *best);
    bool const selectedMagmawMushroomAction =
        selectedMagmawMushroomPlacement || selectedMagmawMushroomDetonation;
    action.AllowMagmawBalanceMushroomSplash = selectedMagmawMushroomAction;
    action.AllowScopedEncounterAreaDamage = scopedAreaSpellId
        && scopedAreaTargetEntry == targetEntry && best->SpellId == scopedAreaSpellId;
    if (selectedMagmawMushroomPlacement
        && !BotEncounter::SetMagmawBalanceMushroomGroundTarget(action, bot, target))
    {
        // A destination-location spell must never fall back to the hostile
        // target when the live lava spawn disappeared between observation and
        // submission. Wait for the next lava spawn instead of placing the
        // mushroom on Magmaw or the exposed head.
        action.Valid = false;
        action.ResolutionReason = "magmaw_lava_spawn_ground_target_unavailable";
        action.DebugName = action.ResolutionReason;
        return action;
    }
    action.DebugName = BotCombatActionCatalog::ToString(best->Category);
    action.MovementDirective = best->Profile.MovementDirective.empty() ? profile.MovementDirective : best->Profile.MovementDirective;
    action.AutoAttackMode = best->Profile.AutoAttackMode.empty() ? profile.AutoAttackMode : best->Profile.AutoAttackMode;
    action.InterruptCurrentChanneledSpell = best->InterruptCurrentChanneledSpell;
    action.MinRange = selfTarget ? 0.0f : (best->Profile.MinRange > 0.0f ? best->Profile.MinRange : profile.MinRange);
    if (!selfTarget)
        action.MinRange = effectiveSpellMinRange(*best, action.MinRange);
    // A self-centered hostile action can still have a player-positioning
    // envelope. Shadowflame and Holy Wrath are cast on the player, while the
    // selected hostile remains the movement/facing anchor. Positive self-target
    // actions have no hostile range envelope and therefore resolve to zero.
    SpellInfo const* selectedSpellInfo = sSpellMgr->GetSpellInfo(best->ResolvedSpellId);
    bool const selectedSpellIsHostile = selectedSpellInfo
        && !selectedSpellInfo->IsPositive();
    float const selfCenteredHostileMaxRange =
        BotWorldPopulationMgrCombatRange::ResolveSelfCenteredHostileMaxRange(
            selfTarget, target != bot, selectedSpellIsHostile,
            best->Profile.MaxRange);
    action.MaxRange = selfTarget
        ? selfCenteredHostileMaxRange
        : (best->Profile.MaxRange > 0.0f
            ? best->Profile.MaxRange : profile.MaxRange);
    action.SuppressAreaDamage = forbidArea && !selectedMagmawMushroomAction
        && !action.AllowScopedEncounterAreaDamage;
    if (!selfTarget && best->Profile.MaxRange <= 0.0f)
        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(best->ResolvedSpellId))
            action.MaxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    if (!selfTarget)
        action.MaxRange = effectiveSpellMaxRange(*best, action.MaxRange);
    return action;
}
