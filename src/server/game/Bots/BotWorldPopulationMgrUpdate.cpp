#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"
#include "Bots/BotMgr.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "Config.h"
#include "Cryptography/CryptoHash.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Group.h"
#include "Log.h"
#include "Pet.h"
#include "Player.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <limits>
#include <memory>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

struct OrdinaryPetSpellIdentity
{
    uint32 SpellId = 0;
    uint8 Active = 0;
    uint8 Type = 0;
};

struct OrdinaryPetSetupSnapshot
{
    bool Present = false;
    bool InWorld = false;
    bool Alive = false;
    bool Owned = false;
    bool Permanent = false;
    ObjectGuid Guid;
    uint32 Entry = 0;
    uint32 FamilyId = 0;
    uint32 PetType = uint32(MAX_PET_TYPE);
    uint32 CreatedBySpellId = 0;
    uint32 Health = 0;
    uint32 MaxHealth = 0;
    uint32 PowerType = 0;
    uint32 Power = 0;
    uint32 MaxPower = 0;
    std::vector<OrdinaryPetSpellIdentity> Spellbook;
    std::string SpellbookSha256;
    std::vector<uint32> AutocastSpellIds;
};

std::string OrdinaryPetSpellbookSha256(
    std::vector<OrdinaryPetSpellIdentity> const& spellbook)
{
    std::ostringstream canonical;
    for (size_t index = 0; index < spellbook.size(); ++index)
    {
        if (index)
            canonical << ';';
        OrdinaryPetSpellIdentity const& spell = spellbook[index];
        canonical << spell.SpellId << ':' << uint32(spell.Active)
                  << ':' << uint32(spell.Type);
    }
    std::string digest = ByteArrayToHexStr(
        Trinity::Crypto::SHA256::GetDigestOf(canonical.str()));
    std::transform(digest.begin(), digest.end(), digest.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });
    return digest;
}

OrdinaryPetSetupSnapshot ObserveOrdinaryPetSetup(Player const* bot)
{
    OrdinaryPetSetupSnapshot snapshot;
    if (!bot)
        return snapshot;

    Pet* pet = bot->GetPet();
    if (!pet)
        return snapshot;

    snapshot.Present = true;
    snapshot.InWorld = pet->IsInWorld();
    snapshot.Alive = pet->IsAlive();
    snapshot.Owned = pet->GetOwner() == bot;
    snapshot.Permanent = pet->IsPermanentPetFor(const_cast<Player*>(bot))
        && !pet->isTemporarySummoned()
        && (pet->getPetType() == SUMMON_PET
            || pet->getPetType() == HUNTER_PET);
    snapshot.Guid = pet->GetGUID();
    snapshot.Entry = pet->GetEntry();
    snapshot.FamilyId = pet->GetCreatureTemplate()
        ? uint32(pet->GetCreatureTemplate()->family) : 0;
    snapshot.PetType = uint32(pet->getPetType());
    snapshot.CreatedBySpellId = pet->GetUInt32Value(UNIT_CREATED_BY_SPELL);
    snapshot.Health = pet->GetHealth();
    snapshot.MaxHealth = pet->GetMaxHealth();
    Powers const powerType = pet->GetPowerType();
    snapshot.PowerType = uint32(powerType);
    snapshot.Power = pet->GetPower(powerType);
    snapshot.MaxPower = pet->GetMaxPower(powerType);
    for (auto const& [spellId, petSpell] : pet->m_spells)
        if (petSpell.state != PETSPELL_REMOVED)
            snapshot.Spellbook.push_back({ spellId, uint8(petSpell.active),
                uint8(petSpell.type) });
    std::sort(snapshot.Spellbook.begin(), snapshot.Spellbook.end(),
        [](OrdinaryPetSpellIdentity const& left,
            OrdinaryPetSpellIdentity const& right)
        {
            if (left.SpellId != right.SpellId)
                return left.SpellId < right.SpellId;
            if (left.Active != right.Active)
                return left.Active < right.Active;
            return left.Type < right.Type;
        });
    snapshot.SpellbookSha256 = OrdinaryPetSpellbookSha256(
        snapshot.Spellbook);
    snapshot.AutocastSpellIds.assign(
        pet->m_autospells.begin(), pet->m_autospells.end());
    std::sort(snapshot.AutocastSpellIds.begin(),
        snapshot.AutocastSpellIds.end());
    snapshot.AutocastSpellIds.erase(std::unique(
        snapshot.AutocastSpellIds.begin(), snapshot.AutocastSpellIds.end()),
        snapshot.AutocastSpellIds.end());
    return snapshot;
}

bool OrdinaryPersistentPetMatches(OrdinaryPetSetupSnapshot const& snapshot,
    uint32 expectedEntry, uint32 expectedFamilyId, uint32 expectedPetType,
    uint32 expectedPowerType, uint32 expectedCreatedBySpellId)
{
    return snapshot.Present && snapshot.InWorld && snapshot.Alive
        && snapshot.Owned && snapshot.Permanent
        && snapshot.Entry == expectedEntry
        && snapshot.FamilyId == expectedFamilyId
        && snapshot.PetType == expectedPetType
        && snapshot.PowerType == expectedPowerType
        && snapshot.CreatedBySpellId == expectedCreatedBySpellId
        && snapshot.Health > 0 && snapshot.MaxHealth > 0
        && snapshot.MaxPower > 0 && !snapshot.Spellbook.empty()
        && snapshot.SpellbookSha256.size() == 64;
}

}

void BotWorldPopulationMgr::Update(uint32 diff)
{
    if (!_runningCohortId.empty())
        SelectCohort(_runningCohortId);

    if (!Cohort().Active)
        return;

    Cohort().ElapsedMs += diff;
    RotateAutoRecordingWindowIfNeeded(diff);
    UpdatePendingHealCasts();
    EnsurePopulation();
    uint64 nowMs = NowMs();
    PublishEncounterBlackboard(nowMs);
    ReconcileNativeBattleResDecisions(nowMs);

    for (auto itr = Party().Bots.begin(); itr != Party().Bots.end();)
    {
        Player* loadedBot = GetLoadedBot(*itr);
        if (!loadedBot)
        {
            if (Cohort().Config.ValidationRouteEnable
                && (Cohort().Raid.ServerProvisioningComplete
                    || Cohort().Raid.BotActionsEnabled))
            {
                MarkValidationCohortViolation(*itr, nullptr,
                    "validation_active_member_unloaded");
                itr->LastDecisionResult = "validation_cohort_action_gate_closed";
                itr->LastDecisionReason = "validation_active_member_unloaded";
                ++itr;
                continue;
            }
            if (itr->SpawnedMs && nowMs - itr->SpawnedMs < 10000)
            {
                ++itr;
                continue;
            }

            ObjectGuid prunedGuid = itr->Guid;
            Cohort().LastPopulationFailureReason = "spawned_bot_not_loaded";
            TC_LOG_ERROR("server", "BotWorld active bot pruned bot=%s reason=spawned_bot_not_loaded spawn_source=%s age_ms=%llu",
                prunedGuid.ToString().c_str(), itr->SpawnSource.c_str(), static_cast<unsigned long long>(itr->SpawnedMs ? nowMs - itr->SpawnedMs : 0));
            FlushDecisionFingerprintMemory(*itr);
            BotRaidAreaAuthority::Clear(prunedGuid.GetRawValue());
            sBotMgr->RemoveWorldBot(prunedGuid);
            if (ReleaseBotGuid(prunedGuid.GetCounter()))
                CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", prunedGuid.GetCounter());
            Cohort().FailedSpawnGuids.insert(prunedGuid.GetCounter());
            itr = Party().Bots.erase(itr);
            Cohort().Metrics.ActiveBots = uint32(Party().Bots.size());
            continue;
        }

        if (!loadedBot->IsInWorld())
        {
            Cohort().LastPopulationFailureReason = "loaded_bot_not_in_world";
            if (Cohort().Config.ValidationRouteEnable)
            {
                if (TryReattachValidationBot(*itr, loadedBot, "population_update_loaded_not_in_world"))
                {
                    Cohort().LastPopulationFailureReason.clear();
                    UpdateBot(*itr, diff);
                    ++itr;
                    continue;
                }

                bool validationBotStillDeciding = Cohort().Config.ValidationRouteEnable && itr->SpawnedMs && nowMs - itr->SpawnedMs >= 30000
                    && itr->LastDecisionTickMs && nowMs - itr->LastDecisionTickMs < 15000;
                if (validationBotStillDeciding)
                {
                    if (!itr->LastNotInWorldInfoLogMs || nowMs - itr->LastNotInWorldInfoLogMs >= 5000)
                    {
                        TC_LOG_INFO("server", "BotWorld active bot respawn deferred bot=%s reason=loaded_bot_not_in_world_waiting_for_recent_decision suppressed=%u",
                            itr->Guid.ToString().c_str(), itr->SuppressedNotInWorldInfoLogs);
                        itr->LastNotInWorldInfoLogMs = nowMs;
                        itr->SuppressedNotInWorldInfoLogs = 0;
                    }
                    else
                        ++itr->SuppressedNotInWorldInfoLogs;
                    ++itr;
                    continue;
                }

                ObjectGuid prunedGuid = itr->Guid;
                MarkValidationCohortViolation(*itr, loadedBot, "validation_same_instance_reattach_failed");
                itr->LastDecisionResult = "loaded_bot_not_in_world";
                itr->LastDecisionReason = "validation_same_instance_reattach_failed";
                TC_LOG_ERROR("server", "BotWorld active bot removed bot=%s reason=loaded_bot_not_in_world diagnostic=validation_same_instance_reattach_failed spawn_source=%s age_ms=%llu",
                    prunedGuid.ToString().c_str(), itr->SpawnSource.c_str(), static_cast<unsigned long long>(itr->SpawnedMs ? nowMs - itr->SpawnedMs : 0));
                FlushDecisionFingerprintMemory(*itr);
                BotRaidAreaAuthority::Clear(prunedGuid.GetRawValue());
                sBotMgr->RemoveWorldBot(prunedGuid);
                Cohort().FailedSpawnGuids.erase(prunedGuid.GetCounter());
                Party().ValidationRouteFocusGuid.Clear();
                Party().ValidationRouteFocusEntry = 0;
                Party().ValidationRouteFocusMapId = 0;
                Party().ValidationRouteFocusX = 0.0f;
                Party().ValidationRouteFocusY = 0.0f;
                Party().ValidationRouteFocusZ = 0.0f;
                Party().ValidationRouteFocusSeenMs = 0;
                Party().ValidationRouteActivationApplied = false;
                itr = Party().Bots.erase(itr);
                Cohort().Metrics.ActiveBots = uint32(Party().Bots.size());
                continue;
            }
            ++itr;
            continue;
        }

        UpdateBot(*itr, diff);
        ++itr;
    }

    if (Cohort().CalibrationActive)
    {
        EnsureCalibrationPopulation();
        EnsureCalibrationCohortGroup();
        uint64 const calibrationNowMs = NowMs();
        if (Cohort().CalibrationWindowComplete && Cohort().CalibrationScoredEndedMs
            && calibrationNowMs >= Cohort().CalibrationScoredEndedMs
            && calibrationNowMs - Cohort().CalibrationScoredEndedMs <= 10000
            && (!Cohort().CalibrationLastPostWindowDrainMs
                || calibrationNowMs - Cohort().CalibrationLastPostWindowDrainMs >= 250))
            DrainCalibrationPostWindowEffects();
        uint32 expectedPopulation = Cohort().CalibrationMode == "healer_controlled_damage_300" ? 5
            : (Cohort().CalibrationMode == "tank_threat_300" ? 2 : 1);
        bool populationReady = Party().CalibrationBots.size() == expectedPopulation;
        for (WorldBotState const& calibrationState : Party().CalibrationBots)
        {
            Player* calibrationBot = GetLoadedBot(calibrationState);
            populationReady = populationReady && calibrationBot && calibrationBot->IsInWorld()
                && calibrationBot->IsAlive() && calibrationBot->GetGroup()
                && calibrationBot->GetGroup()->GetMembersCount() == expectedPopulation;
            bool const calibrationUnholyPresenceRequired =
                Cohort().CalibrationTargetSpec == "frost_death_knight"
                || Cohort().CalibrationTargetSpec == "unholy_death_knight";
            if (populationReady && calibrationBot
                && calibrationUnholyPresenceRequired)
                populationReady = calibrationState.RequiredPresenceSetupSpellId == 48265
                    && calibrationState.RequiredPresenceSetupAuraId == 48265
                    && calibrationState.RequiredPresenceSetupSpellKnown
                    && calibrationBot->HasSpell(48265)
                    && calibrationBot->HasAura(48265)
                    && calibrationState.PresenceSetupNativeCastSubmittedAtMs
                    && calibrationState.PresenceSetupAuraObservedAtMs
                        >= calibrationState.PresenceSetupNativeCastSubmittedAtMs;
            bool const calibrationPetRequired =
                Cohort().CalibrationTargetSpec == "affliction_warlock"
                || Cohort().CalibrationTargetSpec == "demonology_warlock"
                || Cohort().CalibrationTargetSpec == "unholy_death_knight";
            if (populationReady && calibrationBot && calibrationPetRequired)
            {
                WorldBotState::NativePersistentPetSetupReceipt const& petSetup =
                    calibrationState.PersistentPetSetup;
                bool const nativePetReady = petSetup.RequiredSummonSpellId
                    && petSetup.RequiredCreatedBySpellId
                    && petSetup.RequiredEntry && petSetup.SummonSpellKnown
                    && calibrationBot->HasSpell(petSetup.RequiredSummonSpellId)
                    && petSetup.NativeCastSubmittedAtMs
                    && petSetup.NativeCastFinishedSuccessfully
                    && petSetup.NativeCastFinishedAtMs
                        >= petSetup.NativeCastSubmittedAtMs
                    && petSetup.NativeCastObservedAtMs
                        >= petSetup.NativeCastFinishedAtMs
                    && OrdinaryPersistentPetMatches(
                        ObserveOrdinaryPetSetup(calibrationBot),
                        petSetup.RequiredEntry, petSetup.RequiredFamilyId,
                        petSetup.RequiredPetType, petSetup.RequiredPowerType,
                        petSetup.RequiredCreatedBySpellId);
                bool const preexistingAfflictionPetReady =
                    Cohort().CalibrationTargetSpec == "affliction_warlock"
                    && petSetup.RequiredSummonSpellId == 691
                    && petSetup.RequiredCreatedBySpellId == 691
                    && petSetup.RequiredEntry == ENTRY_FELHUNTER
                    && petSetup.SummonSpellKnown
                    && calibrationBot->HasSpell(petSetup.RequiredSummonSpellId)
                    && !petSetup.NativeCastSubmittedAtMs
                    && (!petSetup.PreScoreResummonRequestedAtMs
                        || petSetup.PreScoreResummonObservedAtMs)
                    && OrdinaryPersistentPetMatches(
                        ObserveOrdinaryPetSetup(calibrationBot),
                        petSetup.RequiredEntry, petSetup.RequiredFamilyId,
                        petSetup.RequiredPetType, petSetup.RequiredPowerType,
                        petSetup.RequiredCreatedBySpellId);
                populationReady = nativePetReady || preexistingAfflictionPetReady;
            }
            if (populationReady && calibrationBot
                && Cohort().CalibrationMode == "single_target_300")
            {
                using namespace BotCalibrationFixtureContractGenerated;
                SpecContract const* fixtureContract = FindSpec(
                    Cohort().CalibrationTargetSpec);
                if (fixtureContract && fixtureContract->PetResourceRequired)
                {
                    Pet* pet = calibrationBot->GetPet();
                    bool petResourceReady = pet
                        && fixtureContract->PowerOffset
                            + fixtureContract->PowerCount
                                <= PowerContracts.size();
                    for (uint32 index = 0;
                        petResourceReady && index < fixtureContract->PowerCount;
                        ++index)
                    {
                        PowerContract const& power = PowerContracts[
                            fixtureContract->PowerOffset + index];
                        if (std::string_view(power.UnitKind) != "pet")
                            continue;
                        Powers const powerType = Powers(power.PowerType);
                        uint32 const maximum = std::max<int32>(0,
                            pet->GetMaxPower(powerType));
                        uint32 const required = power.Maximum
                            ? maximum : power.ExactNativeValue;
                        petResourceReady = maximum
                            && pet->GetPowerType() == powerType
                            && uint32(std::max<int32>(0,
                                pet->GetPower(powerType))) == required;
                    }
                    // Pet resources are ordinary live actor state. Keep the
                    // warmup unpublished while normal out-of-combat regen
                    // reaches the exact simulator start contract; never refill
                    // the pet through fixture-only SetPower assistance.
                    populationReady = petResourceReady;
                }
            }
            bool const calibrationRoguePoisonRequired =
                Cohort().CalibrationTargetSpec == "assassination_rogue"
                || Cohort().CalibrationTargetSpec == "combat_rogue";
            if (!populationReady || !calibrationBot
                || !calibrationRoguePoisonRequired)
                continue;
            populationReady = calibrationState.RoguePoisonSetupRequired
                && IsNativePoisonSetupReady(calibrationBot,
                    calibrationState.RogueMainhandPoisonSetup)
                && IsNativePoisonSetupReady(calibrationBot,
                    calibrationState.RogueOffhandPoisonSetup);
        }
        if (!Cohort().CalibrationScoredStartedMs
            && !Cohort().CalibrationWindowComplete && populationReady
            && NowMs() - Cohort().CalibrationStartedMs >= 15000)
            ResetCalibrationScoredWindow();
        if (Cohort().CalibrationScoredStartedMs && !Cohort().CalibrationWindowComplete)
        {
            UpdateCalibrationTargetHealthSchedule(NowMs());
            UpdateCalibrationControlledDamage();
            if (NowMs() - Cohort().CalibrationScoredStartedMs >= 300000)
                CompleteCalibrationScoredWindow();
        }

        for (auto itr = Party().CalibrationBots.begin(); itr != Party().CalibrationBots.end();)
        {
            Player* bot = GetLoadedBot(*itr);
            if (!bot || !bot->IsInWorld())
            {
                if (itr->SpawnedMs && NowMs() - itr->SpawnedMs < 10000)
                {
                    ++itr;
                    continue;
                }
                ObjectGuid guid = itr->Guid;
                BotRaidAreaAuthority::Clear(guid.GetRawValue());
                sBotMgr->RemoveWorldBot(guid);
                if (ReleaseBotGuid(guid.GetCounter()))
                    CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", guid.GetCounter());
                Cohort().CalibrationMetricsByGuid.erase(guid.GetCounter());
                itr = Party().CalibrationBots.erase(itr);
                continue;
            }
            UpdateCalibrationBot(*itr, diff);
            ++itr;
        }
    }

    MaybeAdvanceValidationRouteManifest();
}
