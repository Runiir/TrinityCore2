#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrScopeGuard.h"
#include "Bots/BotAdmissionIdentityGenerated.h"
#include "Bots/BotClassSpecActionProfile.h"

#include "CellImpl.h"
#include "CharmInfo.h"
#include "Creature.h"
#include "Cryptography/CryptoHash.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "GroupReference.h"
#include "Map.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <functional>
#include <limits>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace
{
constexpr uint32 CalibrationSingleTargetDurationMs = 300000;

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

bool UsesRangedAoeCalibrationLane(std::string const& spec)
{
    static constexpr std::array<char const*, 12> RangedAoeSpecs = {
        "balance_druid", "beast_mastery_hunter", "marksmanship_hunter", "survival_hunter",
        "shadow_priest", "elemental_shaman", "arcane_mage", "fire_mage", "frost_mage",
        "affliction_warlock", "demonology_warlock", "destruction_warlock"
    };
    return std::find(RangedAoeSpecs.begin(), RangedAoeSpecs.end(), spec) != RangedAoeSpecs.end();
}

struct HunterPetIdentitySnapshot
{
    uint32 PetId = 0;
    uint32 PetEntry = 0;
    std::vector<std::pair<uint32, uint8>> Spellbook;
    std::string SpellbookSha256;
    std::vector<uint32> AutocastSpellIds;
};

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

}

void BotWorldPopulationMgr::UpdateCalibrationBot(WorldBotState& state, uint32 diff)
{
    Player* bot = GetBot(state);
    CalibrationMetrics& metrics =
        Cohort().CalibrationMetricsByGuid[state.Guid.GetCounter()];
    uint64 const observationNowMs = NowMs();
    if (bot && Cohort().CalibrationScoredStartedMs
        && !Cohort().CalibrationWindowComplete
        && observationNowMs >= Cohort().CalibrationScoredStartedMs
        && observationNowMs - Cohort().CalibrationScoredStartedMs
            < CalibrationSingleTargetDurationMs)
        ObserveWillOfUnbinding(metrics, bot, observationNowMs);
    if (bot && !Cohort().CalibrationScoredStartedMs
        && !Cohort().CalibrationWindowComplete)
        ++metrics.WarmupUpdateOrdinal;
    BeginMeleeAutoAttackDecision(state, bot);
    BotWorldPopulationMgrInternal::ReconcileOnScopeExit meleeAutoAttackReconcile{
        [this, &state, bot]()
        {
            ResolveAndReconcileMeleeAutoAttack(state, bot);
        }};

    if (state.DecisionTimer > diff)
    {
        state.DecisionTimer -= diff;
        return;
    }
    uint32 const reactionTimeMs =
        BotClassSpecActionProfileStore::ReactionTimeMsForSpec(
            Cohort().CalibrationTargetSpec.c_str());
    bool const responsiveCalibration =
        Cohort().CalibrationMode == "healer_controlled_damage_300"
        || Cohort().CalibrationMode == "tank_threat_300"
        // Survival's Lock and Load cadence and instant focus dumps are evaluated
        // by the live controller more often than the generic world-bot interval.
        // Match that responsiveness so a ready shot is not delayed by 500 ms.
        || Cohort().CalibrationTargetSpec == "survival_hunter"
        // Match pinned fixtures that use a 100 ms reaction time. Hasted channels,
        // short Wrath casts, and sub-1.5-second GCDs otherwise lose a material
        // fraction of their throughput waiting for the generic polling tick.
        || reactionTimeMs == 100;
    bool const fixtureReactionTime = reactionTimeMs == 100;
    state.DecisionTimer = fixtureReactionTime ? reactionTimeMs : (responsiveCalibration ? 250 : 500);

    if (!bot || Cohort().CalibrationWindowComplete)
        return;

    bool const scored = Cohort().CalibrationScoredStartedMs
        && NowMs() >= Cohort().CalibrationScoredStartedMs
        && NowMs() - Cohort().CalibrationScoredStartedMs
            < CalibrationSingleTargetDurationMs;
    if (!scored)
    {
        metrics.WarmupProfileActionsSuppressed = true;
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Safety,
            BotActionArbitration::Priority::Terminal,
            "calibration_setup_only_warmup");
    }
    if (scored)
        ++metrics.TickCount;
    auto capturePetTimelineState = [bot](CalibrationMetrics::DecisionTimelineEntry& entry)
    {
        Pet* pet = bot ? bot->GetPet() : nullptr;
        if (!pet)
            return;

        entry.PetAlive = pet->IsAlive();
        entry.PetVictimGuid = pet->GetVictim()
            ? pet->GetVictim()->GetGUID().GetCounter() : 0;
        entry.PetAttacking = entry.PetAlive && pet->GetVictim() != nullptr;
        if (CharmInfo* charmInfo = pet->GetCharmInfo())
        {
            entry.PetCommandState = uint8(charmInfo->GetCommandState());
            entry.PetCommandAttack = charmInfo->IsCommandAttack();
        }
        if (Spell* current = pet->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            entry.PetCurrentGenericSpellId = current->GetSpellInfo()->Id;
        if (Spell* current = pet->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
            entry.PetCurrentChanneledSpellId = current->GetSpellInfo()->Id;
        if (Spell* current = pet->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL))
            entry.PetCurrentAutorepeatSpellId = current->GetSpellInfo()->Id;
    };
    if (!bot->IsAlive())
    {
        if (scored && !metrics.DeathRecorded)
        {
            ++metrics.DeathCount;
            metrics.DeathRecorded = true;
            if (metrics.DecisionTimeline.size() < 4096)
            {
                CalibrationMetrics::DecisionTimelineEntry entry;
                entry.ElapsedMs = NowMs() - Cohort().CalibrationScoredStartedMs;
                entry.Result = "dead";
                entry.Health = bot->GetHealth();
                entry.MaxHealth = bot->GetMaxHealth();
                entry.Mana = bot->GetPower(POWER_MANA);
                entry.MaxMana = bot->GetMaxPower(POWER_MANA);
                if (Spell* current = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                    entry.CurrentGenericSpellId = current->GetSpellInfo()->Id;
                if (Spell* current = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                    entry.CurrentChanneledSpellId = current->GetSpellInfo()->Id;
                if (Pet* pet = bot->GetPet())
                {
                    entry.PetHealth = pet->GetHealth();
                    entry.PetMaxHealth = pet->GetMaxHealth();
                }
                capturePetTimelineState(entry);
                entry.Alive = false;
                metrics.DecisionTimeline.push_back(std::move(entry));
            }
        }
        return;
    }
    if (scored)
    {
        if (Cohort().CalibrationMode == "single_target_300"
            && !metrics.InitialGearManifestSha256.empty())
        {
            uint64 const gearObservedAtMs = NowMs();
            std::vector<RaidRosterItemIdentity> observedGear;
            std::string observedGearSha256;
            ++metrics.GearIdentitySampleCount;
            if (!ObserveEquippedGearIdentity(bot, observedGear,
                    observedGearSha256)
                || observedGearSha256
                    != metrics.InitialGearManifestSha256)
                ++metrics.GearIdentityMismatchSampleCount;
            metrics.LastObservedGearManifestSha256 =
                observedGearSha256;
            if (metrics.LastGearIdentityObservedAtMs)
                metrics.MaximumGearIdentityObservationGapMs = std::max(
                    metrics.MaximumGearIdentityObservationGapMs,
                    gearObservedAtMs - metrics.LastGearIdentityObservedAtMs);
            metrics.LastGearIdentityObservedAtMs = gearObservedAtMs;
        }
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
        {
            ++metrics.RequiredPetReadyTicks;
            ++metrics.PetSetupReadySampleCount;
        }
        uint64 const petObservedAtMs = NowMs();
        if (!metrics.FirstPetSetupObservedAtMs)
            metrics.FirstPetSetupObservedAtMs = petObservedAtMs;
        if (metrics.LastPetSetupObservedAtMs)
            metrics.MaximumPetSetupObservationGapMs = std::max(
                metrics.MaximumPetSetupObservationGapMs,
                petObservedAtMs - metrics.LastPetSetupObservedAtMs);
        metrics.LastPetSetupObservedAtMs = petObservedAtMs;
        metrics.MinimumHealthRatio = std::min(metrics.MinimumHealthRatio, UnitHealthPct(bot));
        if (bot->GetPowerType() != POWER_MANA && bot->GetMaxPower(bot->GetPowerType()))
        {
            Powers const powerType = bot->GetPowerType();
            float powerRatio = float(bot->GetPower(powerType)) / float(bot->GetMaxPower(powerType));
            if (powerRatio >= 0.95f)
                ++metrics.ResourceCappedTicks;
            // Rage and runic power are generated from combat and intentionally
            // spent toward zero. Low stored power is not starvation for these
            // spend-up resources; lost damage and action uptime remain gated
            // independently.
            if (powerType != POWER_RAGE && powerType != POWER_RUNIC_POWER && powerRatio <= 0.05f)
                ++metrics.ResourceStarvedTicks;
        }
        else if (bot->GetMaxPower(POWER_MANA)
            && float(bot->GetPower(POWER_MANA)) / float(bot->GetMaxPower(POWER_MANA)) <= 0.05f)
            ++metrics.ResourceStarvedTicks;

        if (Cohort().CalibrationTargetSpec == "shadow_priest")
        {
            if (bot->HasAura(77486))
                ++metrics.ShadowOrbPowerActiveTicks;
            if (Aura const* shadowOrb = bot->GetAura(77487))
            {
                ++metrics.ShadowOrbActiveTicks;
                metrics.MaximumShadowOrbStacks = std::max<uint8>(metrics.MaximumShadowOrbStacks, shadowOrb->GetStackAmount());
            }
            if (bot->HasAura(95799))
                ++metrics.EmpoweredShadowActiveTicks;
        }
    }

    std::string const role = GetDungeonRole(bot);
    if (role == "healer")
    {
        if (TryEnsurePersistentCombatSetup(state, bot, nullptr))
            return;

        uint32 const controlledDispelAura = ControlledDispelAuraForHealer(bot);
        bool anyDispelAura = false;
        if (Group* group = bot->GetGroup())
            for (GroupReference* itr = group->GetFirstMember(); itr; itr = itr->next())
                if (Player* member = itr->GetSource())
                    anyDispelAura = anyDispelAura || member->HasAura(controlledDispelAura);
        if (metrics.DispelAttempts && !anyDispelAura && !metrics.DispelSuccesses)
            metrics.DispelSuccesses = 1;
        bool demand = anyDispelAura || !metrics.LastControlledDamageMsByTarget.empty();
        if (Group* group = bot->GetGroup())
            for (GroupReference* itr = group->GetFirstMember(); itr; itr = itr->next())
                if (Player* member = itr->GetSource())
                    demand = demand || (member->IsAlive() && UnitHealthPct(member) <= 0.94f);
        bool const acted = UpdateCalibrationHealer(state, bot);
        if (scored)
        {
            ++metrics.ActiveTicks;
            if (demand)
            {
                ++metrics.DemandTicks;
                if (!acted)
                    ++metrics.IdleUnderDemandTicks;
            }
        }
        return;
    }
    if (Cohort().CalibrationMode == "healer_controlled_damage_300")
        return;

    std::vector<Creature*> dummies;
    bool const isolatedSingleTarget = Cohort().CalibrationMode == "single_target_300";
    if (isolatedSingleTarget)
    {
        Creature* fixtureTarget = bot->GetMap() ? bot->GetMap()->GetCreature(
            Cohort().CalibrationFixtureTargetGuid) : nullptr;
        if (fixtureTarget && fixtureTarget->IsAlive()
            && IsTrainingDummy(fixtureTarget)
            && bot->IsValidAttackTarget(fixtureTarget))
        {
            dummies.push_back(fixtureTarget);
            if (scored && Cohort().CalibrationTargetSpec == "affliction_warlock")
                ObserveAfflictionCalibrationModifiers(metrics, bot, fixtureTarget);
        }
    }
    else
    {
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 80.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 80.0f);
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (creature && creature->IsAlive() && IsTrainingDummy(creature)
                && bot->IsValidAttackTarget(creature))
                dummies.push_back(creature);
        }
    }
    std::sort(dummies.begin(), dummies.end(), [bot](Creature const* left, Creature const* right)
    {
        float leftDistance = bot->GetExactDist(left);
        float rightDistance = bot->GetExactDist(right);
        if (std::fabs(leftDistance - rightDistance) > 0.01f)
            return leftDistance < rightDistance;
        return left->GetGUID() < right->GetGUID();
    });
    if (dummies.empty())
    {
        if (isolatedSingleTarget)
        {
            Cohort().LastPopulationFailureReason =
                "calibration_isolated_target_lost";
            Cohort().CalibrationFailureReason =
                Cohort().LastPopulationFailureReason;
            if (Cohort().CalibrationScoredStartedMs)
                CompleteCalibrationScoredWindow();
            else
                Cohort().CalibrationWindowComplete = true;
        }
        return;
    }

    // Melee profiles always use the nearest dummy. Ranged AoE profiles instead
    // anchor target-centered effects on the densest stable part of the cluster;
    // using the lane's nearest edge dummy made effects such as Mind Sear reach
    // only two of the other seven qualification targets.
    Unit* target = dummies.front();
    if (Cohort().CalibrationAoePhase && UsesRangedAoeCalibrationLane(Cohort().CalibrationTargetSpec))
    {
        static constexpr float AoeAnchorRadius = 10.0f;
        auto density = [&dummies](Creature const* candidate)
        {
            return std::count_if(dummies.begin(), dummies.end(), [candidate](Creature const* other)
            {
                return candidate->GetExactDist(other) <= AoeAnchorRadius;
            });
        };
        target = *std::min_element(dummies.begin(), dummies.end(), [bot, &density](Creature const* left, Creature const* right)
        {
            size_t const leftDensity = density(left);
            size_t const rightDensity = density(right);
            if (leftDensity != rightDensity)
                return leftDensity > rightDensity;
            float const leftDistance = bot->GetExactDist(left);
            float const rightDistance = bot->GetExactDist(right);
            if (std::fabs(leftDistance - rightDistance) > 0.01f)
                return leftDistance < rightDistance;
            return left->GetGUID() < right->GetGUID();
        });
    }
    if (Cohort().CalibrationMode == "tank_threat_300"
        && bot->GetGUID() == Cohort().CalibrationTargetGuid
        && !Cohort().CalibrationInterruptTargetGuid.IsEmpty())
    {
        auto interruptTarget = std::find_if(dummies.begin(), dummies.end(), [this](Creature const* dummy)
        {
            return dummy && dummy->GetGUID() == Cohort().CalibrationInterruptTargetGuid;
        });
        if (interruptTarget != dummies.end() && (*interruptTarget)->IsNonMeleeSpellCast(false))
            target = *interruptTarget;
        else
            Cohort().CalibrationInterruptTargetGuid.Clear();
    }
    uint32 hostileCount = Cohort().CalibrationAoePhase ? uint32(dummies.size()) : 1;

    if (scored)
    {
        BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::BuildForSpec(
            bot, role.c_str(), Cohort().CalibrationTargetSpec.c_str());
        std::vector<BotActionCandidate> candidates = BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile);
        for (BotActionCandidate const& candidate : candidates)
        {
            Unit* candidateTarget = candidate.Profile.TargetSelector == "self"
                ? static_cast<Unit*>(bot) : target;
            float const candidateTargetHealth = UnitHealthPct(candidateTarget);
            float const candidateSelfHealth = UnitHealthPct(bot);
            if (!candidate.RejectReason.empty()
                || candidate.Profile.MinEnemies > hostileCount
                || (candidate.Profile.MaxEnemies && hostileCount > candidate.Profile.MaxEnemies)
                || candidateTargetHealth < candidate.Profile.MinTargetHealthPct
                || candidateTargetHealth > candidate.Profile.MaxTargetHealthPct
                || !MeetsHostileTargetHealthGate(candidate.Profile, UnitHealthPct(target))
                || candidateSelfHealth < candidate.Profile.MinSelfHealthPct
                || candidateSelfHealth > candidate.Profile.MaxSelfHealthPct
                || (candidate.Profile.RequiresInterruptibleTarget && !target->IsNonMeleeSpellCast(false))
                || (candidate.Category == BotCombatActionCategory::Taunt
                    && (!target->GetVictim() || target->GetVictim() == bot))
                || candidate.Category == BotCombatActionCategory::HealFast
                || candidate.Category == BotCombatActionCategory::HealEfficient
                || candidate.Category == BotCombatActionCategory::HealAoe
                || candidate.Category == BotCombatActionCategory::DispelCleanse
                || candidate.Category == BotCombatActionCategory::ExternalDefensive
                || candidate.Category == BotCombatActionCategory::Buff)
                continue;
            metrics.ExpectedActionGroups.insert(BotCombatActionCatalog::ToString(candidate.Category));
        }
    }

    if (EnsureCalibrationSelfProvidedConsumables(state, bot, target, scored))
        return;
    auto [referenceBuffsReady, referenceTargetDebuffsReady] = ApplyCalibrationReferenceConditions(bot, target);
    metrics.ReferenceBuffsReady = referenceBuffsReady;
    metrics.ReferenceReplenishmentObserved = metrics.ReferenceReplenishmentObserved || bot->HasAura(57669);
    metrics.ReferenceTargetDebuffsReady = referenceTargetDebuffsReady;
    metrics.ReferenceHeroismWindowObserved = metrics.ReferenceHeroismWindowObserved || bot->HasAura(2825);

    if (scored && Cohort().CalibrationMode == "single_target_300")
    {
        uint64 const externalObservedAtMs = NowMs();
        bool const heroismObserved = bot->HasAura(2825);
        bool const powerInfusionObserved = bot->HasAura(10060);
        ++metrics.ExternalWindowSampleCount;
        if (!metrics.FirstExternalWindowObservedAtMs)
            metrics.FirstExternalWindowObservedAtMs = externalObservedAtMs;
        if (metrics.LastExternalWindowObservedAtMs)
            metrics.MaximumExternalWindowObservationGapMs = std::max(
                metrics.MaximumExternalWindowObservationGapMs,
                externalObservedAtMs
                    - metrics.LastExternalWindowObservedAtMs);
        metrics.LastExternalWindowObservedAtMs = externalObservedAtMs;
        if (heroismObserved)
            ++metrics.HeroismObservedActiveSamples;
        if (heroismObserved)
            ++metrics.HeroismMismatchSamples;
        if (powerInfusionObserved)
            ++metrics.PowerInfusionObservedActiveSamples;
        if (powerInfusionObserved)
            ++metrics.PowerInfusionMismatchSamples;
        if (bot->HasAura(85767))
            ++metrics.UnexpectedDarkIntentBaseSamples;
        if (bot->HasAura(85759))
            ++metrics.UnexpectedDarkIntentProcSamples;
        if (bot->HasAura(96230))
            ++metrics.UnexpectedSynapseSpringsSamples;
        ObserveCalibrationReferenceConditions(
            metrics, bot, target, externalObservedAtMs);
    }

    if (TryEnsurePersistentCombatSetup(state, bot, target,
        Cohort().CalibrationTargetSpec.c_str()))
        return;

    // Warmup exists only to let ordinary player setup casts, item uses, and
    // permanent pets settle. Profile combat actions, auto attacks, and damage
    // are suppressed until the controller publishes the scored timestamp.
    if (!scored)
    {
        return;
    }

    // Hunter pet autocast target selection does not reliably choose self-only
    // offensive cooldowns. Drive the two exact ferocity-pet cooldowns used by
    // the pinned fixture from the start of the scored window. Only stop after a
    // successful cast so one rejected cooldown cannot suppress the other.
    if (scored && bot->getClass() == CLASS_HUNTER)
    {
        if (Pet* pet = bot->GetPet(); pet && !pet->HasUnitState(UNIT_STATE_CASTING))
        {
            static constexpr std::array<uint32, 2> PetCooldowns = { 53434, 53401 }; // Call of the Wild, Rabid
            for (uint32 spellId : PetCooldowns)
            {
                SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
                if (!spellInfo || !pet->HasSpell(spellId) || !pet->GetSpellHistory()->IsReady(spellInfo))
                    continue;
                if (pet->CastSpell(pet, spellId, false) == SPELL_CAST_OK)
                    break;
            }
        }
    }

    if (scored && !metrics.WindowStartedMs)
        metrics.WindowStartedMs = Cohort().CalibrationScoredStartedMs;

    bool tankStanceActive = role != "tank";
    if (role == "tank")
    {
        switch (bot->getClass())
        {
            case CLASS_WARRIOR: tankStanceActive = bot->HasAura(71); break;
            case CLASS_PALADIN: tankStanceActive = bot->HasAura(25780); break;
            case CLASS_DEATH_KNIGHT: tankStanceActive = bot->HasAura(48263); break;
            case CLASS_DRUID: tankStanceActive = bot->HasAura(5487); break;
            default: tankStanceActive = false; break;
        }
        if (scored && tankStanceActive)
        {
            ++metrics.StanceFormActiveTicks;
            ++metrics.ThreatAuraActiveTicks;
        }

        // The class tank stance/presence/form supplies continuous baseline
        // mitigation; class cooldown auras add active coverage on top of it.
        // Defensive action execution is recorded independently below.
        bool mitigationActive = tankStanceActive;
        switch (bot->getClass())
        {
            case CLASS_WARRIOR:
                mitigationActive = mitigationActive || bot->HasAura(2565) || bot->HasAura(871) || bot->HasAura(12975);
                break;
            case CLASS_PALADIN:
                mitigationActive = mitigationActive || bot->HasAura(498) || bot->HasAura(31850) || bot->HasAura(86150);
                break;
            case CLASS_DEATH_KNIGHT:
                mitigationActive = mitigationActive || bot->HasAura(49222) || bot->HasAura(55233) || bot->HasAura(48792);
                break;
            case CLASS_DRUID:
                mitigationActive = mitigationActive || bot->HasAura(22812) || bot->HasAura(61336) || bot->HasAura(22842);
                break;
            default:
                break;
        }
        if (scored && mitigationActive)
            ++metrics.MitigationCoveredTicks;
    }

    // Keep the tank's normal threat stance active. Other rotational choices go
    // through the same profile resolver and executor used in the dungeon.
    if (bot->getClass() == CLASS_PALADIN && std::string(GetDungeonRole(bot)) == "tank"
        && bot->HasSpell(25780) && !bot->HasAura(25780) && !bot->HasUnitState(UNIT_STATE_CASTING))
    {
        bot->CastSpell(bot, 25780, false);
        return;
    }

    bool const interruptOpportunity = target->IsNonMeleeSpellCast(false);
    bool const strictSingleTarget = Cohort().CalibrationMode == "single_target_300";
    // The single-target fixture is an isolated primary target and acceptance
    // independently requires one damaged target plus zero off-target damage.
    // Preserve player rotations that legally use an area-capable spell on one
    // target (for example Shadowflame or Howling Blast); only multidot target
    // selection remains disabled in this mode.
    bool const forbidArea = false;
    bool const allowMultidot = !strictSingleTarget;
    ResolvedCombatAction action = ResolveProfileCombatAction(
        bot, target, hostileCount, Cohort().CalibrationAoePhase, 0, false,
        false, forbidArea, allowMultidot, false, false,
        Cohort().CalibrationTargetSpec.c_str());
    auto actionCategory = Party().LastActionCategoryByBot.find(bot->GetGUID().GetCounter());
    std::string const actionGroup = actionCategory != Party().LastActionCategoryByBot.end()
        ? actionCategory->second : action.DebugName;
    float distance = bot->GetExactDist(target);
    if ((action.MinRange > 0.0f && distance < action.MinRange)
        || (action.MaxRange > 0.0f && distance > std::max(5.0f, action.MaxRange - 0.25f))
        || !bot->IsWithinLOSInMap(target))
    {
        if (scored)
        {
            ++metrics.MovementRangeLossTicks;
            if (metrics.DecisionTimeline.size() < 4096)
            {
                CalibrationMetrics::DecisionTimelineEntry entry;
                entry.ElapsedMs = NowMs() - Cohort().CalibrationScoredStartedMs;
                entry.SpellId = action.SpellId;
                entry.Result = "movement_range";
                entry.Health = bot->GetHealth();
                entry.MaxHealth = bot->GetMaxHealth();
                entry.Mana = bot->GetPower(POWER_MANA);
                entry.MaxMana = bot->GetMaxPower(POWER_MANA);
                if (Spell* current = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                    entry.CurrentGenericSpellId = current->GetSpellInfo()->Id;
                if (Spell* current = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                    entry.CurrentChanneledSpellId = current->GetSpellInfo()->Id;
                if (Pet* pet = bot->GetPet())
                {
                    entry.PetHealth = pet->GetHealth();
                    entry.PetMaxHealth = pet->GetMaxHealth();
                }
                capturePetTimelineState(entry);
                entry.TargetDistance = distance;
                entry.Alive = true;
                metrics.DecisionTimeline.push_back(std::move(entry));
            }
        }
        MoveBotToProfileRange(state, bot, target, &action);
        return;
    }

    BotActionResult result = ExecuteProfileCombatAction(
        &state, bot, target, &action, hostileCount,
        Cohort().CalibrationAoePhase, 0, false, false,
        forbidArea, allowMultidot);
    if (scored)
    {
        ++metrics.ActiveTicks;
        ++metrics.ResultCounts[ToString(result)];
        if (result == BotActionResult::CastFailed && !state.LastCombatAttempt.Reason.empty())
            ++metrics.ResultCounts[std::string("cast_failed:") + state.LastCombatAttempt.Reason];
        if (action.Valid)
        {
            metrics.ActionGroups.insert(actionGroup.empty() ? action.Type : actionGroup);
            if (action.SpellId)
                ++metrics.ActionAttempts[action.SpellId];
            if (result == BotActionResult::Ok
                && (actionGroup == "defensive" || actionGroup == "external_defensive"))
                ++metrics.DefensiveActionCount;
            if (result == BotActionResult::Ok && actionGroup == "interrupt" && interruptOpportunity)
                ++metrics.InterruptSuccesses;
        }
        if (result != BotActionResult::Casting && result != BotActionResult::GlobalCooldown && result != BotActionResult::NoAction)
        {
            ++metrics.Attempts;
            if (result == BotActionResult::Ok)
                ++metrics.Successes;
        }
        if (metrics.DecisionTimeline.size() < 4096)
        {
            CalibrationMetrics::DecisionTimelineEntry entry;
            entry.ElapsedMs = NowMs() - Cohort().CalibrationScoredStartedMs;
            entry.SpellId = action.SpellId;
            entry.Result = ToString(result);
            entry.Health = bot->GetHealth();
            entry.MaxHealth = bot->GetMaxHealth();
            entry.Mana = bot->GetPower(POWER_MANA);
            entry.MaxMana = bot->GetMaxPower(POWER_MANA);
            if (Spell* current = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL))
                entry.CurrentGenericSpellId = current->GetSpellInfo()->Id;
            if (Spell* current = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                entry.CurrentChanneledSpellId = current->GetSpellInfo()->Id;
            if (Pet* pet = bot->GetPet())
            {
                entry.PetHealth = pet->GetHealth();
                entry.PetMaxHealth = pet->GetMaxHealth();
            }
            capturePetTimelineState(entry);
            entry.TargetDistance = bot->GetExactDist(target);
            entry.Alive = bot->IsAlive();
            metrics.DecisionTimeline.push_back(std::move(entry));
        }
    }

    float threat = 0.0f;
    uint32 retainedHostiles = 0;
    bool healerExposed = false;
    uint64 const nowMs = NowMs();
    // Training dummies forcibly end each attacker combat reference after five
    // seconds without damage. Preserve the real threat-manager observation, but
    // also accept recent real damage within a normal tank AoE refresh cadence so
    // the dummy script cannot manufacture threat loss between valid refreshes.
    static constexpr uint64 TankThreatDamageRetentionMs = 15000;
    for (Creature* dummy : dummies)
    {
        float const dummyThreat = dummy->GetThreatManager().GetThreat(bot, true);
        threat += dummyThreat;
        auto const lastDamage = metrics.LastDamageMsByTarget.find(dummy->GetGUID().GetCounter());
        bool const recentlyDamaged = lastDamage != metrics.LastDamageMsByTarget.end()
            && nowMs >= lastDamage->second
            && nowMs - lastDamage->second <= TankThreatDamageRetentionMs;
        if (dummyThreat > 0.0f || recentlyDamaged)
            ++retainedHostiles;
        if (Player* victim = dummy->GetVictim() ? dummy->GetVictim()->ToPlayer() : nullptr)
            healerExposed = healerExposed || GetDungeonRole(victim) == std::string("healer");
    }
    if (metrics.ThreatBaseline < 0.0f)
        metrics.ThreatBaseline = threat;
    metrics.ThreatCurrent = threat;
    if (scored && role == "tank")
    {
        uint32 const requiredHostiles = Cohort().CalibrationMode == "tank_threat_300"
            ? std::min<uint32>(3, uint32(dummies.size())) : 1;
        bool const retained = retainedHostiles >= requiredHostiles;
        uint64 const elapsedMs = NowMs() - Cohort().CalibrationScoredStartedMs;
        ++metrics.ThreatSampleCount;
        if (retained)
            ++metrics.AllHostilesRetainedSamples;
        if (healerExposed)
            ++metrics.HealerExposureTicks;
        if (!metrics.SnapThreatChecks && elapsedMs >= 10000)
        {
            ++metrics.SnapThreatChecks;
            if (retained)
                ++metrics.SnapThreatSuccesses;
        }
        else if (elapsedMs > 10000)
        {
            ++metrics.AddThreatChecks;
            if (retained)
                ++metrics.AddThreatSuccesses;
        }
    }
}
