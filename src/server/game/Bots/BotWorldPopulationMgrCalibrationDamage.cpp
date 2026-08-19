#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotClassSpecActionProfile.h"

#include "CellImpl.h"
#include "CharmInfo.h"
#include "Creature.h"
#include "DynamicObject.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Pet.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
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

void BotWorldPopulationMgr::DrainCalibrationPostWindowEffects()
{
    if (!Cohort().CalibrationActive || !Cohort().CalibrationWindowComplete)
        return;

    Cohort().CalibrationLastPostWindowDrainMs = NowMs();
    for (WorldBotState const& state : Party().CalibrationBots)
    {
        Player* bot = GetLoadedBot(state);
        if (!bot)
            continue;
        bot->InterruptNonMeleeSpells(true);
        // Consecration and Immolation Aura use finite owner auras rather than
        // dynamic objects. Unholy Blight's proc driver can also reapply its
        // periodic aura when an in-flight Death Coil lands after the boundary.
        // Cancel these drivers before draining the completed window.
        bot->RemoveAurasDueToSpell(26573, bot->GetGUID(), 0, AuraRemoveFlags::ByCancel);
        bot->RemoveAurasDueToSpell(49194, bot->GetGUID(), 0, AuraRemoveFlags::ByCancel);
        bot->RemoveAurasDueToSpell(50536, bot->GetGUID(), 0, AuraRemoveFlags::ByCancel);
        bot->RemoveAurasDueToSpell(50589, bot->GetGUID(), 0, AuraRemoveFlags::ByCancel);
        bot->CombatStopWithPets(true);
        // Freeze the completed window without stripping persistent class setup.
        // The clone is destroyed by StopCombatCalibration immediately after the
        // report is captured; removing every profile aura here invalidates the
        // post-window stat/setup snapshot and can disturb pet-backed teardown.
        // Repeat the target-side drain briefly so projectiles already in flight
        // cannot apply a new periodic aura after the exact boundary cleanup.

        std::vector<ObjectGuid> ownedCasterGuids = { bot->GetGUID() };
        std::vector<Unit*> ownedUnits = { bot };
        std::vector<TempSummon*> temporarySummons;
        Pet* pet = bot->GetPet();
        if (pet)
        {
            ownedCasterGuids.push_back(pet->GetGUID());
            ownedUnits.push_back(pet);
            pet->AttackStop();
            pet->InterruptNonMeleeSpells(true);
            pet->CombatStop(true);
            pet->FollowTarget(bot);
            if (CharmInfo* charmInfo = pet->GetCharmInfo())
            {
                charmInfo->SetCommandState(COMMAND_FOLLOW);
                charmInfo->SetIsCommandAttack(false);
                charmInfo->SetIsAtStay(false);
                charmInfo->SetIsReturning(true);
                charmInfo->SetIsCommandFollow(true);
                charmInfo->SetIsFollowing(false);
            }
        }
        std::vector<Unit*> controlledUnits(bot->m_Controlled.begin(), bot->m_Controlled.end());
        for (Unit* controlled : controlledUnits)
        {
            if (!controlled || controlled == pet)
                continue;
            ownedCasterGuids.push_back(controlled->GetGUID());
            ownedUnits.push_back(controlled);
            controlled->CombatStop(true);
            if (TempSummon* summon = controlled->ToTempSummon())
                temporarySummons.push_back(summon);
        }

        std::vector<WorldObject*> nearbyObjects;
        Trinity::AllWorldObjectsInRange dummyCheck(bot, 80.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> dummySearcher(bot, nearbyObjects, dummyCheck);
        Cell::VisitAllObjects(bot, dummySearcher, 80.0f);
        for (WorldObject* object : nearbyObjects)
        {
            DynamicObject* dynamicObject = object ? object->ToDynObject() : nullptr;
            if (dynamicObject && std::find(ownedCasterGuids.begin(), ownedCasterGuids.end(),
                dynamicObject->GetCasterGUID()) != ownedCasterGuids.end())
                ownedCasterGuids.push_back(dynamicObject->GetGUID());
        }
        for (WorldObject* object : nearbyObjects)
        {
            Creature* dummy = object ? object->ToCreature() : nullptr;
            if (!dummy || !IsTrainingDummy(dummy))
                continue;
            dummy->CombatStop(true);
            dummy->GetThreatManager().ClearAllThreat();
            dummy->RemoveOwnedAuras([&ownedCasterGuids](Aura const* aura)
            {
                return aura && std::find(ownedCasterGuids.begin(), ownedCasterGuids.end(),
                    aura->GetCasterGUID()) != ownedCasterGuids.end();
            }, AuraRemoveFlags::ByCancel);
        }
        for (Unit* ownedUnit : ownedUnits)
        {
            ownedUnit->RemoveAllDynObjects();
            ownedUnit->RemoveAllGameObjects();
        }
        for (TempSummon* summon : temporarySummons)
            if (summon && summon->IsInWorld())
                summon->UnSummon();
    }
}

void BotWorldPopulationMgr::UpdateCalibrationControlledDamage()
{
    if (!Cohort().CalibrationScoredStartedMs || Cohort().CalibrationWindowComplete)
        return;
    bool const healerMode = Cohort().CalibrationMode == "healer_controlled_damage_300";
    bool const tankMode = Cohort().CalibrationMode == "tank_threat_300";
    if (!healerMode && !tankMode)
        return;

    uint64 const elapsedSecond = (NowMs() - Cohort().CalibrationScoredStartedMs) / 1000;
    if (elapsedSecond == Cohort().CalibrationLastControlledEventSecond)
        return;
    Cohort().CalibrationLastControlledEventSecond = elapsedSecond;

    std::string phase;
    uint32 interval = 5;
    float damageRatio = 0.07f;
    bool groupDamage = false;
    bool unequalDamage = false;
    bool dispelEvent = false;
    if (tankMode)
    {
        if (elapsedSecond < 120)
            phase = "tank_sustained_damage";
        else if (elapsedSecond < 180)
        {
            phase = "tank_burst_damage";
            interval = 10;
            damageRatio = 0.25f;
        }
        else if (elapsedSecond < 240)
        {
            phase = "tank_cooldown_required";
            interval = 15;
            damageRatio = 0.45f;
        }
        else
        {
            phase = "tank_endurance";
            damageRatio = 0.10f;
        }
    }
    else if (elapsedSecond < 60)
        phase = "sustained_tank_damage";
    else if (elapsedSecond < 90)
    {
        phase = "burst_tank_damage";
        interval = 15;
        damageRatio = 0.20f;
    }
    else if (elapsedSecond < 130)
    {
        phase = "group_damage";
        interval = 10;
        damageRatio = 0.10f;
        groupDamage = true;
    }
    else if (elapsedSecond < 170)
    {
        phase = "unequal_health_triage";
        interval = 10;
        damageRatio = 0.08f;
        groupDamage = true;
        unequalDamage = true;
    }
    else if (elapsedSecond < 200)
    {
        phase = "dispel";
        interval = 30;
        damageRatio = 0.0f;
        dispelEvent = true;
    }
    else if (elapsedSecond < 240)
    {
        phase = "cooldown_required";
        interval = 10;
        damageRatio = 0.40f;
        groupDamage = true;
    }
    else
        phase = "mana_endurance";
    Cohort().CalibrationCurrentDamagePhase = phase;
    auto targetMetrics = Cohort().CalibrationMetricsByGuid.find(Cohort().CalibrationTargetGuid.GetCounter());
    if (targetMetrics == Cohort().CalibrationMetricsByGuid.end())
        return;
    CalibrationMetrics& metrics = targetMetrics->second;

    uint32 const dueInterruptOpportunities = tankMode && elapsedSecond >= 30
        ? std::min<uint32>(5, uint32((elapsedSecond - 30) / 60 + 1)) : 0;
    if (dueInterruptOpportunities > metrics.InterruptSuccesses
        && Cohort().CalibrationInterruptTargetGuid.IsEmpty())
    {
        Player* tank = nullptr;
        for (WorldBotState const& state : Party().CalibrationBots)
            if (state.Guid == Cohort().CalibrationTargetGuid)
            {
                tank = GetLoadedBot(state);
                break;
            }
        uint32 interruptSpellId = 0;
        if (tank)
        {
            switch (tank->getClass())
            {
                case CLASS_WARRIOR: interruptSpellId = 6552; break;
                case CLASS_PALADIN: interruptSpellId = 96231; break;
                case CLASS_DEATH_KNIGHT: interruptSpellId = 47528; break;
                case CLASS_DRUID: interruptSpellId = 80964; break;
                default: break;
            }
        }
        SpellInfo const* interruptSpell = interruptSpellId ? sSpellMgr->GetSpellInfo(interruptSpellId) : nullptr;
        bool const interruptReady = tank && interruptSpell && tank->HasSpell(interruptSpellId)
            && !tank->HasUnitState(UNIT_STATE_CASTING)
            && !tank->GetSpellHistory()->HasGlobalCooldown(interruptSpell)
            && tank->GetSpellHistory()->IsReady(interruptSpell);
        if (interruptReady)
        {
            std::vector<WorldObject*> nearbyObjects;
            Trinity::AllWorldObjectsInRange dummyCheck(tank, 80.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> dummySearcher(
                tank, nearbyObjects, dummyCheck);
            Cell::VisitAllObjects(tank, dummySearcher, 80.0f);
            Creature* nearestDummy = nullptr;
            for (WorldObject* object : nearbyObjects)
            {
                Creature* dummy = object ? object->ToCreature() : nullptr;
                if (!dummy || !dummy->IsAlive() || !IsTrainingDummy(dummy)
                    || !tank->IsValidAttackTarget(dummy))
                    continue;
                if (!nearestDummy || tank->GetExactDist(dummy) < tank->GetExactDist(nearestDummy))
                    nearestDummy = dummy;
            }
            if (nearestDummy && !nearestDummy->IsNonMeleeSpellCast(false))
            {
                nearestDummy->CastSpell(tank, 686, false);
                if (nearestDummy->IsNonMeleeSpellCast(false))
                {
                    Cohort().CalibrationInterruptTargetGuid = nearestDummy->GetGUID();
                    if (metrics.InterruptChecks < dueInterruptOpportunities)
                        ++metrics.InterruptChecks;
                }
            }
        }
    }

    Creature* controlledDispelCaster = nullptr;
    uint32 controlledDispelAura = 589;
    if (healerMode)
    {
        Player* healer = nullptr;
        for (WorldBotState const& state : Party().CalibrationBots)
            if (state.Guid == Cohort().CalibrationTargetGuid)
            {
                healer = GetLoadedBot(state);
                break;
            }
        if (healer)
        {
            controlledDispelAura = ControlledDispelAuraForHealer(healer);
            std::vector<WorldObject*> nearbyObjects;
            Trinity::AllWorldObjectsInRange dummyCheck(healer, 80.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> dummySearcher(
                healer, nearbyObjects, dummyCheck);
            Cell::VisitAllObjects(healer, dummySearcher, 80.0f);
            Creature* nearestDummy = nullptr;
            for (WorldObject* object : nearbyObjects)
            {
                Creature* dummy = object ? object->ToCreature() : nullptr;
                if (!dummy || !dummy->IsAlive() || !IsTrainingDummy(dummy)
                    || !healer->IsValidAttackTarget(dummy))
                    continue;
                if (!nearestDummy || healer->GetExactDist(dummy) < healer->GetExactDist(nearestDummy))
                    nearestDummy = dummy;
            }
            if (nearestDummy)
            {
                controlledDispelCaster = nearestDummy;
                for (WorldBotState const& state : Party().CalibrationBots)
                    if (Player* member = GetLoadedBot(state))
                        if (member->IsAlive())
                        {
                            member->SetInCombatWith(nearestDummy);
                            nearestDummy->SetInCombatWith(member);
                        }
            }
        }
    }

    if (elapsedSecond % interval)
        return;
    if (healerMode)
        for (WorldBotState& state : Party().CalibrationBots)
            if (state.Guid == Cohort().CalibrationTargetGuid)
                if (Player* healer = GetLoadedBot(state))
                {
                    healer->InterruptNonMeleeSpells(true);
                    state.DecisionTimer = 0;
                    BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(healer, "healer");
                    for (BotActionProfileSpell const& spell : profile.Spells)
                        if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId))
                            healer->GetSpellHistory()->CancelGlobalCooldown(spellInfo);
                    break;
                }
    metrics.ScheduledDamagePhases.insert(phase);
    ++metrics.ScheduledDamageEvents;

    std::vector<Player*> recipients;
    Player* tank = nullptr;
    for (WorldBotState const& state : Party().CalibrationBots)
    {
        Player* member = GetLoadedBot(state);
        if (!member || !member->IsAlive())
            continue;
        if (GetDungeonRole(member) == std::string("tank"))
            tank = member;
        if (groupDamage && member->GetGUID() != Cohort().CalibrationTargetGuid)
            recipients.push_back(member);
    }
    if (!groupDamage)
    {
        Player* recipient = tankMode ? GetLoadedBot(Party().CalibrationBots.front()) : tank;
        if (recipient)
            recipients.push_back(recipient);
    }
    if (recipients.empty())
        return;

    bool delivered = false;
    uint64 const eventMs = NowMs();
    for (size_t index = 0; index < recipients.size(); ++index)
    {
        Player* recipient = recipients[index];
        if (!recipient)
            continue;
        if (dispelEvent)
        {
            if (!recipient->HasAura(controlledDispelAura) && controlledDispelCaster)
                controlledDispelCaster->AddAura(controlledDispelAura, recipient);
            delivered = delivered || recipient->HasAura(controlledDispelAura);
            if (delivered)
                metrics.LastControlledDamageMsByTarget[recipient->GetGUID().GetCounter()] = eventMs;
            break;
        }
        uint64 amount = uint64(float(recipient->GetMaxHealth()) * damageRatio * (unequalDamage ? float(index + 1) / float(recipients.size()) : 1.0f));
        uint64 const minimumHealth = std::max<uint64>(1, (uint64(recipient->GetMaxHealth()) * 21 + 99) / 100);
        uint64 const availableHealth = recipient->GetHealth() > minimumHealth
            ? recipient->GetHealth() - minimumHealth : 0;
        amount = std::min<uint64>(amount, availableHealth);
        if (!amount)
        {
            delivered = true;
            continue;
        }
        recipient->SetHealth(recipient->GetHealth() - amount);
        metrics.ControlledDamage += amount;
        metrics.MaximumControlledDamage = std::max(metrics.MaximumControlledDamage, amount);
        if (recipient->GetMaxHealth())
            metrics.MaximumControlledDamageRatio = std::max(
                metrics.MaximumControlledDamageRatio,
                float(amount) / float(recipient->GetMaxHealth()));
        metrics.MinimumHealthRatio = std::min(metrics.MinimumHealthRatio, UnitHealthPct(recipient));
        metrics.LastControlledDamageMsByTarget[recipient->GetGUID().GetCounter()] = eventMs;
        delivered = true;
    }
    if (delivered)
    {
        metrics.DeliveredDamagePhases.insert(phase);
        ++metrics.DeliveredDamageEvents;
    }
}
