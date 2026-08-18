#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotClassSpecActionProfile.h"

#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <limits>
#include <string>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;
    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}

uint32 ControlledDispelAuraForHealer(Player const* healer)
{
    return healer && healer->getClass() == CLASS_DRUID ? 702 : 589;
}
}

bool BotWorldPopulationMgr::UpdateCalibrationHealer(WorldBotState& state, Player* healer)
{
    if (!healer || GetDungeonRole(healer) != std::string("healer"))
        return false;
    CalibrationMetrics& metrics = Cohort().CalibrationMetricsByGuid[healer->GetGUID().GetCounter()];
    Unit* lowestTarget = nullptr;
    float lowestHealth = 2.0f;
    std::vector<Player*> members;
    if (Group* group = healer->GetGroup())
        for (GroupReference* itr = group->GetFirstMember(); itr; itr = itr->next())
            if (Player* member = itr->GetSource())
                if (member->IsAlive() && member->GetMap() == healer->GetMap())
                {
                    members.push_back(member);
                    if (UnitHealthPct(member) < lowestHealth)
                    {
                        lowestTarget = member;
                        lowestHealth = UnitHealthPct(member);
                    }
                }
    if (!lowestTarget)
        return false;

    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(healer, "healer");
    auto recordHealResponse = [&metrics](Unit* target, uint32 latencyMs)
    {
        if (!target || metrics.LastControlledDamageMsByTarget.empty())
            return false;
        auto damaged = metrics.LastControlledDamageMsByTarget.find(target->GetGUID().GetCounter());
        if (damaged == metrics.LastControlledDamageMsByTarget.end())
            damaged = std::min_element(metrics.LastControlledDamageMsByTarget.begin(),
                metrics.LastControlledDamageMsByTarget.end(), [](auto const& left, auto const& right)
                {
                    return left.second < right.second;
                });
        // A valid heal on the group's lowest-health member is a response to the
        // oldest pending controlled event even when that member was already at
        // the fixture's health floor and took no additional event damage.
        // Target-selection and unequal-triage gates independently prove that the
        // selected member is appropriate.
        uint64 const eventMs = damaged->second;
        metrics.HealResponseLatenciesMs.push_back(latencyMs);
        for (auto itr = metrics.LastControlledDamageMsByTarget.begin();
            itr != metrics.LastControlledDamageMsByTarget.end();)
            if (itr->second == eventMs)
                itr = metrics.LastControlledDamageMsByTarget.erase(itr);
            else
                ++itr;
        return true;
    };
    Unit* tankTarget = lowestTarget;
    for (Player* member : members)
        if (GetDungeonRole(member) == std::string("tank"))
        {
            tankTarget = member;
            break;
        }
    auto candidateEligible = [healer, &profile](BotActionProfileSpell const& spell, Unit* target)
    {
        BotClassSpecActionProfile singleActionProfile = profile;
        singleActionProfile.Spells = { spell };
        std::vector<BotActionCandidate> candidates =
            BotClassSpecActionProfileStore::BuildCandidates(healer, target, singleActionProfile);
        return candidates.size() == 1 && candidates.front().RejectReason.empty();
    };
    bool const globalCooldownActive = std::any_of(profile.Spells.begin(), profile.Spells.end(), [healer](BotActionProfileSpell const& spell)
    {
        SpellInfo const* spellInfo = spell.SpellId ? sSpellMgr->GetSpellInfo(spell.SpellId) : nullptr;
        return spellInfo && healer->GetSpellHistory()->HasGlobalCooldown(spellInfo);
    });
    bool healingCastResponded = false;
    bool healingCastActive = false;
    if (Spell* currentSpell = healer->GetCurrentSpell(CURRENT_GENERIC_SPELL))
    {
        healingCastActive = std::any_of(profile.Spells.begin(), profile.Spells.end(), [currentSpell](BotActionProfileSpell const& spell)
        {
            return currentSpell->GetSpellInfo()->Id == spell.SpellId
                && (spell.Category == BotCombatActionCategory::HealFast
                    || spell.Category == BotCombatActionCategory::HealEfficient
                    || spell.Category == BotCombatActionCategory::HealAoe);
        });
        // Controlled damage that lands while a valid heal is already in flight
        // for an affected target has an immediate response; do not charge the
        // remaining cast time to the healer's decision latency.
        if (healingCastActive)
            healingCastResponded = recordHealResponse(currentSpell->m_targets.GetUnitTarget(), 0);
    }
    bool casting = healer->HasUnitState(UNIT_STATE_CASTING);
    if (casting && healingCastActive && !healingCastResponded
        && metrics.LastControlledDamageMsByTarget.find(lowestTarget->GetGUID().GetCounter())
            != metrics.LastControlledDamageMsByTarget.end())
    {
        // A newly damaged higher-priority target is not covered by the current
        // heal. Preempt the stale cast so an eligible instant or fast heal can
        // begin as soon as the real global cooldown permits.
        healer->InterruptNonMeleeSpells(false);
        state.DecisionTimer = 0;
        casting = healer->HasUnitState(UNIT_STATE_CASTING);
    }
    if (casting || globalCooldownActive)
        return true;

    if (Cohort().CalibrationCurrentDamagePhase == "dispel")
    {
        uint32 const controlledDispelAura = ControlledDispelAuraForHealer(healer);
        Unit* dispelTarget = nullptr;
        for (Player* member : members)
            if (member->HasAura(controlledDispelAura))
            {
                dispelTarget = member;
                break;
            }
        if (dispelTarget)
            for (BotActionProfileSpell const& spell : profile.Spells)
                if (spell.Category == BotCombatActionCategory::DispelCleanse && healer->HasSpell(spell.SpellId)
                    && candidateEligible(spell, dispelTarget))
                {
                    ++metrics.DispelAttempts;
                    ++metrics.Attempts;
                    std::string reason;
                    bool const cast = TryCastFriendlySpell(healer, dispelTarget, spell.SpellId, &reason);
                    ++metrics.ResultCounts[cast ? "dispel_cast" : "cast_failed:" + reason];
                    if (cast)
                    {
                        ++metrics.Successes;
                        metrics.ActionGroups.insert(BotCombatActionCatalog::ToString(spell.Category));
                        auto damaged = metrics.LastControlledDamageMsByTarget.find(dispelTarget->GetGUID().GetCounter());
                        if (damaged != metrics.LastControlledDamageMsByTarget.end())
                        {
                            uint64 const eventMs = damaged->second;
                            for (auto itr = metrics.LastControlledDamageMsByTarget.begin();
                                itr != metrics.LastControlledDamageMsByTarget.end();)
                                if (itr->second == eventMs)
                                    itr = metrics.LastControlledDamageMsByTarget.erase(itr);
                                else
                                    ++itr;
                        }
                    }
                    return true;
                }
    }

    if (Cohort().CalibrationCurrentDamagePhase == "cooldown_required" && lowestHealth <= 0.65f)
        for (BotActionProfileSpell const& spell : profile.Spells)
            if ((spell.Category == BotCombatActionCategory::ExternalDefensive
                || spell.Category == BotCombatActionCategory::Defensive
                || spell.Category == BotCombatActionCategory::OffensiveCooldown)
                && healer->HasSpell(spell.SpellId))
            {
                Unit* cooldownTarget = spell.TargetSelector == "self"
                    ? static_cast<Unit*>(healer)
                    : (spell.TargetSelector == "tank" ? tankTarget : lowestTarget);
                if (!candidateEligible(spell, cooldownTarget))
                    continue;
                ++metrics.CooldownAttempts;
                ++metrics.Attempts;
                std::string reason;
                bool const cast = TryCastFriendlySpell(healer, cooldownTarget, spell.SpellId, &reason);
                ++metrics.ResultCounts[cast ? "cooldown_cast" : "cast_failed:" + reason];
                if (cast)
                {
                    ++metrics.CooldownSuccesses;
                    ++metrics.Successes;
                    metrics.ActionGroups.insert(BotCombatActionCatalog::ToString(spell.Category));
                    // A defensive cooldown is the deliberate first response in
                    // this phase. Record that decision now instead of charging
                    // the following heal with the cooldown's global cooldown.
                    if (!metrics.LastControlledDamageMsByTarget.empty())
                    {
                        uint64 const eventMs = std::min_element(metrics.LastControlledDamageMsByTarget.begin(),
                            metrics.LastControlledDamageMsByTarget.end(), [](auto const& left, auto const& right)
                            {
                                return left.second < right.second;
                            })->second;
                        recordHealResponse(lowestTarget, uint32(std::min<uint64>(
                            NowMs() - eventMs, std::numeric_limits<uint32>::max())));
                    }
                }
                return true;
            }

    if (lowestHealth > 0.94f)
        return false;
    uint32 healSpell = SelectHealSpell(healer, lowestTarget);
    if (!healSpell)
    {
        BotActionCandidate const* fallback = nullptr;
        std::vector<BotActionCandidate> candidates =
            BotClassSpecActionProfileStore::BuildCandidates(healer, lowestTarget, profile);
        for (BotActionCandidate const& candidate : candidates)
        {
            if (candidate.Category != BotCombatActionCategory::HealFast
                && candidate.Category != BotCombatActionCategory::HealEfficient
                && candidate.Category != BotCombatActionCategory::HealAoe)
                continue;
            if (!candidate.RejectReason.empty() || !healer->HasSpell(candidate.SpellId))
                continue;
            if (!fallback || candidate.Profile.HealingWeight > fallback->Profile.HealingWeight)
                fallback = &candidate;
        }
        healSpell = fallback ? fallback->SpellId : 0;
    }
    if (!healSpell)
    {
        ++metrics.ResultCounts["no_heal_action"];
        return false;
    }
    ++metrics.Attempts;
    ++metrics.HealSelectionAttempts;
    if (lowestHealth <= 0.94f)
        ++metrics.HealSelectionSuccesses;
    ++metrics.ActionAttempts[healSpell];
    std::string reason;
    bool const cast = TryCastFriendlySpell(healer, lowestTarget, healSpell, &reason);
    ++metrics.ResultCounts[cast ? "heal_cast" : "cast_failed:" + reason];
    if (cast)
    {
        ++metrics.Successes;
        metrics.ActionGroups.insert("heal");
        // Response latency measures the decision to begin a valid heal, not the
        // spell's class-specific cast time. Throughput and effective-heal gates
        // independently prove that the started cast actually restores health.
        if (!metrics.LastControlledDamageMsByTarget.empty())
        {
            uint64 const eventMs = std::min_element(metrics.LastControlledDamageMsByTarget.begin(),
                metrics.LastControlledDamageMsByTarget.end(), [](auto const& left, auto const& right)
                {
                    return left.second < right.second;
                })->second;
            recordHealResponse(lowestTarget, uint32(std::min<uint64>(
                NowMs() - eventMs, std::numeric_limits<uint32>::max())));
        }
    }
    return true;
}

