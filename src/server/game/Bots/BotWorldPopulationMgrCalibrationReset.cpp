#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotAdmissionIdentityGenerated.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"
#include "Bots/BotClassSpecActionProfile.h"

#include "CharmInfo.h"
#include "CellImpl.h"
#include "Creature.h"
#include "Cryptography/CryptoHash.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Log.h"
#include "Pet.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <cmath>
#include <limits>
#include <sstream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace
{
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

void BotWorldPopulationMgr::ResetCalibrationScoredWindow()
{
    // This function is the calibration controller's final provisioning
    // boundary. Publish the scored start timestamp only after every resource,
    // target, and gear observation below has been read back successfully.
    bool const firstResetPass = Cohort().CalibrationResetId.empty();
    Cohort().CalibrationScoredStartedMs = 0;
    Cohort().CalibrationScoredEndedMs = 0;
    Cohort().CalibrationLastPostWindowDrainMs = 0;
    Cohort().CalibrationLastControlledEventSecond = std::numeric_limits<uint64>::max();
    Cohort().CalibrationCrossWindowEventCount = 0;
    Cohort().CalibrationExcludedBoundaryDamageEventCount = 0;
    Cohort().CalibrationFixtureTargetPassiveObservationSampleCount = 0;
    Cohort().CalibrationFixtureTargetVictimObservationSampleCount = 0;
    Cohort().CalibrationFixtureTargetAttackEventCount = 0;
    Cohort().CalibrationFixtureTargetOriginatedDamageEventCount = 0;
    Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs = 0;
    Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs = 0;
    Cohort().CalibrationFixtureTargetMaximumPassiveObservationGapMs = 0;
    Cohort().CalibrationInterruptTargetGuid.Clear();
    Cohort().CalibrationCurrentDamagePhase.clear();
    Cohort().CalibrationResetId = Cohort().CalibrationTargetSpec + ":" + Cohort().CalibrationMode
        + ":seed-" + std::to_string(Cohort().CalibrationSeed);

    if (firstResetPass || !IsSelfProvidedCalibrationBaseline())
        for (WorldBotState& state : Party().CalibrationBots)
        {
            CalibrationMetrics& metrics =
                Cohort().CalibrationMetricsByGuid[state.Guid.GetCounter()];
            metrics = CalibrationMetrics();
            state.DecisionTimer = 0;
        }

    using namespace BotCalibrationFixtureContractGenerated;
    SpecContract const* fixtureContract = Cohort().CalibrationMode
            == "single_target_300"
        ? FindSpec(Cohort().CalibrationTargetSpec) : nullptr;
    if (Cohort().CalibrationMode == "single_target_300"
        && (!fixtureContract
            || !fixtureContract->PetRuntimeProjectionComplete))
    {
        Cohort().LastPopulationFailureReason = fixtureContract
            ? "calibration_pet_runtime_projection_incomplete"
            : "calibration_fixture_spec_contract_missing";
        Cohort().CalibrationFailureReason =
            Cohort().LastPopulationFailureReason;
        Cohort().CalibrationWindowComplete = true;
        return;
    }

    Creature* preScoreFixtureTarget = nullptr;
    if (Cohort().CalibrationMode == "single_target_300")
        for (WorldBotState const& state : Party().CalibrationBots)
            if (state.Guid == Cohort().CalibrationTargetGuid)
                if (Player* targetBot = GetLoadedBot(state);
                    targetBot && targetBot->GetMap())
                    preScoreFixtureTarget = targetBot->GetMap()->GetCreature(
                        Cohort().CalibrationFixtureTargetGuid);

    // Warmup is setup-only. Keep t=0 unpublished while any normal native
    // setup cast, item use, or pet summon is still pending.
    if (Cohort().CalibrationMode == "single_target_300")
        for (WorldBotState& state : Party().CalibrationBots)
            if (Player* bot = GetLoadedBot(state))
            {
                if (EnsureCalibrationSelfProvidedConsumables(
                        state, bot, preScoreFixtureTarget, false))
                    return;
                ApplyCalibrationReferenceConditions(
                    bot, preScoreFixtureTarget);
                if (TryEnsurePersistentCombatSetup(
                    state, bot, preScoreFixtureTarget,
                    Cohort().CalibrationTargetSpec.c_str()))
                    return;
            }

    for (WorldBotState& state : Party().CalibrationBots)
    {
        Player* bot = GetLoadedBot(state);
        CalibrationMetrics& metrics = Cohort().CalibrationMetricsByGuid[state.Guid.GetCounter()];
        state.DecisionTimer = 0;
        if (!bot)
            continue;
        // A self-provided pre-pot is submitted only after this reset. Never
        // repeat the reset afterward, because that would clear its native
        // potion cooldown and manufacture an immediate combat potion.
        if (IsSelfProvidedCalibrationBaseline()
            && metrics.PreScoreCooldownResetComplete)
            continue;
        bot->InterruptNonMeleeSpells(true);
        bot->GetSpellHistory()->ResetAllCooldowns();
        // Warmup Black Arrow can leave Lock and Load or its internal-cooldown
        // marker active even though the scored reset removes the originating
        // target aura. Clear both so the scored opener starts from one
        // deterministic proc state.
        if (Cohort().CalibrationTargetSpec == "survival_hunter")
        {
            bot->RemoveAurasDueToSpell(56453);
            bot->RemoveAurasDueToSpell(67544);
        }
        // Unholy Blight is an owner aura that continues emitting periodic damage
        // after its triggering Death Coil. Clear warmup carryover before scoring.
        bot->RemoveAurasDueToSpell(50536, bot->GetGUID(), 0, AuraRemoveFlags::ByCancel);
        bot->RemoveAllDynObjects();
        bot->RemoveAllGameObjects();
        bot->CombatStopWithPets(true);
        bot->SetFullHealth();
        if (Cohort().CalibrationMode == "single_target_300")
        {
            std::string const& spec = Cohort().CalibrationTargetSpec;
            using namespace BotCalibrationFixtureContractGenerated;
            SpecContract const* contract = FindSpec(spec);
            metrics.InitialResourceSourceContract = ContentSha256;
            auto addPower = [&metrics](Unit* unit, char const* unitKind,
                Powers power, char const* name, uint32 exactNativeValue,
                bool maximum)
            {
                uint32 const maxNative = unit
                    ? std::max<int32>(0, unit->GetMaxPower(power)) : 0;
                uint32 const expectedNative = maximum ? maxNative : exactNativeValue;
                // Player fixture resource initialization is server-owned and
                // non-certifying. A pet is already an active player-owned
                // actor, however, so its native post-summon resource must only
                // be observed here and must never be refilled by the fixture.
                if (unit && std::string_view(unitKind) != "pet")
                    unit->SetPower(power, int32(expectedNative));
                uint32 const observedNative = unit ? unit->GetPower(power) : 0;
                auto displayValue = [power](uint32 value)
                {
                    return power == POWER_RAGE || power == POWER_RUNIC_POWER
                        ? value / 10 : value;
                };
                CalibrationMetrics::InitialPowerObservation observation;
                observation.PowerType = uint8(power);
                observation.UnitKind = unitKind;
                observation.UnitGuid = unit
                    ? unit->GetGUID().GetCounter() : 0;
                observation.PowerName = name;
                observation.ExpectedNativeValue = expectedNative;
                observation.ExpectedDisplayValue = displayValue(expectedNative);
                observation.ObservedNativeValue = observedNative;
                observation.ObservedDisplayValue = displayValue(observedNative);
                observation.ObservedMaximumNativeValue = maxNative;
                observation.ExpectedMaximum = maximum;
                observation.MatchesContract = unit && maxNative
                    && observedNative == expectedNative
                    && (std::string_view(unitKind) != "pet"
                        || unit->GetPowerType() == power);
                metrics.InitialPowerObservations.push_back(std::move(observation));
            };

            if (contract && contract->PowerOffset + contract->PowerCount
                    <= PowerContracts.size())
            {
                for (uint32 index = 0; index < contract->PowerCount; ++index)
                {
                    PowerContract const& power =
                        PowerContracts[contract->PowerOffset + index];
                    Unit* unit = std::string_view(power.UnitKind) == "pet"
                        ? static_cast<Unit*>(bot->GetPet())
                        : static_cast<Unit*>(bot);
                    addPower(unit, power.UnitKind, Powers(power.PowerType),
                        power.Name, power.ExactNativeValue, power.Maximum);
                }
            }

            if (contract && contract->RunesReadyMask)
            {
                bot->InitRunes();
                metrics.InitialRunesRequired = true;
                metrics.InitialExpectedRuneReadyMask =
                    contract->RunesReadyMask;
                metrics.InitialObservedRuneReadyMask = bot->GetRunesState();
            }

            if (contract && contract->ComboPoints != 255)
            {
                bot->ClearComboPoints();
                metrics.InitialComboPointsRequired = true;
                metrics.InitialExpectedComboPoints = contract->ComboPoints;
                metrics.InitialObservedComboPoints = bot->GetComboPoints();
            }

            if (contract && contract->NeutralEclipse)
            {
                bot->RemoveAurasDueToSpell(48517);
                bot->RemoveAurasDueToSpell(48518);
                metrics.InitialNeutralEclipseRequired = true;
                metrics.InitialNeutralEclipseObserved =
                    !bot->HasAura(48517) && !bot->HasAura(48518)
                    && bot->GetPower(POWER_ECLIPSE) == 0;
            }

            bool const petResourceRequired = contract
                && contract->PetResourceRequired;
            metrics.InitialPetResourceRequired = petResourceRequired;
            metrics.InitialPetResourceObserved = !petResourceRequired
                || std::any_of(metrics.InitialPowerObservations.begin(),
                    metrics.InitialPowerObservations.end(),
                    [](CalibrationMetrics::InitialPowerObservation const& row)
                    {
                        return row.UnitKind == "pet"
                            && row.MatchesContract;
                    });

            metrics.InitialResourcesObservedAtMs = NowMs();
            metrics.InitialResourcesApplied = contract
                && !metrics.InitialPowerObservations.empty();
            metrics.InitialResourcesMatchContract = metrics.InitialResourcesApplied
                && std::all_of(metrics.InitialPowerObservations.begin(),
                    metrics.InitialPowerObservations.end(),
                    [](CalibrationMetrics::InitialPowerObservation const& row)
                    {
                        return row.MatchesContract;
                    })
                && (!metrics.InitialRunesRequired
                    || metrics.InitialObservedRuneReadyMask
                        == metrics.InitialExpectedRuneReadyMask)
                && (!metrics.InitialComboPointsRequired
                    || metrics.InitialObservedComboPoints
                        == metrics.InitialExpectedComboPoints)
                && (!metrics.InitialNeutralEclipseRequired
                    || metrics.InitialNeutralEclipseObserved)
                && (!metrics.InitialPetResourceRequired
                    || metrics.InitialPetResourceObserved);

            std::vector<RaidRosterItemIdentity> initialGear;
            if (!ObserveEquippedGearIdentity(bot, initialGear,
                metrics.InitialGearManifestSha256))
                metrics.InitialResourcesMatchContract = false;
            metrics.LastObservedGearManifestSha256 =
                metrics.InitialGearManifestSha256;
            // The provisioning identity is the comparison baseline. Scored
            // continuity sampling begins exactly at the published t=0 edge.
            metrics.GearIdentitySampleCount = 0;
            metrics.FirstGearIdentityObservedAtMs = 0;
            metrics.LastGearIdentityObservedAtMs = 0;
        }
        else
        {
            if (bot->GetMaxPower(POWER_MANA))
                bot->SetPower(POWER_MANA, bot->GetMaxPower(POWER_MANA));
            if (bot->getClass() == CLASS_WARLOCK
                && bot->GetMaxPower(POWER_SOUL_SHARDS))
                bot->SetPower(POWER_SOUL_SHARDS,
                    bot->GetMaxPower(POWER_SOUL_SHARDS));
            // Protection Warrior snap threat must not depend on the arbitrary
            // rage remaining after the discarded warmup.
            if (Cohort().CalibrationMode == "tank_threat_300"
                && Cohort().CalibrationTargetSpec == "protection_warrior"
                && bot->GetMaxPower(POWER_RAGE))
                bot->SetPower(POWER_RAGE, bot->GetMaxPower(POWER_RAGE));
        }

        std::vector<ObjectGuid> ownedCasterGuids = { bot->GetGUID() };
        std::vector<TempSummon*> temporarySummons;
        Pet* pet = bot->GetPet();
        if (pet)
        {
            ownedCasterGuids.push_back(pet->GetGUID());
            pet->CombatStop(true);
            pet->GetSpellHistory()->ResetAllCooldowns();
        }
        std::vector<Unit*> controlledUnits(bot->m_Controlled.begin(), bot->m_Controlled.end());
        for (Unit* controlled : controlledUnits)
        {
            if (!controlled || controlled == pet)
                continue;
            ownedCasterGuids.push_back(controlled->GetGUID());
            controlled->CombatStop(true);
            controlled->GetSpellHistory()->ResetAllCooldowns();
            if (TempSummon* summon = controlled->ToTempSummon())
                temporarySummons.push_back(summon);
        }

        std::vector<WorldObject*> nearbyObjects;
        Trinity::AllWorldObjectsInRange dummyCheck(bot, 80.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> dummySearcher(bot, nearbyObjects, dummyCheck);
        Cell::VisitAllObjects(bot, dummySearcher, 80.0f);
        for (WorldObject* object : nearbyObjects)
        {
            Creature* dummy = object ? object->ToCreature() : nullptr;
            if (!dummy || !IsTrainingDummy(dummy))
                continue;
            dummy->CombatStop(true);
            dummy->SetFullHealth();
            dummy->GetThreatManager().ClearAllThreat();
            dummy->RemoveOwnedAuras([&ownedCasterGuids](Aura const* aura)
            {
                return aura && aura->GetSpellInfo() && aura->GetSpellInfo()->Id != 1130
                    && std::find(ownedCasterGuids.begin(), ownedCasterGuids.end(),
                        aura->GetCasterGUID()) != ownedCasterGuids.end();
            }, AuraRemoveFlags::ByCancel);
        }
        for (TempSummon* summon : temporarySummons)
            if (summon && summon->IsInWorld())
                summon->UnSummon();
        if (IsSelfProvidedCalibrationBaseline())
            metrics.PreScoreCooldownResetComplete = true;
    }

    if (Cohort().CalibrationMode == "single_target_300")
    {
        Player* targetBot = nullptr;
        for (WorldBotState const& state : Party().CalibrationBots)
            if (state.Guid == Cohort().CalibrationTargetGuid)
            {
                targetBot = GetLoadedBot(state);
                break;
            }
        Creature* fixtureTarget = targetBot && targetBot->GetMap()
            ? targetBot->GetMap()->GetCreature(
                Cohort().CalibrationFixtureTargetGuid) : nullptr;
        float const observedTargetDistance = fixtureTarget && targetBot
            ? targetBot->GetExactDist(fixtureTarget) : 0.0f;
        bool const targetReady = fixtureTarget && targetBot
            && fixtureContract
            && fixtureTarget->getLevel()
                == Cohort().CalibrationFixtureExpectedTargetLevel
            && fixtureTarget->GetArmor()
                == Cohort().CalibrationFixtureExpectedTargetArmor
            && fixtureTarget->GetCreatureType()
                == Cohort().CalibrationFixtureExpectedTargetCreatureType
            && fixtureTarget->GetMaxHealth()
                == Cohort().CalibrationFixtureExpectedTargetMaxHealth
            && !fixtureTarget->IsInCombat()
            && !fixtureTarget->GetVictim()
            && observedTargetDistance
                >= fixtureContract->RuntimeMinimumDistanceYards
            && observedTargetDistance
                <= fixtureContract->RuntimeMaximumDistanceYards;
        if (!targetReady)
        {
            TC_LOG_ERROR("server",
                "BotWorld calibration target fidelity drift before scoring "
                "spec=%s fixture=%u bot=%u contract=%u level=%u/%u "
                "armor=%u/%u type=%u/%u max_health=%u/%u alive=%u "
                "combat=%u victim=%u distance=%.3f range=[%.3f,%.3f]",
                Cohort().CalibrationTargetSpec.c_str(),
                fixtureTarget ? fixtureTarget->GetGUID().GetCounter() : 0,
                targetBot ? targetBot->GetGUID().GetCounter() : 0,
                fixtureContract ? 1u : 0u,
                fixtureTarget ? uint32(fixtureTarget->getLevel()) : 0,
                Cohort().CalibrationFixtureExpectedTargetLevel,
                fixtureTarget ? fixtureTarget->GetArmor() : 0,
                Cohort().CalibrationFixtureExpectedTargetArmor,
                fixtureTarget ? uint32(fixtureTarget->GetCreatureType()) : 0,
                Cohort().CalibrationFixtureExpectedTargetCreatureType,
                fixtureTarget ? fixtureTarget->GetMaxHealth() : 0,
                Cohort().CalibrationFixtureExpectedTargetMaxHealth,
                fixtureTarget && fixtureTarget->IsAlive() ? 1u : 0u,
                fixtureTarget && fixtureTarget->IsInCombat() ? 1u : 0u,
                fixtureTarget && fixtureTarget->GetVictim() ? 1u : 0u,
                observedTargetDistance,
                fixtureContract
                    ? fixtureContract->RuntimeMinimumDistanceYards : 0.0f,
                fixtureContract
                    ? fixtureContract->RuntimeMaximumDistanceYards : 0.0f);
            Cohort().LastPopulationFailureReason =
                "calibration_target_fidelity_drift_before_scoring";
            Cohort().CalibrationFailureReason =
                Cohort().LastPopulationFailureReason;
            Cohort().CalibrationWindowComplete = true;
            return;
        }

        Cohort().CalibrationFixtureTargetObservedBeforeScoringAtMs = NowMs();
        Cohort().CalibrationFixtureBeforeScoringTargetLevel =
            fixtureTarget->getLevel();
        Cohort().CalibrationFixtureBeforeScoringTargetArmor =
            fixtureTarget->GetArmor();
        Cohort().CalibrationFixtureBeforeScoringTargetCreatureType =
            fixtureTarget->GetCreatureType();
        Cohort().CalibrationFixtureBeforeScoringTargetCreatureTypeMask =
            fixtureTarget->GetCreatureTypeMask();
        Cohort().CalibrationFixtureBeforeScoringTargetMaxHealth =
            fixtureTarget->GetMaxHealth();
        Cohort().CalibrationFixtureBeforeScoringTargetMapId =
            fixtureTarget->GetMapId();
        Cohort().CalibrationFixtureBeforeScoringTargetGuid =
            fixtureTarget->GetGUID();
        Cohort().CalibrationFixtureBeforeScoringTargetX =
            fixtureTarget->GetPositionX();
        Cohort().CalibrationFixtureBeforeScoringTargetY =
            fixtureTarget->GetPositionY();
        Cohort().CalibrationFixtureBeforeScoringTargetZ =
            fixtureTarget->GetPositionZ();
        Cohort().CalibrationFixtureBeforeScoringBotTargetDistance =
            observedTargetDistance;
        Cohort().CalibrationFixtureBeforeScoringTargetInCombat =
            fixtureTarget->IsInCombat();
        Cohort().CalibrationFixtureBeforeScoringTargetHasVictim =
            fixtureTarget->GetVictim() != nullptr;

        bool allPreScoreStateReady = fixtureContract
            && fixtureContract->SetupAuraOffset
                    + fixtureContract->SetupAuraCount
                <= BotCalibrationFixtureContractGenerated::RequiredSetupAuraSpellIds.size();
        for (WorldBotState& state : Party().CalibrationBots)
        {
            Player* bot = GetLoadedBot(state);
            CalibrationMetrics& metrics =
                Cohort().CalibrationMetricsByGuid[state.Guid.GetCounter()];
            if (!bot || !fixtureContract)
            {
                allPreScoreStateReady = false;
                continue;
            }

            auto [referenceBuffsReady, referenceTargetDebuffsReady] =
                ApplyCalibrationReferenceConditions(bot, fixtureTarget);

            static constexpr std::array<uint32, 11>
                SelfProvidedForbiddenPlayerAuras = {
                    53646, 79058, 24932, 2895, 8515, 8076, 82930,
                    57669, 20217, 79063, 79102,
                };
            static constexpr std::array<uint32, 4>
                SelfProvidedForbiddenTargetAuras = {
                    1490, 22959, 81326, 58567,
                };
            bool const selfProvidedExternalAurasAbsent =
                !IsSelfProvidedCalibrationBaseline()
                || std::none_of(SelfProvidedForbiddenPlayerAuras.begin(),
                    SelfProvidedForbiddenPlayerAuras.end(),
                    [bot](uint32 spellId) { return bot->HasAura(spellId); });
            bool const selfProvidedTargetAurasAbsent =
                !IsSelfProvidedCalibrationBaseline()
                || std::none_of(SelfProvidedForbiddenTargetAuras.begin(),
                    SelfProvidedForbiddenTargetAuras.end(),
                    [fixtureTarget](uint32 spellId)
                    {
                        return fixtureTarget->HasAura(spellId);
                    });
            bool const selfProvidedConsumablesReady =
                !IsSelfProvidedCalibrationBaseline()
                || (metrics.FlaskConsumable.NativeUseFinishedSuccessfully
                    && metrics.FlaskConsumable.SuccessfulUseCount >= 1
                    && metrics.FoodConsumable.NativeUseFinishedSuccessfully
                    && metrics.FoodConsumable.SuccessfulUseCount >= 1
                    && metrics.PrepotConsumable.NativeUseFinishedSuccessfully
                    && metrics.PrepotConsumable.SuccessfulUseCount >= 1
                    && metrics.CombatPotionConsumable.SuccessfulUseCount == 0
                    && bot->HasAura(fixtureContract->FlaskAuraSpellId)
                    && bot->HasAura(fixtureContract->FoodAuraSpellId));

            // The base v1 denominator has no temporal external cooldowns.
            // Observe their absence; never manufacture or strip them in the
            // fixture controller. A stale aura therefore fails closed.
            bool const temporalExternalsAbsent = !bot->HasAura(2825)
                && !bot->HasAura(10060) && !bot->HasAura(85767)
                && !bot->HasAura(85759) && !bot->HasAura(96230);
            static constexpr std::array<uint32, 3>
                ExternalBleedAuraSpellIds = { 16511, 33876, 46857 };
            bool const externalBleedAbsent = std::none_of(
                ExternalBleedAuraSpellIds.begin(),
                ExternalBleedAuraSpellIds.end(),
                [fixtureTarget](uint32 spellId)
                {
                    return fixtureTarget->HasAura(spellId);
                });

            bool setupAurasReady = true;
            for (uint32 index = 0;
                index < fixtureContract->SetupAuraCount; ++index)
                setupAurasReady = setupAurasReady && bot->HasAura(
                    BotCalibrationFixtureContractGenerated::RequiredSetupAuraSpellIds[
                        fixtureContract->SetupAuraOffset + index]);

            // Reset ordinary spell cooldowns after setup, then explicitly
            // clear every profile/global-cooldown category. ResetAllCooldowns
            // intentionally does not own SpellHistory::_globalCooldowns.
            bot->GetSpellHistory()->ResetAllCooldowns();
            BotClassSpecActionProfile const profile =
                BotClassSpecActionProfileStore::Build(
                    bot, GetDungeonRole(bot));
            for (BotActionProfileSpell const& action : profile.Spells)
                if (SpellInfo const* spellInfo =
                    sSpellMgr->GetSpellInfo(action.SpellId))
                    bot->GetSpellHistory()->CancelGlobalCooldown(spellInfo);
            bool playerGlobalCooldownClear = std::none_of(
                profile.Spells.begin(), profile.Spells.end(),
                [bot](BotActionProfileSpell const& action)
                {
                    SpellInfo const* spellInfo =
                        sSpellMgr->GetSpellInfo(action.SpellId);
                    return spellInfo && bot->GetSpellHistory()
                        ->HasGlobalCooldown(spellInfo);
                });

            bool petGlobalCooldownClear = true;
            if (Pet* pet = bot->GetPet())
            {
                pet->GetSpellHistory()->ResetAllCooldowns();
                for (auto const& [spellId, petSpell] : pet->m_spells)
                    if (petSpell.state != PETSPELL_REMOVED)
                        if (SpellInfo const* spellInfo =
                            sSpellMgr->GetSpellInfo(spellId))
                            pet->GetSpellHistory()->CancelGlobalCooldown(
                                spellInfo);
                for (auto const& [spellId, petSpell] : pet->m_spells)
                    if (petSpell.state != PETSPELL_REMOVED)
                        if (SpellInfo const* spellInfo =
                            sSpellMgr->GetSpellInfo(spellId);
                            spellInfo && pet->GetSpellHistory()
                                ->HasGlobalCooldown(spellInfo))
                            petGlobalCooldownClear = false;
            }

            metrics.PreScorePersistentSetupReady = setupAurasReady;
            metrics.PreScoreReferenceBuffsReady = referenceBuffsReady
                && (!fixtureContract->FlaskAuraSpellId
                    || bot->HasAura(fixtureContract->FlaskAuraSpellId))
                && (!fixtureContract->FoodAuraSpellId
                    || bot->HasAura(fixtureContract->FoodAuraSpellId))
                && selfProvidedConsumablesReady;
            metrics.PreScoreReferenceTargetDebuffsReady =
                referenceTargetDebuffsReady;
            metrics.PreScoreHeroismReady = false;
            metrics.PreScoreTemporalExternalsAbsent =
                temporalExternalsAbsent;
            metrics.PreScoreExternalBleedAbsent = externalBleedAbsent;
            metrics.PreScoreLastPotionItemId = bot->GetLastPotionId();
            metrics.PreScoreNoActiveCast =
                !bot->HasUnitState(UNIT_STATE_CASTING);
            metrics.PreScoreNoCombat = !bot->IsInCombat()
                && (!bot->GetPet() || !bot->GetPet()->IsInCombat());
            metrics.PreScoreGlobalCooldownClear =
                playerGlobalCooldownClear && petGlobalCooldownClear;
            metrics.PreScoreCooldownResetApplied = true;
            metrics.WarmupProfileActionsSuppressed = true;
            metrics.PreScoreStateObservedAtMs = NowMs();
            allPreScoreStateReady = allPreScoreStateReady
                && metrics.PreScorePersistentSetupReady
                && metrics.PreScoreReferenceBuffsReady
                && metrics.PreScoreReferenceTargetDebuffsReady
                && metrics.PreScoreTemporalExternalsAbsent
                && metrics.PreScoreExternalBleedAbsent
                && selfProvidedExternalAurasAbsent
                && selfProvidedTargetAurasAbsent
                && (IsSelfProvidedCalibrationBaseline()
                    ? selfProvidedConsumablesReady
                    : !metrics.PreScoreLastPotionItemId)
                && metrics.PreScoreNoActiveCast
                && metrics.PreScoreNoCombat
                && metrics.PreScoreGlobalCooldownClear;
        }

        bool const resourcesReady = std::all_of(
            Cohort().CalibrationMetricsByGuid.begin(),
            Cohort().CalibrationMetricsByGuid.end(), [](auto const& entry)
            {
                return entry.second.InitialResourcesMatchContract;
            });
        if (!resourcesReady)
        {
            Cohort().LastPopulationFailureReason =
                "calibration_initial_resource_contract_mismatch";
            Cohort().CalibrationFailureReason =
                Cohort().LastPopulationFailureReason;
            Cohort().CalibrationWindowComplete = true;
            return;
        }
        if (!allPreScoreStateReady)
        {
            Cohort().LastPopulationFailureReason =
                "calibration_pre_score_state_contract_mismatch";
            Cohort().CalibrationFailureReason =
                Cohort().LastPopulationFailureReason;
            Cohort().CalibrationWindowComplete = true;
            return;
        }
    }

    uint64 const startedMs = NowMs();
    Cohort().CalibrationScoredStartedMs = startedMs;
    for (auto& [guid, metrics] : Cohort().CalibrationMetricsByGuid)
        metrics.WindowStartedMs = startedMs;

    // Read both the passive target and any required permanent pet at the exact
    // published scoring edge. Periodic observations and the final close sample
    // prove that neither contract was satisfied only during provisioning.
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
        Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs = startedMs;
        Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs = startedMs;
    }
    for (WorldBotState const& state : Party().CalibrationBots)
    {
        auto metricsItr = Cohort().CalibrationMetricsByGuid.find(
            state.Guid.GetCounter());
        Player* bot = GetLoadedBot(state);
        if (!bot || metricsItr == Cohort().CalibrationMetricsByGuid.end())
            continue;
        CalibrationMetrics& metrics = metricsItr->second;
        ObserveCalibrationEffectiveStats(
            bot, startedMs, metrics.ScoringStartPlayerStats);
        ObserveCalibrationEffectiveStats(
            bot->GetPet(), startedMs, metrics.ScoringStartPetStats);
        if (!metrics.InitialGearManifestSha256.empty())
        {
            std::vector<RaidRosterItemIdentity> observedGear;
            std::string observedGearSha256;
            ++metrics.GearIdentitySampleCount;
            if (!ObserveEquippedGearIdentity(bot, observedGear,
                    observedGearSha256)
                || observedGearSha256
                    != metrics.InitialGearManifestSha256)
                ++metrics.GearIdentityMismatchSampleCount;
            metrics.LastObservedGearManifestSha256 = observedGearSha256;
            metrics.FirstGearIdentityObservedAtMs = startedMs;
            metrics.LastGearIdentityObservedAtMs = startedMs;
        }
        OrdinaryPetSetupSnapshot const petObservation =
            ObserveOrdinaryPetSetup(bot);
        uint32 const observedPetGuid = petObservation.Guid.GetCounter();
        metrics.FirstPetSetupObservedGuid = observedPetGuid;
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
        bool const petReady = CalibrationPetObservationReady(
            petObservation, hunterPetRequired,
            state.PersistentPetSetup.RequiredEntry,
            state.PersistentPetSetup.RequiredFamilyId,
            state.PersistentPetSetup.RequiredPetType,
            state.PersistentPetSetup.RequiredPowerType,
            state.PersistentPetSetup.RequiredCreatedBySpellId);
        bool const petExpected = hunterPetRequired
            || state.PersistentPetSetup.RequiredEntry;
        bool const petGuidReady = petExpected
            ? observedPetGuid != 0 : observedPetGuid == 0;
        if (petReady && petGuidReady && hunterPetIdentityReady)
            ++metrics.PetSetupReadySampleCount;
        metrics.FirstPetSetupObservedAtMs = startedMs;
        metrics.LastPetSetupObservedAtMs = startedMs;

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
        metrics.FirstExternalWindowObservedAtMs = startedMs;
        metrics.LastExternalWindowObservedAtMs = startedMs;
        ObserveCalibrationReferenceConditions(
            metrics, bot, scoredTarget, startedMs);
    }
}
