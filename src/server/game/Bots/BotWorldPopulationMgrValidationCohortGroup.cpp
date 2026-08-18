#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotAdmissionIdentityGenerated.h"

#include "CharmInfo.h"
#include "Cryptography/CryptoHash.h"
#include "DataStores/DBCStores.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupMgr.h"
#include "GroupReference.h"
#include "Map.h"
#include "MapManager.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "WorldPacket.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cctype>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace
{
struct HunterPetIdentitySnapshot
{
    uint32 PetId = 0;
    uint32 PetEntry = 0;
    std::vector<std::pair<uint32, uint8>> Spellbook;
    std::string SpellbookSha256;
    std::vector<uint32> AutocastSpellIds;
};

float Distance2d(float ax, float ay, float bx, float by)
{
    float const dx = ax - bx;
    float const dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
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
    auto const* identity = FindExpectedBotAdmissionIdentity(classSpec);
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
        auto const& spell = BotAdmissionIdentityGenerated::PetSpells[
            identity->PetSpellOffset + index];
        spellbook.emplace_back(spell.SpellId, spell.Active);
    }
    return true;
}

std::string HunterPetSpellbookSha256(
    std::vector<std::pair<uint32, uint8>> const& spellbook)
{
    std::ostringstream canonical;
    for (size_t index = 0; index < spellbook.size(); ++index)
    {
        if (index)
            canonical << ';';
        canonical << spellbook[index].first << ':'
                  << uint32(spellbook[index].second);
    }
    std::string digest = ByteArrayToHexStr(
        Trinity::Crypto::SHA256::GetDigestOf(canonical.str()));
    std::transform(digest.begin(), digest.end(), digest.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });
    return digest;
}

bool ObserveActiveOrdinaryHunterPet(Player const* bot,
    HunterPetIdentitySnapshot& snapshot)
{
    if (!bot || bot->getClass() != CLASS_HUNTER)
        return false;
    Pet* pet = bot->GetPet();
    PlayerPetData const* stored =
        const_cast<Player*>(bot)->GetPlayerPetDataCurrent();
    if (!pet || !stored || !stored->Active || stored->Type != HUNTER_PET
        || pet->getPetType() != HUNTER_PET || !pet->IsInWorld()
        || !pet->IsAlive()
        || !pet->IsPermanentPetFor(const_cast<Player*>(bot))
        || pet->GetOwner() != bot || !pet->GetCharmInfo()
        || !stored->PetId || !stored->CreatureId
        || pet->GetCharmInfo()->GetPetNumber() != stored->PetId
        || pet->GetEntry() != stored->CreatureId)
        return false;
    snapshot.PetId = stored->PetId;
    snapshot.PetEntry = stored->CreatureId;
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

bool LoadedBotMatchesPinnedHunterPet(Player const* bot,
    std::string const& classSpec)
{
    if (!bot || bot->getClass() != CLASS_HUNTER)
        return true;
    uint32 expectedPetId = 0;
    uint32 expectedPetEntry = 0;
    std::vector<std::pair<uint32, uint8>> expectedSpellbook;
    if (!ResolveExpectedHunterPetIdentity(classSpec, expectedPetId,
            expectedPetEntry, expectedSpellbook))
        return false;
    std::vector<uint32> expectedAutocastSpellIds;
    for (auto const& [spellId, active] : expectedSpellbook)
        if (active == ACT_ENABLED)
            expectedAutocastSpellIds.push_back(spellId);
    std::sort(expectedAutocastSpellIds.begin(), expectedAutocastSpellIds.end());
    HunterPetIdentitySnapshot observed;
    return ObserveActiveOrdinaryHunterPet(bot, observed)
        && observed.PetId == expectedPetId
        && observed.PetEntry == expectedPetEntry
        && observed.Spellbook == expectedSpellbook
        && observed.SpellbookSha256 == HunterPetSpellbookSha256(expectedSpellbook)
        && observed.AutocastSpellIds == expectedAutocastSpellIds;
}

bool ResolveExpectedBotGearIdentity(std::string const& classSpec,
    std::string& gearProfileId, std::string& gearManifestSha256)
{
    auto const* identity = FindExpectedBotAdmissionIdentity(classSpec);
    if (!identity)
        return false;
    gearProfileId = identity->GearProfileId;
    gearManifestSha256 = identity->GearManifestSha256;
    return !gearProfileId.empty() && gearManifestSha256.size() == 64;
}
}

void BotWorldPopulationMgr::EnsureValidationCohortGroup()
{
    if (!Cohort().Config.ValidationRouteEnable || Party().Bots.empty())
        return;
    bool const activeObservationOnly = Cohort().ValidationAdmission == ValidationAdmissionPhase::Active
        || Cohort().Raid.BotActionsEnabled;

    std::vector<Player*> members;
    members.reserve(Party().Bots.size());
    for (WorldBotState const& state : Party().Bots)
    {
        Player* bot = GetLoadedBot(state);
        if (!bot)
            continue;

        if (bot->IsInWorld())
        {
            members.push_back(bot);
            continue;
        }

        // An admitted validation raid must keep observing the exact native
        // recovery transition while a corpse-bound worldport is in flight.
        // Omitting that member here freezes RaidRuntime at the pre-release
        // snapshot; the subsequent re-entry cannot prove release/runback.
        // Include only the two independently-authorized native worldports.
        if (state.ValidationCohortLocked && Cohort().Config.ValidationRouteEnable
            && (IsNativeReleasedGhostWorldport(state, bot)
                || IsNativeValidationRunbackWorldport(state, bot)))
            members.push_back(bot);
    }

    // Admission is not a one-shot latch. Once actions have been enabled,
    // revalidate the complete native group and immutable difficulty/instance
    // identity before every decision pass. Partial deaths and the two typed
    // corpse-recovery transits remain valid; roster, group, difficulty, or
    // unexplained worldport drift fails the whole attempt closed.
    if (activeObservationOnly)
    {
        RaidRuntime const& admission = Cohort().Raid;
        WorldBotState* invalidState = nullptr;
        Player* invalidBot = nullptr;
        char const* invalidReason = nullptr;
        auto invalidate = [&](WorldBotState& state, Player* bot, char const* reason)
        {
            if (!invalidReason)
            {
                invalidState = &state;
                invalidBot = bot;
                invalidReason = reason;
            }
        };

        if (!admission.ExpectedSize || Party().Bots.size() != admission.ExpectedSize)
            invalidate(Party().Bots.front(), GetLoadedBot(Party().Bots.front()),
                "validation_active_roster_size_drift");

        Group* admittedGroup = nullptr;
        std::set<ObjectGuid> expectedGuids;
        for (WorldBotState& state : Party().Bots)
        {
            Player* bot = GetLoadedBot(state);
            expectedGuids.insert(state.Guid);
            if (!bot || !state.ServerProvisioned || !state.ValidationCohortLocked)
            {
                invalidate(state, bot, "validation_active_member_identity_missing");
                continue;
            }

            Group* group = bot->GetGroup();
            if (!group || group->GetGUID() != state.ValidationCohortGroupGuid
                || group->GetLeaderGUID() != state.ValidationCohortLeaderGuid
                || group->GetGUID() != admission.GroupGuid
                || group->GetLeaderGUID() != admission.LeaderGuid)
            {
                invalidate(state, bot, "validation_active_group_identity_drift");
                continue;
            }
            if (!admittedGroup)
                admittedGroup = group;
            else if (admittedGroup != group)
                invalidate(state, bot, "validation_active_group_split");

            Difficulty const memberDifficulty = admission.RaidInstance
                ? bot->GetRaidDifficulty() : bot->GetDungeonDifficulty();
            Difficulty const groupDifficulty = admission.RaidInstance
                ? group->GetRaidDifficulty() : group->GetDungeonDifficulty();
            if (uint8(memberDifficulty) != admission.ExpectedDifficulty
                || uint8(groupDifficulty) != admission.ExpectedDifficulty)
                invalidate(state, bot, "validation_active_difficulty_drift");

            if (!bot->IsInWorld())
            {
                if (!IsNativeReleasedGhostWorldport(state, bot)
                    && !IsNativeValidationRunbackWorldport(state, bot))
                    invalidate(state, bot, "validation_active_untyped_worldport");
                continue;
            }

            if (!IsValidationCohortMemberInOriginalInstance(state, bot))
            {
                invalidate(state, bot, "validation_active_instance_drift");
                continue;
            }

            bool const inOriginalInstance = bot->GetMapId() == state.ValidationCohortMapId
                && bot->GetInstanceId() == state.ValidationCohortInstanceId;
            if (inOriginalInstance && (!bot->GetMap()
                || uint8(bot->GetMap()->GetDifficulty()) != admission.ExpectedDifficulty))
                invalidate(state, bot, "validation_active_map_difficulty_drift");
            if (!inOriginalInstance && (!state.NativeReleaseRequested
                || !state.NativeReleaseLandingObserved
                || !HasNativeRaidCorpseAuthority(state, bot)))
                invalidate(state, bot, "validation_active_untyped_recovery_transit");

            if (bot->getClass() == CLASS_HUNTER)
            {
                auto const admittedPet = admission.AdmissionReceiptByGuid.find(
                    state.Guid.GetCounter());
                if (admittedPet == admission.AdmissionReceiptByGuid.end()
                    || !admittedPet->second.PetIdentityPresent)
                {
                    invalidate(state, bot,
                        "validation_active_hunter_pet_receipt_missing");
                    continue;
                }

                HunterPetIdentitySnapshot observedPet;
                if (!ObserveActiveOrdinaryHunterPet(bot, observedPet))
                {
                    invalidate(state, bot,
                        "validation_active_hunter_pet_missing");
                    continue;
                }

                uint32 expectedPetId = 0;
                uint32 expectedPetEntry = 0;
                std::vector<std::pair<uint32, uint8>> expectedSpellbook;
                bool const canonicalPetMatches = ResolveExpectedHunterPetIdentity(
                        admittedPet->second.ClassSpec, expectedPetId, expectedPetEntry,
                        expectedSpellbook)
                    && observedPet.PetId == expectedPetId
                    && observedPet.PetEntry == expectedPetEntry
                    && observedPet.Spellbook == expectedSpellbook
                    && observedPet.SpellbookSha256
                        == HunterPetSpellbookSha256(expectedSpellbook);
                if (!canonicalPetMatches)
                {
                    invalidate(state, bot,
                        "validation_active_hunter_pet_canonical_identity_drift");
                    continue;
                }

                CohortAdmissionMemberReceipt const& frozenPet = admittedPet->second;
                bool const frozenPetMatches = frozenPet.PetId == observedPet.PetId
                    && frozenPet.PetEntry == observedPet.PetEntry
                    && frozenPet.PetSpellCount == observedPet.Spellbook.size()
                    && frozenPet.PetSpellbook == observedPet.Spellbook
                    && frozenPet.PetSpellbookSha256 == observedPet.SpellbookSha256;
                if (!frozenPetMatches)
                    invalidate(state, bot,
                        "validation_active_hunter_pet_admission_identity_drift");
            }
        }

        if (admittedGroup)
        {
            std::set<ObjectGuid> nativeGroupGuids;
            for (Group::MemberSlot const& slot : admittedGroup->GetMemberSlots())
                nativeGroupGuids.insert(slot.guid);
            if (nativeGroupGuids != expectedGuids)
                invalidate(Party().Bots.front(), GetLoadedBot(Party().Bots.front()),
                    "validation_active_native_group_membership_drift");
        }
        else
            invalidate(Party().Bots.front(), GetLoadedBot(Party().Bots.front()),
                "validation_active_group_missing");

        if (invalidReason)
        {
            MarkValidationCohortViolation(*invalidState, invalidBot, invalidReason);
            return;
        }
    }

    if (members.empty())
        return;

    Player* leader = members.front();
    bool const instancedValidation = (Cohort().Config.ValidationRouteMapId && sMapStore.LookupEntry(Cohort().Config.ValidationRouteMapId) && sMapStore.LookupEntry(Cohort().Config.ValidationRouteMapId)->Instanceable())
        || (leader->GetMap() && leader->GetMap()->Instanceable())
        || Cohort().Config.AllowDungeons
        || Cohort().Config.AllowRaids;
    if (!instancedValidation)
        return;

    Group* group = leader->GetGroup();
    if (!group)
    {
        if (activeObservationOnly)
        {
            MarkValidationCohortViolation(Party().Bots.front(), leader,
                "validation_active_group_missing");
            return;
        }
        group = new Group();
        if (!group->Create(leader))
        {
            delete group;
            Cohort().LastPopulationFailureReason = "validation_group_create_failed";
            return;
        }

        sGroupMgr->AddGroup(group);
        TC_LOG_INFO("server", "BotWorld validation cohort group created leader=%s group=%s",
            leader->GetGUID().ToString().c_str(), group->GetGUID().ToString().c_str());
    }

    bool const raidValidation = Cohort().Config.AllowRaids || members.size() > MAXGROUPSIZE || (leader->GetMap() && leader->GetMap()->IsRaid());
    std::vector<RaidRosterPlanSlot> const rosterPlan = BuildRosterPlan();
    if (!activeObservationOnly && raidValidation && !group->isRaidGroup())
        group->ConvertToRaid();

    // Form the exact group before invoking client-equivalent difficulty
    // semantics. The native handler must be able to inspect every member and
    // reject any member already inside a raid.
    for (Player* member : members)
    {
        if (!member || member == leader)
            continue;
        if (!activeObservationOnly && !member->GetGroup() && !group->AddMember(member))
        {
            Cohort().LastPopulationFailureReason = "validation_group_add_member_failed";
            return;
        }
        if (member->GetGroup() != group)
        {
            Cohort().LastPopulationFailureReason = "validation_bot_in_different_group";
            return;
        }
    }

    // Group creation is allowed while the roster is loading so subsequent
    // members enter the same native instance. Identity and formation evidence
    // are not: freezing a partial roster can combine a configured raid map
    // with an unrelated pre-entry instance zero and poison the whole attempt.
    uint32 const exactFormationSize = raidValidation
        ? uint32(rosterPlan.size()) : Cohort().Config.TargetPopulation;
    if (!exactFormationSize || members.size() != exactFormationSize)
    {
        Cohort().LastPopulationFailureReason = "validation_cohort_formation_pending";
        return;
    }

    for (WorldBotState& state : Party().Bots)
        if (state.ValidationCohortLocked
            && (state.ValidationCohortGroupGuid != group->GetGUID()
                || state.ValidationCohortLeaderGuid != group->GetLeaderGUID()))
        {
            MarkValidationCohortViolation(state, GetLoadedBot(state),
                "validation_cohort_immutable_group_leader_drift");
            Cohort().LastPopulationFailureReason = "validation_cohort_immutable_group_leader_drift";
            return;
        }

    Difficulty const requestedDungeonDifficulty = Difficulty(Cohort().Config.DungeonDifficulty);
    if (!raidValidation && group->GetDungeonDifficulty() != requestedDungeonDifficulty)
    {
        // Every bot receives the native player difficulty request before map
        // admission. Group::Create inherits the leader's value. A mismatch at
        // this point is evidence of an invalid admission sequence; never
        // repair it by mutating the live group from inside the instance.
        Cohort().LastPopulationFailureReason = "native_dungeon_difficulty_preentry_readback_mismatch";
        return;
    }
    Difficulty requestedRaidDifficulty = Difficulty(Cohort().Config.RaidDifficulty);
    bool const requested25Player = (Cohort().Config.RaidDifficulty & RAID_DIFFICULTY_MASK_25MAN) != 0;
    if (raidValidation && ((Cohort().Config.RaidSize == 25) != requested25Player))
    {
        Cohort().LastPopulationFailureReason = "raid_size_difficulty_mismatch";
        return;
    }
    if (raidValidation && group->GetRaidDifficulty() != requestedRaidDifficulty)
    {
        // Match WorldSession::HandleSetRaidDifficultyOpcode: an instance
        // occupant may not mutate raid difficulty.  Provisioning must set the
        // legitimate group difficulty before entry; runtime only reads it.
        if (leader->GetMap() && leader->GetMap()->IsRaid())
        {
            Cohort().LastPopulationFailureReason = "raid_difficulty_mismatch_inside_instance";
            return;
        }
        WorldPacket difficultyRequest(MSG_SET_RAID_DIFFICULTY, sizeof(uint32));
        difficultyRequest << uint32(requestedRaidDifficulty);
        leader->GetSession()->HandleSetRaidDifficultyOpcode(difficultyRequest);
        if (group->GetRaidDifficulty() != requestedRaidDifficulty)
        {
            Cohort().LastPopulationFailureReason = "native_raid_difficulty_change_rejected";
            return;
        }
    }

    uint32 leaderMapId = 0;
    uint32 leaderInstanceId = 0;
    bool frozenIdentityObserved = false;
    for (WorldBotState const& state : Party().Bots)
        if (state.ValidationCohortLocked)
        {
            if (!state.ValidationCohortMapId || !state.ValidationCohortInstanceId)
            {
                Cohort().LastPopulationFailureReason = "validation_cohort_zero_instance_identity";
                return;
            }
            if (!frozenIdentityObserved)
            {
                leaderMapId = state.ValidationCohortMapId;
                leaderInstanceId = state.ValidationCohortInstanceId;
                frozenIdentityObserved = true;
            }
            else if (state.ValidationCohortMapId != leaderMapId
                || state.ValidationCohortInstanceId != leaderInstanceId)
            {
                Cohort().LastPopulationFailureReason = "validation_cohort_frozen_identity_split";
                return;
            }
        }

    if (!frozenIdentityObserved)
    {
        uint32 const requiredMapId = Cohort().Config.ValidationRouteMapId;
        for (Player* member : members)
        {
            if (!member || !member->IsInWorld()
                || (requiredMapId && member->GetMapId() != requiredMapId)
                || !member->GetInstanceId())
            {
                Cohort().LastPopulationFailureReason = "validation_cohort_live_instance_pending";
                return;
            }
            if (!leaderInstanceId)
            {
                leaderMapId = member->GetMapId();
                leaderInstanceId = member->GetInstanceId();
            }
            else if (member->GetMapId() != leaderMapId
                || member->GetInstanceId() != leaderInstanceId)
            {
                Cohort().LastPopulationFailureReason = "validation_cohort_live_instance_split";
                return;
            }
        }
    }
    Party().GroupGuid = group->GetGUID();
    Party().MapId = leaderMapId;
    Party().InstanceId = leaderInstanceId;

    UpdateValidationCohortRaidRuntime(members, leader, group,
        activeObservationOnly, raidValidation, rosterPlan,
        leaderMapId, leaderInstanceId);
    RaidRuntime& raid = Cohort().Raid;
    std::unordered_map<uint32, WorldBotState*> stateByGuid;
    stateByGuid.reserve(Party().Bots.size());
    for (WorldBotState& state : Party().Bots)
        stateByGuid.emplace(state.Guid.GetCounter(), &state);

    // Freeze the server-provisioned identity before the action gate opens.
    // This is admission metadata, not a bot decision; UpdateBot remains inert
    // until BotActionsEnabled is committed below.
    for (Player* member : members)
    {
        if (!member || member->GetGroup() != group)
            continue;
        auto stateItr = stateByGuid.find(member->GetGUID().GetCounter());
        if (stateItr == stateByGuid.end())
            continue;
        WorldBotState& state = *stateItr->second;
        if (state.ValidationCohortLocked
            && (state.ValidationCohortLeaderGuid != leader->GetGUID()
                || state.ValidationCohortGroupGuid != group->GetGUID()
                || state.ValidationCohortMapId != leaderMapId
                || state.ValidationCohortInstanceId != leaderInstanceId))
        {
            MarkValidationCohortViolation(state, member,
                "validation_cohort_immutable_identity_drift");
            return;
        }
        if (!state.ValidationCohortLocked)
        {
            state.ValidationCohortLocked = true;
            state.ValidationCohortLeaderGuid = leader->GetGUID();
            state.ValidationCohortGroupGuid = group->GetGUID();
            state.ValidationCohortMapId = leaderMapId;
            state.ValidationCohortInstanceId = leaderInstanceId;
            state.ValidationCohortPhaseMask = 0;
        }
    }

    std::set<ObjectGuid> expectedNativeGroupGuids;
    for (WorldBotState const& state : Party().Bots)
        expectedNativeGroupGuids.insert(state.Guid);
    std::set<ObjectGuid> observedNativeGroupGuids;
    for (Group::MemberSlot const& slot : group->GetMemberSlots())
        observedNativeGroupGuids.insert(slot.guid);
    bool const nativeGroupMembershipExact = expectedNativeGroupGuids == observedNativeGroupGuids
        && observedNativeGroupGuids.size() == raid.ExpectedSize;

    // Admission gear is immutable for the whole attempt.  Re-observe the
    // loaded Player equipment on every active cohort pass so an item/enchant/
    // reforge/gem edit after the receipt was committed cannot qualify through
    // an old receipt or an unchanged average item level.
    if (raid.ServerProvisioningComplete)
    {
        if (raid.AdmissionReceiptByGuid.size() != raid.ExpectedSize)
        {
            if (!Party().Bots.empty())
                MarkValidationCohortViolation(Party().Bots.front(),
                    GetLoadedBot(Party().Bots.front()),
                    "validation_cohort_gear_identity_drift");
            return;
        }
        for (WorldBotState& state : Party().Bots)
        {
            Player* member = GetLoadedBot(state);
            auto const receiptItr = raid.AdmissionReceiptByGuid.find(
                state.Guid.GetCounter());
            std::vector<RaidRosterItemIdentity> currentManifest;
            std::string currentManifestSha256;
            std::string expectedGearProfileId;
            std::string expectedManifestSha256;
            if (!member || receiptItr == raid.AdmissionReceiptByGuid.end()
                || !ResolveExpectedBotGearIdentity(state.RosterClassSpec,
                    expectedGearProfileId, expectedManifestSha256)
                || !ObserveEquippedGearIdentity(member,
                    currentManifest, currentManifestSha256)
                || receiptItr->second.ClassSpec != state.RosterClassSpec
                || receiptItr->second.GearProfileId != expectedGearProfileId
                || receiptItr->second.GearManifestSha256 != expectedManifestSha256
                || currentManifestSha256 != receiptItr->second.GearManifestSha256
                || !EquippedGearManifestsEqual(
                    currentManifest, receiptItr->second.GearManifest))
            {
                MarkValidationCohortViolation(state, member,
                    "validation_cohort_gear_identity_drift");
                return;
            }
        }
    }

    if (!raid.ServerProvisioningComplete)
    {
        raid.ProvisionedMemberCount = 0;
        for (Player* member : members)
        {
            if (!member || !member->IsInWorld() || member->GetGroup() != group
                || member->GetMapId() != leaderMapId
                || member->GetInstanceId() != leaderInstanceId)
                continue;
            auto const stateItr = stateByGuid.find(member->GetGUID().GetCounter());
            if (stateItr != stateByGuid.end() && stateItr->second->ServerProvisioned)
                ++raid.ProvisionedMemberCount;
        }
        bool exactEntrancePlacement = Cohort().ValidationAdmissionBatchSealed
            && !Party().ValidationRouteManifest.empty();
        bool exactInitialAliveState = exactEntrancePlacement;
        if (exactEntrancePlacement)
        {
            ValidationRouteManifestNode const& routeStart = Party().ValidationRouteManifest.front();
            static constexpr float RouteStartHorizontalToleranceYards = 5.0f;
            static constexpr float RouteStartVerticalToleranceYards = 3.0f;
            for (WorldBotState const& state : Party().Bots)
                if (state.SpawnMapId != routeStart.BotStartMapId
                    || Distance2d(state.SpawnX, state.SpawnY,
                        routeStart.BotStartX, routeStart.BotStartY) > RouteStartHorizontalToleranceYards
                    || std::fabs(state.SpawnZ - routeStart.BotStartZ) > RouteStartVerticalToleranceYards)
                {
                    exactEntrancePlacement = false;
                    break;
                }
        }
        if (exactInitialAliveState)
            for (Player* member : members)
                if (!member || !member->IsAlive()
                    || member->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
                    || member->HasCorpse())
                {
                    exactInitialAliveState = false;
                    break;
                }
        raid.ServerProvisioningComplete = raid.ExpectedSize > 0
            && raid.ProvisionedMemberCount == raid.ExpectedSize
            && raid.RosterComplete && raid.UniqueLeases
            && raid.RosterCompositionValid && raid.DifficultyMatches
            && nativeGroupMembershipExact && exactEntrancePlacement
            && exactInitialAliveState;
        if (raid.ServerProvisioningComplete)
        {
            std::map<uint32, CohortAdmissionMemberReceipt> receipt;
            for (Player* member : members)
            {
                auto const stateItr = member
                    ? stateByGuid.find(member->GetGUID().GetCounter()) : stateByGuid.end();
                if (!member || stateItr == stateByGuid.end() || !member->GetMap())
                {
                    receipt.clear();
                    break;
                }
                CohortAdmissionMemberReceipt row;
                row.Guid = member->GetGUID();
                row.GroupGuid = group->GetGUID();
                row.LeaderGuid = group->GetLeaderGUID();
                row.RosterSlotId = stateItr->second->RosterSlotId;
                row.Role = stateItr->second->RosterRole.empty()
                    ? GetDungeonRole(member) : stateItr->second->RosterRole;
                row.ClassSpec = stateItr->second->RosterClassSpec.empty()
                    ? GetBotClassSpec(member) : stateItr->second->RosterClassSpec;
                row.ClassId = member->getClass();
                row.ActiveSpecIndex = member->GetActiveSpec();
                row.PrimaryTalentTreeId = member->GetPrimaryTalentTree(row.ActiveSpecIndex);
                row.ActiveTalentCount = uint32(std::count_if(
                    member->GetTalentMap(row.ActiveSpecIndex).begin(),
                    member->GetTalentMap(row.ActiveSpecIndex).end(),
                    [](auto const& talent) { return talent.second.State != PLAYERSPELL_REMOVED; }));
                for (auto const& [spellId, talent] : member->GetTalentMap(row.ActiveSpecIndex))
                    if (talent.State != PLAYERSPELL_REMOVED)
                        row.ActiveTalentSpellIds.push_back(spellId);
                std::sort(row.ActiveTalentSpellIds.begin(), row.ActiveTalentSpellIds.end());
                std::string expectedGearManifestSha256;
                if (!ResolveExpectedBotGearIdentity(row.ClassSpec,
                        row.GearProfileId, expectedGearManifestSha256)
                    || !ObserveEquippedGearIdentity(member,
                        row.GearManifest, row.GearManifestSha256)
                    || row.GearManifestSha256 != expectedGearManifestSha256)
                {
                    receipt.clear();
                    raid.ServerProvisioningComplete = false;
                    Cohort().LastPopulationFailureReason =
                        "validation_cohort_gear_identity_mismatch";
                    break;
                }
                row.GearItemCount = uint32(row.GearManifest.size());
                if (member->getClass() == CLASS_HUNTER)
                {
                    HunterPetIdentitySnapshot petIdentity;
                    if (!LoadedBotMatchesPinnedHunterPet(member, row.ClassSpec)
                        || !ObserveActiveOrdinaryHunterPet(member, petIdentity))
                    {
                        receipt.clear();
                        raid.ServerProvisioningComplete = false;
                        break;
                    }
                    row.PetIdentityPresent = true;
                    row.PetId = petIdentity.PetId;
                    row.PetEntry = petIdentity.PetEntry;
                    row.PetSpellCount = uint32(petIdentity.Spellbook.size());
                    row.PetSpellbook = std::move(petIdentity.Spellbook);
                    row.PetSpellbookSha256 = std::move(petIdentity.SpellbookSha256);
                }
                row.MapId = member->GetMapId();
                row.InstanceId = member->GetInstanceId();
                row.ExpectedDifficulty = raid.ExpectedDifficulty;
                row.PlayerDifficulty = uint8(raidValidation
                    ? member->GetRaidDifficulty() : member->GetDungeonDifficulty());
                row.MapDifficulty = int16(member->GetMap()->GetDifficulty());
                row.SpawnX = stateItr->second->SpawnX;
                row.SpawnY = stateItr->second->SpawnY;
                row.SpawnZ = stateItr->second->SpawnZ;
                row.SpawnO = stateItr->second->SpawnO;
                row.ServerProvisioned = stateItr->second->ServerProvisioned;
                row.InitialBaselineNormalized =
                    stateItr->second->ServerBaselineNormalized;
                row.InitialAliveStateVerified = member->IsAlive()
                    && !member->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST)
                    && !member->HasCorpse();
                receipt.emplace(row.Guid.GetCounter(), row);
            }
            if (receipt.size() != raid.ExpectedSize)
                raid.ServerProvisioningComplete = false;
            else
            {
                ValidationRouteManifestNode const& admissionStart =
                    Party().ValidationRouteManifest.front();
                raid.AdmissionReceiptByGuid = std::move(receipt);
                raid.AdmissionAttemptId = Cohort().AttemptId;
                raid.AdmissionCommittedAtMs = NowMs();
                raid.AdmissionActionGateEnabled = false;
                raid.AdmissionScenarioId = Cohort().Config.ValidationRouteScenarioId;
                raid.AdmissionRuntimeProfile = Cohort().SelectedProfileName;
                raid.AdmissionRouteManifestSha256 = Party().ValidationRouteManifestSha256;
                raid.AdmissionRecoveryEntranceAreaTriggerId =
                    admissionStart.RecoveryEntranceAreaTriggerId;
                raid.AdmissionRecoveryEntranceSourceMapId =
                    admissionStart.RecoveryEntranceSourceMapId;
                raid.AdmissionRecoveryEntranceTargetMapId =
                    admissionStart.RecoveryEntranceTargetMapId;
                raid.AdmissionEntranceMapId = admissionStart.BotStartMapId;
                raid.AdmissionEntranceX = admissionStart.BotStartX;
                raid.AdmissionEntranceY = admissionStart.BotStartY;
                raid.AdmissionEntranceZ = admissionStart.BotStartZ;
                raid.AdmissionEntranceO = admissionStart.BotStartO;
            }
        }
    }
    bool const currentAttemptFailed = !Cohort().ValidationAttemptFailureReason.empty()
        && Cohort().ValidationAttemptFailureAttemptId == Cohort().AttemptId;
    if (!raid.BotActionsEnabled && raid.ServerProvisioningComplete && !currentAttemptFailed)
    {
        raid.BotActionsEnabled = true;
        Cohort().ValidationAdmission = ValidationAdmissionPhase::Active;
        // Committing the receipt and opening the action gate are one server
        // tick transaction; UpdateBot cannot run between these two writes.
        raid.AdmissionActionGateEnabled = true;
    }

    if (raidValidation && members.size() > raid.ExpectedSize)
        Cohort().LastPopulationFailureReason = "raid_roster_exceeds_expected_size";
    else if (raidValidation && !raid.RosterCompositionValid)
        Cohort().LastPopulationFailureReason = "exact_raid_role_composition_mismatch";
    else if (raidValidation && leader->GetMap() && leader->GetMap()->IsRaid() && !raid.DifficultyMatches)
        Cohort().LastPopulationFailureReason = "raid_live_difficulty_mismatch";
    else if (!raidValidation && leader->GetMap() && leader->GetMap()->IsNonRaidDungeon() && !raid.DifficultyMatches)
        Cohort().LastPopulationFailureReason = "dungeon_live_difficulty_mismatch";
    else if (!nativeGroupMembershipExact)
        Cohort().LastPopulationFailureReason = "validation_native_group_membership_mismatch";

    // This is the server-to-agent activation barrier. Before it succeeds the
    // loaded characters exist only as an inert provisioned cohort; UpdateBot
    // rejects every decision because ValidationCohortLocked remains false.
    if (!raid.BotActionsEnabled)
    {
        if (Cohort().LastPopulationFailureReason.empty()
            || Cohort().LastPopulationFailureReason == "validation_cohort_formation_pending")
            Cohort().LastPopulationFailureReason = "server_provisioning_activation_pending";
        return;
    }
    if (Cohort().LastPopulationFailureReason == "validation_cohort_formation_pending"
        || Cohort().LastPopulationFailureReason == "server_provisioning_activation_pending")
        Cohort().LastPopulationFailureReason.clear();

    for (Player* bot : members)
    {
        if (!bot || bot->GetGroup() != group)
            continue;

        WorldBotState* memberState = nullptr;
        if (auto stateItr = stateByGuid.find(bot->GetGUID().GetCounter()); stateItr != stateByGuid.end())
            memberState = stateItr->second;
        if (!memberState)
            continue;

        if (memberState->ValidationCohortLocked
            && (memberState->ValidationCohortMapId != leaderMapId
                || memberState->ValidationCohortInstanceId != leaderInstanceId))
        {
            MarkValidationCohortViolation(*memberState, bot, "validation_cohort_immutable_identity_drift");
            continue;
        }
        if (!memberState->ValidationCohortLocked)
        {
            memberState->ValidationCohortLocked = true;
            memberState->ValidationCohortLeaderGuid = leader->GetGUID();
            memberState->ValidationCohortGroupGuid = group->GetGUID();
            memberState->ValidationCohortMapId = leaderMapId;
            memberState->ValidationCohortInstanceId = leaderInstanceId;
            memberState->ValidationCohortPhaseMask = 0;
        }

        std::string role = GetDungeonRole(bot);
        Party().RoleByGuid[bot->GetGUID().GetCounter()] = role;
        uint8 const expectedLfgRole = role == "tank" ? lfg::PLAYER_ROLE_TANK
            : (role == "healer" ? lfg::PLAYER_ROLE_HEALER : lfg::PLAYER_ROLE_DAMAGE);
        if (!activeObservationOnly && group->GetLfgRoles(bot->GetGUID()) != expectedLfgRole)
            group->SetLfgRoles(bot->GetGUID(), expectedLfgRole);

        // Formation payloads are immutable admission evidence. Do not rebuild
        // role power, raw state, and semantic JSON on every world tick after
        // those edge events have already been recorded.
        bool const recordGroupFormation = !memberState->ValidationGroupFormationRecorded;
        bool const recordRaidFormation = raidValidation && !memberState->ValidationRaidFormationRecorded;
        bool const recordRoleAssignment = !memberState->ValidationRoleAssignmentRecorded;
        if (recordGroupFormation || recordRaidFormation || recordRoleAssignment)
        {
            BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
            BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, raidValidation ? "raid_formation" : "party_formation", &power, stage);
            if (recordGroupFormation)
            {
                RecordEvent(*memberState, bot, "validation_group_formed", nullptr, raidValidation ? "raid" : "party", raw.c_str(), semantic.c_str(), float(members.size()), group->GetGUID().GetCounter());
                memberState->ValidationGroupFormationRecorded = true;
            }
            if (recordRaidFormation)
            {
                RecordEvent(*memberState, bot, "raid_formed", nullptr, "ok", raw.c_str(), semantic.c_str(), float(members.size()), group->GetGUID().GetCounter());
                memberState->ValidationRaidFormationRecorded = true;
            }
            if (recordRoleAssignment)
            {
                RecordEvent(*memberState, bot, "validation_role_assignment", nullptr, role.c_str(), raw.c_str(), semantic.c_str(), float(members.size()), expectedLfgRole);
                memberState->ValidationRoleAssignmentRecorded = true;
            }
        }
    }
}
