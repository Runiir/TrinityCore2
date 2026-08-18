#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotAdmissionIdentityGenerated.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "Cryptography/CryptoHash.h"
#include "GameTime.h"
#include "Map.h"
#include "Pet.h"
#include "Player.h"
#include "Util.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <sstream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace
{
static constexpr uint32 CalibrationSingleTargetDurationMs = 300000;

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

struct HunterPetIdentitySnapshot
{
    uint32 PetId = 0;
    uint32 PetEntry = 0;
    std::vector<std::pair<uint32, uint8>> Spellbook;
    std::string SpellbookSha256;
    std::vector<uint32> AutocastSpellIds;
};
BotAdmissionIdentityGenerated::Identity const* FindExpectedBotAdmissionIdentity(
    std::string const& classSpec)
{
    for (BotAdmissionIdentityGenerated::Identity const& identity :
        BotAdmissionIdentityGenerated::Identities)
        if (classSpec == identity.ClassSpec)
            return &identity;
    return nullptr;
}

bool ResolveExpectedHunterPetIdentity(std::string const& classSpec,
    uint32& petId, uint32& petEntry,
    std::vector<std::pair<uint32, uint8>>& spellbook)
{
    // Admission only observes this generated compile-time authority; it must
    // never repair, summon, or rewrite a pet after the cohort becomes active.
    BotAdmissionIdentityGenerated::Identity const* identity =
        FindExpectedBotAdmissionIdentity(classSpec);
    if (!identity || !identity->PetId || !identity->PetEntry
        || !identity->PetSpellCount
        || identity->PetSpellOffset + identity->PetSpellCount
            > BotAdmissionIdentityGenerated::PetSpells.size())
        return false;
    petId = identity->PetId;
    petEntry = identity->PetEntry;
    spellbook.clear();
    for (uint32 index = 0; index < identity->PetSpellCount; ++index)
    {
        BotAdmissionIdentityGenerated::PetSpellIdentity const& spell =
            BotAdmissionIdentityGenerated::PetSpells[
                identity->PetSpellOffset + index];
        spellbook.emplace_back(spell.SpellId, spell.Active);
    }
    return true;
}
std::string HunterPetSpellbookSha256(std::vector<std::pair<uint32, uint8>> const& spellbook)
{
    std::ostringstream canonical;
    for (size_t index = 0; index < spellbook.size(); ++index)
    {
        if (index)
            canonical << ';';
        canonical << spellbook[index].first << ':' << uint32(spellbook[index].second);
    }
    std::string digest = ByteArrayToHexStr(
        Trinity::Crypto::SHA256::GetDigestOf(canonical.str()));
    std::transform(digest.begin(), digest.end(), digest.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });
    return digest;
}

bool ObserveActiveOrdinaryHunterPet(Player const* bot, HunterPetIdentitySnapshot& snapshot)
{
    if (!bot || bot->getClass() != CLASS_HUNTER)
        return false;

    Pet* pet = bot->GetPet();
    PlayerPetData const* stored = const_cast<Player*>(bot)->GetPlayerPetDataCurrent();
    if (!pet || !stored || !stored->Active || stored->Type != HUNTER_PET
        || pet->getPetType() != HUNTER_PET || !pet->IsInWorld() || !pet->IsAlive()
        || !pet->IsPermanentPetFor(const_cast<Player*>(bot)) || pet->GetOwner() != bot
        || !pet->GetCharmInfo() || !stored->PetId || !stored->CreatureId
        || pet->GetCharmInfo()->GetPetNumber() != stored->PetId
        || pet->GetEntry() != stored->CreatureId)
        return false;

    snapshot.PetId = stored->PetId;
    snapshot.PetEntry = stored->CreatureId;
    // Family passives are deterministically derived from world DBC data and
    // are intentionally never persisted by Pet::_SaveSpells.  The pinned
    // provisioning identity is the mutable, persistable runtime spellbook;
    // including derived family passives would make an exact catalog check
    // depend on unrelated world-data implementation details.
    for (auto const& [spellId, petSpell] : pet->m_spells)
        if (petSpell.state != PETSPELL_REMOVED
            && petSpell.type != PETSPELL_FAMILY)
            snapshot.Spellbook.emplace_back(spellId, uint8(petSpell.active));
    std::sort(snapshot.Spellbook.begin(), snapshot.Spellbook.end());
    snapshot.SpellbookSha256 = HunterPetSpellbookSha256(snapshot.Spellbook);
    snapshot.AutocastSpellIds.assign(
        pet->m_autospells.begin(), pet->m_autospells.end());
    std::sort(snapshot.AutocastSpellIds.begin(),
        snapshot.AutocastSpellIds.end());
    snapshot.AutocastSpellIds.erase(std::unique(
        snapshot.AutocastSpellIds.begin(), snapshot.AutocastSpellIds.end()),
        snapshot.AutocastSpellIds.end());
    return true;
}

bool LoadedBotMatchesPinnedHunterPet(Player const* bot, std::string const& classSpec)
{
    if (!bot || bot->getClass() != CLASS_HUNTER)
        return true;

    uint32 expectedPetId = 0;
    uint32 expectedPetEntry = 0;
    std::vector<std::pair<uint32, uint8>> expectedSpellbook;
    std::vector<uint32> expectedAutocastSpellIds;
    HunterPetIdentitySnapshot observed;
    if (!ResolveExpectedHunterPetIdentity(classSpec, expectedPetId,
            expectedPetEntry, expectedSpellbook))
        return false;
    for (auto const& [spellId, active] : expectedSpellbook)
        if (active == ACT_ENABLED)
            expectedAutocastSpellIds.push_back(spellId);
    std::sort(expectedAutocastSpellIds.begin(),
        expectedAutocastSpellIds.end());
    return ObserveActiveOrdinaryHunterPet(bot, observed)
        && observed.PetId == expectedPetId
        && observed.PetEntry == expectedPetEntry
        && observed.Spellbook == expectedSpellbook
        && observed.SpellbookSha256 == HunterPetSpellbookSha256(expectedSpellbook)
        && observed.AutocastSpellIds == expectedAutocastSpellIds;
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

bool CalibrationPetObservationReady(
    OrdinaryPetSetupSnapshot const& snapshot, bool hunterPetRequired,
    uint32 expectedEntry, uint32 expectedFamilyId, uint32 expectedPetType,
    uint32 expectedPowerType, uint32 expectedCreatedBySpellId)
{
    if (expectedEntry)
        return OrdinaryPersistentPetMatches(snapshot, expectedEntry,
            expectedFamilyId, expectedPetType, expectedPowerType,
            expectedCreatedBySpellId);
    if (hunterPetRequired)
        return snapshot.Present && snapshot.InWorld && snapshot.Alive
            && snapshot.Owned && snapshot.Permanent && snapshot.Health > 0
            && snapshot.MaxHealth > 0 && snapshot.MaxPower > 0
            && !snapshot.Spellbook.empty()
            && snapshot.SpellbookSha256.size() == 64;
    return !snapshot.Present;
}
}

void BotWorldPopulationMgr::CompleteCalibrationScoredWindow()
{
    if (Cohort().CalibrationWindowComplete || !Cohort().CalibrationScoredStartedMs)
        return;
    // The acceptance interval is the exact half-open [t0,t0+300000) fixture
    // contract. Manager scheduling jitter may deliver this close call a few
    // milliseconds later, but must not silently lengthen the denominator or
    // any continuity-observation window.
    uint64 const scheduledEndedMs = Cohort().CalibrationScoredStartedMs
        + CalibrationSingleTargetDurationMs;
    uint64 const endedMs = std::min(NowMs(), scheduledEndedMs);
    Cohort().CalibrationScoredEndedMs = endedMs;
    Creature* scoredTarget = nullptr;
    for (WorldBotState const& state : Party().CalibrationBots)
        if (state.Guid == Cohort().CalibrationTargetGuid)
            if (Player* targetBot = GetLoadedBot(state);
                targetBot && targetBot->GetMap())
                scoredTarget = targetBot->GetMap()->GetCreature(
                    Cohort().CalibrationFixtureTargetGuid);
    if (scoredTarget)
    {
        ++Cohort().CalibrationFixtureTargetPassiveObservationSampleCount;
        if (scoredTarget->GetVictim())
            ++Cohort().CalibrationFixtureTargetVictimObservationSampleCount;
        if (!Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs)
            Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs = endedMs;
        if (Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs)
            Cohort().CalibrationFixtureTargetMaximumPassiveObservationGapMs =
                std::max(Cohort().CalibrationFixtureTargetMaximumPassiveObservationGapMs,
                    endedMs
                        - Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs);
        Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs = endedMs;
    }
    for (WorldBotState const& state : Party().CalibrationBots)
    {
        Player* bot = GetLoadedBot(state);
        auto metricsItr = Cohort().CalibrationMetricsByGuid.find(
            state.Guid.GetCounter());
        if (!bot || metricsItr == Cohort().CalibrationMetricsByGuid.end()
            || metricsItr->second.InitialGearManifestSha256.empty())
            continue;
        CalibrationMetrics& metrics = metricsItr->second;
        WorldBotState::NativePersistentPetSetupReceipt const& petSetup =
            state.PersistentPetSetup;
        OrdinaryPetSetupSnapshot const petObservation =
            ObserveOrdinaryPetSetup(bot);
        uint32 const observedPetGuid = petObservation.Guid.GetCounter();
        if (!metrics.PetSetupObservationSampleCount)
            metrics.FirstPetSetupObservedGuid = observedPetGuid;
        else if (observedPetGuid != metrics.FirstPetSetupObservedGuid)
            ++metrics.PetSetupGuidMismatchSampleCount;
        metrics.LastPetSetupObservedGuid = observedPetGuid;
        ++metrics.PetSetupObservationSampleCount;
        bool const hunterPetRequired =
            Cohort().CalibrationTargetSpec == "marksmanship_hunter"
            || Cohort().CalibrationTargetSpec == "survival_hunter";
        bool const hunterPetIdentityReady = !hunterPetRequired
            || LoadedBotMatchesPinnedHunterPet(bot,
                Cohort().CalibrationTargetSpec);
        if (!hunterPetIdentityReady)
            ++metrics.PetSetupIdentityMismatchSampleCount;
        bool const petReady = CalibrationPetObservationReady(petObservation,
            hunterPetRequired, petSetup.RequiredEntry,
            petSetup.RequiredFamilyId, petSetup.RequiredPetType,
            petSetup.RequiredPowerType, petSetup.RequiredCreatedBySpellId);
        bool const petExpected = hunterPetRequired || petSetup.RequiredEntry;
        bool const petGuidReady = observedPetGuid
                == metrics.FirstPetSetupObservedGuid
            && (petExpected ? observedPetGuid != 0 : observedPetGuid == 0);
        if (petReady && petGuidReady && hunterPetIdentityReady)
            ++metrics.PetSetupReadySampleCount;
        if (!metrics.FirstPetSetupObservedAtMs)
            metrics.FirstPetSetupObservedAtMs = endedMs;
        if (metrics.LastPetSetupObservedAtMs)
            metrics.MaximumPetSetupObservationGapMs = std::max(
                metrics.MaximumPetSetupObservationGapMs,
                endedMs - metrics.LastPetSetupObservedAtMs);
        metrics.LastPetSetupObservedAtMs = endedMs;

        ++metrics.ExternalWindowSampleCount;
        if (bot->HasAura(2825))
        {
            ++metrics.HeroismObservedActiveSamples;
            ++metrics.HeroismMismatchSamples;
        }
        if (bot->HasAura(10060))
        {
            ++metrics.PowerInfusionObservedActiveSamples;
            ++metrics.PowerInfusionMismatchSamples;
        }
        if (bot->HasAura(85767))
            ++metrics.UnexpectedDarkIntentBaseSamples;
        if (bot->HasAura(85759))
            ++metrics.UnexpectedDarkIntentProcSamples;
        if (bot->HasAura(96230))
            ++metrics.UnexpectedSynapseSpringsSamples;
        if (!metrics.FirstExternalWindowObservedAtMs)
            metrics.FirstExternalWindowObservedAtMs = endedMs;
        if (metrics.LastExternalWindowObservedAtMs)
            metrics.MaximumExternalWindowObservationGapMs = std::max(
                metrics.MaximumExternalWindowObservationGapMs,
                endedMs - metrics.LastExternalWindowObservedAtMs);
        metrics.LastExternalWindowObservedAtMs = endedMs;
        ObserveCalibrationReferenceConditions(
            metrics, bot, scoredTarget, endedMs);
        std::vector<RaidRosterItemIdentity> observedGear;
        std::string observedGearSha256;
        ++metrics.GearIdentitySampleCount;
        if (!ObserveEquippedGearIdentity(bot, observedGear,
                observedGearSha256)
            || observedGearSha256
                != metrics.InitialGearManifestSha256)
            ++metrics.GearIdentityMismatchSampleCount;
        metrics.LastObservedGearManifestSha256 = observedGearSha256;
        if (metrics.LastGearIdentityObservedAtMs)
            metrics.MaximumGearIdentityObservationGapMs = std::max(
                metrics.MaximumGearIdentityObservationGapMs,
                endedMs - metrics.LastGearIdentityObservedAtMs);
        metrics.LastGearIdentityObservedAtMs = endedMs;
    }
    Cohort().CalibrationWindowComplete = true;
    for (auto& [guid, metrics] : Cohort().CalibrationMetricsByGuid)
        metrics.WindowEndedMs = endedMs;
    DrainCalibrationPostWindowEffects();
    Cohort().CalibrationPreviousMetrics = Cohort().CalibrationMetricsByGuid;
    Cohort().CalibrationPreviousAoePhase = Cohort().CalibrationAoePhase;
    Cohort().CalibrationPreviousWindowValid = true;
    if (Cohort().CalibrationMode == "aoe_300")
    {
        Cohort().CalibrationBestAoeMetrics = Cohort().CalibrationMetricsByGuid;
        ++Cohort().CalibrationCompletedAoeWindows;
    }
    else
    {
        Cohort().CalibrationBestSingleMetrics = Cohort().CalibrationMetricsByGuid;
        ++Cohort().CalibrationCompletedSingleWindows;
    }
}
