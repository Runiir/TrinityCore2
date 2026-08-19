#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotAdmissionIdentityGenerated.h"

#include "CharmInfo.h"
#include "Creature.h"
#include "Cryptography/CryptoHash.h"
#include "DatabaseEnv.h"
#include "DataStores/DBCStores.h"
#include "GameTime.h"
#include "Group.h"
#include "Instances/InstanceScript.h"
#include "Instances/InstanceSaveMgr.h"
#include "Item.h"
#include "ItemTemplate.h"
#include "LFG.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "Pet.h"
#include "Player.h"
#include "SpellInfo.h"
#include "Unit.h"
#include "Util.h"
#include "WorldSession.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

float Distance2d(float ax, float ay, float bx, float by)
{
    float dx = ax - bx;
    float dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
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
bool LoadedBotMatchesDeclaredSpec(Player const* bot, std::string const& classSpec)
{
    BotAdmissionIdentityGenerated::Identity const* identity =
        FindExpectedBotAdmissionIdentity(classSpec);
    if (!bot || !identity || !identity->TalentCount
        || identity->TalentOffset + identity->TalentCount
            > BotAdmissionIdentityGenerated::TalentSpellIds.size())
        return false;
    if (bot->getClass() != identity->ClassId
        || bot->GetPrimaryTalentTree(bot->GetActiveSpec())
            != identity->PrimaryTalentTreeId)
        return false;

    std::vector<uint32> observedTalents;
    for (auto const& [spellId, talent] : bot->GetTalentMap(bot->GetActiveSpec()))
        if (talent.State != PLAYERSPELL_REMOVED)
            observedTalents.push_back(spellId);
    std::sort(observedTalents.begin(), observedTalents.end());
    auto const expectedBegin = BotAdmissionIdentityGenerated::TalentSpellIds.begin()
        + identity->TalentOffset;
    return observedTalents.size() == identity->TalentCount
        && std::equal(observedTalents.begin(), observedTalents.end(), expectedBegin);
}
}

void BotWorldPopulationMgr::UpdateValidationCohortRaidRuntime(
    std::vector<Player*> const& members, Player* leader, Group* group,
    bool activeObservationOnly, bool raidValidation,
    std::vector<RaidRosterPlanSlot> const& rosterPlan,
    uint32 leaderMapId, uint32 leaderInstanceId)
{
    RaidRuntime& raid = Cohort().Raid;
    if (raid.GroupGuid != group->GetGUID() || raid.AttemptId != Cohort().AttemptId)
        raid = RaidRuntime();
    int16 const previousMapDifficulty = raid.MapDifficulty;
    uint32 const previousLockoutSaveId = raid.LockoutSaveId;
    raid.Active = raidValidation;
    raid.RaidInstance = raidValidation;
    raid.GroupGuid = group->GetGUID();
    raid.LeaderGuid = leader->GetGUID();
    raid.ExpectedSize = raidValidation ? uint32(rosterPlan.size()) : uint32(members.size());
    raid.ExpectedDifficulty = raidValidation
        ? Cohort().Config.RaidDifficulty : Cohort().Config.DungeonDifficulty;
    raid.GroupDifficulty = uint8(raidValidation
        ? group->GetRaidDifficulty() : group->GetDungeonDifficulty());
    Player* instanceMapObserver = nullptr;
    raid.DifficultyMemberCount = 0;
    raid.DifficultyMatchingMemberCount = 0;
    for (Player* member : members)
        if (member && member->GetMap() && member->GetMap()->IsDungeon()
            && member->GetMapId() == leaderMapId && member->GetInstanceId() == leaderInstanceId)
        {
            if (!instanceMapObserver)
                instanceMapObserver = member;
            ++raid.DifficultyMemberCount;
            Difficulty const memberDifficulty = raidValidation
                ? member->GetRaidDifficulty() : member->GetDungeonDifficulty();
            if (uint8(memberDifficulty) == raid.ExpectedDifficulty
                && uint8(member->GetMap()->GetDifficulty()) == raid.ExpectedDifficulty)
                ++raid.DifficultyMatchingMemberCount;
        }
    raid.MapDifficulty = instanceMapObserver
        ? int16(instanceMapObserver->GetMap()->GetDifficulty()) : previousMapDifficulty;
    raid.MapId = leaderMapId;
    raid.InstanceId = leaderInstanceId;
    raid.ServerEpoch = _serverEpoch;
    raid.AttemptId = Cohort().AttemptId;
    raid.ProfileGeneration = Cohort().PinnedProfileGeneration;
    raid.ProfileContentHash = Cohort().PinnedProfileContentHash;
    std::string currentStrategyId = Cohort().Config.ValidationRouteMechanicProfile.empty()
        ? Cohort().Config.ValidationRouteScenarioId : Cohort().Config.ValidationRouteMechanicProfile;
    if (!raid.StrategyId.empty() && raid.StrategyId != currentStrategyId)
    {
        raid.PreviousStrategyId = raid.StrategyId;
        raid.StrategyTransitionRouteGeneration = Party().ValidationRouteGeneration;
    }
    raid.StrategyId = currentStrategyId;
    raid.DifficultyReadbackComplete = raid.ExpectedSize > 0
        && raid.DifficultyMemberCount == raid.ExpectedSize;
    raid.DifficultyMatches = raid.GroupDifficulty == raid.ExpectedDifficulty
        && raid.DifficultyReadbackComplete
        && raid.DifficultyMatchingMemberCount == raid.ExpectedSize
        && raid.MapDifficulty == int16(raid.ExpectedDifficulty);
    // A live in-instance observer must provide the current bind.  Preserve
    // the prior save only while every released ghost is legitimately outside
    // the instance during native runback; never attribute a stale save to a
    // currently observed raid map.
    raid.LockoutSaveId = instanceMapObserver ? 0 : previousLockoutSaveId;
    if (instanceMapObserver)
        if (InstanceGroupBind* bind = group->GetBoundInstance(instanceMapObserver->GetMap()))
            if (bind->save)
                raid.LockoutSaveId = bind->save->GetInstanceId();

    std::vector<uint8> const previousBossStates = raid.BossStates;
    std::string const previousWipeState = raid.WipeState;
    std::string const previousRecoveryState = raid.RecoveryState;
    std::map<uint32, RaidRosterSlot> previousRoster = raid.RosterByGuid;
    std::map<uint32, RaidNativeSignalState> const previousNativeSignals = raid.NativeSignalsByGuid;
    std::unordered_map<uint32, WorldBotState*> stateByGuid;
    stateByGuid.reserve(Party().Bots.size());
    for (WorldBotState& state : Party().Bots)
        stateByGuid.emplace(state.Guid.GetCounter(), &state);
    raid.RosterByGuid.clear();
    raid.UniqueLeases = true;
    raid.RosterCompositionValid = true;
    std::set<uint32> observedGuids;
    std::set<std::string> observedSlots;

    auto findRosterPlanSlot = [&rosterPlan](std::string const& rosterSlotId) -> RaidRosterPlanSlot const*
    {
        for (RaidRosterPlanSlot const& slot : rosterPlan)
            if (slot.RosterSlotId == rosterSlotId)
                return &slot;
        return nullptr;
    };

    for (size_t memberIndex = 0; memberIndex < members.size(); ++memberIndex)
    {
        Player* bot = members[memberIndex];
        if (!bot || bot == leader)
        {
            if (!bot)
                continue;
        }

        if (bot->GetGroup() != group)
        {
            Cohort().LastPopulationFailureReason = "validation_bot_in_different_group";
            TC_LOG_ERROR("server", "BotWorld validation cohort bot already in different group leader=%s bot=%s",
                leader->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str());
            continue;
        }

        uint32 const guid = bot->GetGUID().GetCounter();
        WorldBotState const* botState = nullptr;
        if (auto stateItr = stateByGuid.find(guid); stateItr != stateByGuid.end())
            botState = stateItr->second;
        RaidRosterPlanSlot const* plannedSlot = botState ? findRosterPlanSlot(botState->RosterSlotId) : nullptr;
        if (Cohort().Config.ValidationRouteEnable && !plannedSlot)
            raid.RosterCompositionValid = false;

        uint8 const subgroup = plannedSlot ? plannedSlot->SubGroup : uint8(std::min<size_t>(memberIndex / MAXGROUPSIZE, 4));
        if (!activeObservationOnly && raidValidation && group->GetMemberGroup(bot->GetGUID()) != subgroup)
            group->ChangeMembersGroup(bot->GetGUID(), subgroup);

        RaidRosterSlot slot;
        slot.RosterSlotId = botState ? botState->RosterSlotId : "";
        slot.LeaseRoleSlot = slot.RosterSlotId;
        slot.SlotIndex = plannedSlot ? plannedSlot->SlotIndex : uint32(memberIndex);
        slot.Guid = bot->GetGUID();
        slot.AccountId = bot->GetSession() ? bot->GetSession()->GetAccountId() : 0;
        auto const cachedAccount = raid.AccountNameById.find(slot.AccountId);
        if (cachedAccount != raid.AccountNameById.end())
            slot.AccountName = cachedAccount->second;
        if (slot.AccountId && raid.AccountNameLookupAttempted.insert(slot.AccountId).second)
            if (QueryResult account = LoginDatabase.PQuery("SELECT username FROM account WHERE id = %u", slot.AccountId))
                raid.AccountNameById[slot.AccountId] = slot.AccountName = account->Fetch()[0].GetString();
        slot.CharacterName = bot->GetName();
        slot.SubGroup = raidValidation ? group->GetMemberGroup(bot->GetGUID()) : 0;
        slot.Role = plannedSlot && !plannedSlot->Role.empty() ? plannedSlot->Role : GetDungeonRole(bot);
        slot.ClassId = bot->getClass();
        slot.ClassSpec = botState && !botState->RosterClassSpec.empty() ? botState->RosterClassSpec : GetBotClassSpec(bot);
        slot.AverageItemLevel = botState && botState->RosterAverageItemLevel > 0.0f
            ? botState->RosterAverageItemLevel : bot->GetAverageItemLevel();
        std::ostringstream gearIdentity;
        gearIdentity << "equipped";
        for (uint8 equipmentSlot = EQUIPMENT_SLOT_START; equipmentSlot < EQUIPMENT_SLOT_END; ++equipmentSlot)
            if (Item const* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, equipmentSlot))
            {
                RaidRosterItemIdentity manifestItem;
                manifestItem.Slot = equipmentSlot;
                manifestItem.Guid = item->GetGUID().GetCounter();
                manifestItem.Entry = item->GetEntry();
                manifestItem.EnchantId = item->GetEnchantmentId(PERM_ENCHANTMENT_SLOT);
                manifestItem.ReforgeId = item->GetEnchantmentId(REFORGE_ENCHANTMENT_SLOT);
                for (uint8 gemSlot = 0; gemSlot < MAX_GEM_SOCKETS; ++gemSlot)
                {
                    uint32 const gemEnchantId = item->GetEnchantmentId(EnchantmentSlot(SOCK_ENCHANTMENT_SLOT + gemSlot));
                    if (SpellItemEnchantmentEntry const* enchant = sSpellItemEnchantmentStore.LookupEntry(gemEnchantId))
                        if (enchant->Src_itemID)
                            manifestItem.GemItemIds.push_back(enchant->Src_itemID);
                }
                slot.GearManifest.push_back(std::move(manifestItem));
                gearIdentity << ';' << uint32(equipmentSlot) << ':' << item->GetGUID().GetCounter()
                    << ':' << item->GetEntry() << ':';
                for (uint8 enchantSlot = 0; enchantSlot < MAX_ENCHANTMENT_SLOT; ++enchantSlot)
                {
                    if (enchantSlot)
                        gearIdentity << ',';
                    // Raid roster identity is permanent. Weapon oils, poisons,
                    // and class imbues occupy TEMP_ENCHANTMENT_SLOT and may
                    // legitimately change after the roster has been frozen.
                    gearIdentity << (enchantSlot == TEMP_ENCHANTMENT_SLOT
                        ? 0 : item->GetEnchantmentId(EnchantmentSlot(enchantSlot)));
                }
            }
        slot.GearIdentity = gearIdentity.str();
        std::ostringstream talentIdentity;
        talentIdentity << "active_spec:" << uint32(bot->GetActiveSpec());
        std::vector<uint32> activeTalents;
        for (auto const& [spellId, talent] : bot->GetTalentMap(bot->GetActiveSpec()))
            if (talent.State != PLAYERSPELL_REMOVED)
                activeTalents.push_back(spellId);
        std::sort(activeTalents.begin(), activeTalents.end());
        slot.Talents = activeTalents;
        for (uint32 spellId : activeTalents)
            talentIdentity << ';' << spellId;
        slot.TalentIdentity = talentIdentity.str();
        std::ostringstream glyphIdentity;
        glyphIdentity << "active_spec:" << uint32(bot->GetActiveSpec());
        for (uint8 glyphSlot = 0; glyphSlot < MAX_GLYPH_SLOT_INDEX; ++glyphSlot)
        {
            uint32 const glyph = bot->GetGlyph(bot->GetActiveSpec(), glyphSlot);
            glyphIdentity << ';' << uint32(glyphSlot) << ':' << glyph;
            if (glyph)
                slot.Glyphs.push_back(glyph);
        }
        slot.GlyphIdentity = glyphIdentity.str();
        slot.Active = bot->IsInWorld();
        slot.LeaseOwned = LeaseOwnedByCurrentCohort(guid, slot.LeaseRoleSlot);
        raid.RosterByGuid.emplace(guid, slot);
        if (!observedGuids.insert(guid).second || !observedSlots.insert(slot.RosterSlotId).second
            || slot.RosterSlotId.empty() || !slot.LeaseOwned)
            raid.UniqueLeases = false;

        if (Cohort().Config.ValidationRouteEnable
            && (!plannedSlot || slot.Role != plannedSlot->Role
                || (!Cohort().Config.PoolClassSpecFilter.empty()
                    && (plannedSlot->SlotIndex >= Cohort().Config.PoolClassSpecFilter.size()
                        || slot.ClassSpec != Cohort().Config.PoolClassSpecFilter[plannedSlot->SlotIndex]))
                || !LoadedBotMatchesDeclaredSpec(bot, slot.ClassSpec)
                || (!activeObservationOnly
                    && !LoadedBotMatchesPinnedHunterPet(bot, slot.ClassSpec))))
            raid.RosterCompositionValid = false;

        RaidNativeSignalState currentSignal;
        auto previousSignal = previousNativeSignals.find(guid);
        if (previousSignal != previousNativeSignals.end())
            currentSignal = previousSignal->second;
        currentSignal.Initialized = true;
        currentSignal.Alive = bot->IsAlive();
        // Player::GetCorpse() follows the player's current map and therefore
        // becomes null as soon as a native release moves the ghost to the
        // outdoor graveyard.  Use the same immutable original-instance corpse
        // authority as the recovery action instead of losing the corpse edge
        // in the runtime evidence graph.
        currentSignal.HasCorpse = botState && HasNativeRaidCorpseAuthority(*botState, bot);
        currentSignal.Released = bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST);
        currentSignal.MapId = bot->GetMapId();
        currentSignal.InstanceId = bot->GetInstanceId();
        currentSignal.OutsideOriginalInstance = currentSignal.MapId != raid.MapId
            || currentSignal.InstanceId != raid.InstanceId;
        currentSignal.X = bot->GetPositionX();
        currentSignal.Y = bot->GetPositionY();
        currentSignal.Z = bot->GetPositionZ();
        raid.NativeSignalsByGuid[guid] = currentSignal;

        std::string role = slot.Role;
        if (!activeObservationOnly && role == "tank")
            group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_TANK);
        else if (!activeObservationOnly && role == "healer")
            group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_HEALER);
        else if (!activeObservationOnly)
            group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_DAMAGE);

        if (botState && !IsValidationCohortMemberInOriginalInstance(*botState, bot))
        {
            for (WorldBotState& state : Party().Bots)
                if (state.Guid == bot->GetGUID())
                    MarkValidationCohortViolation(state, bot, "validation_cohort_spawned_outside_leader_instance");
            continue;
        }
    }

    raid.ActiveSize = uint32(raid.RosterByGuid.size());
    for (auto itr = raid.NativeSignalsByGuid.begin(); itr != raid.NativeSignalsByGuid.end();)
        if (!observedGuids.count(itr->first))
            itr = raid.NativeSignalsByGuid.erase(itr);
        else
            ++itr;
    raid.AliveSize = uint32(std::count_if(members.begin(), members.end(), [](Player const* member)
    {
        return member && member->IsAlive();
    }));
    raid.RosterComplete = raid.ActiveSize == raid.ExpectedSize;
    bool const typedValidationRoster = Cohort().Config.ValidationRouteEnable
        && rosterPlan.size() == raid.ExpectedSize
        && std::all_of(rosterPlan.begin(), rosterPlan.end(),
            [](RaidRosterPlanSlot const& slot) { return !slot.Role.empty(); });
    if (typedValidationRoster)
    {
        uint32 tankCount = 0;
        uint32 healerCount = 0;
        uint32 dpsCount = 0;
        for (auto const& [guid, slot] : raid.RosterByGuid)
        {
            if (slot.Role == "tank")
                ++tankCount;
            else if (slot.Role == "healer")
                ++healerCount;
            else if (slot.Role == "dps")
                ++dpsCount;
            else
                raid.RosterCompositionValid = false;
        }
        uint32 const expectedTanks = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
            [](RaidRosterPlanSlot const& slot) { return slot.Role == "tank"; }));
        uint32 const expectedHealers = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
            [](RaidRosterPlanSlot const& slot) { return slot.Role == "healer"; }));
        uint32 const expectedDps = uint32(std::count_if(rosterPlan.begin(), rosterPlan.end(),
            [](RaidRosterPlanSlot const& slot) { return slot.Role == "dps"; }));
        raid.RosterCompositionValid = raid.RosterCompositionValid
            && tankCount == expectedTanks && healerCount == expectedHealers && dpsCount == expectedDps;
    }
    else if (!Cohort().Config.ValidationRouteEnable)
        raid.RosterCompositionValid = true;
    else
        raid.RosterCompositionValid = false;

    if (previousRoster.size() != raid.RosterByGuid.size())
        ++raid.AssignmentGeneration;
    else
        for (auto const& [guid, slot] : raid.RosterByGuid)
        {
            auto previous = previousRoster.find(guid);
            if (previous == previousRoster.end() || previous->second.SlotIndex != slot.SlotIndex
                || previous->second.SubGroup != slot.SubGroup || previous->second.Role != slot.Role
                || previous->second.RosterSlotId != slot.RosterSlotId
                || previous->second.ClassSpec != slot.ClassSpec
                || previous->second.AverageItemLevel != slot.AverageItemLevel)
            {
                ++raid.AssignmentGeneration;
                break;
            }
        }

    raid.BossStates = previousBossStates;
    raid.EncounterInProgress = false;
    if (InstanceScript* instance = instanceMapObserver ? instanceMapObserver->GetInstanceScript() : nullptr)
    {
        raid.BossStates.clear();
        raid.EncounterInProgress = instance->IsEncounterInProgress();
        raid.BossStates.reserve(instance->GetEncounterCount());
        for (uint32 bossId = 0; bossId < instance->GetEncounterCount(); ++bossId)
            raid.BossStates.push_back(uint8(instance->GetBossState(bossId)));
    }

    bool bossResetObserved = false;
    for (size_t bossId = 0; bossId < std::min(previousBossStates.size(), raid.BossStates.size()); ++bossId)
        if (previousBossStates[bossId] == uint8(IN_PROGRESS)
            && raid.BossStates[bossId] != uint8(IN_PROGRESS)
            && raid.BossStates[bossId] != uint8(DONE))
        {
            bossResetObserved = true;
            break;
        }
    if (bossResetObserved)
        ++raid.BossResetGeneration;

    // Hostile reset evidence belongs to one immutable attempt/node scope.
    // Never let an earlier trash node or route generation arm a later wipe.
    uint64 const hostileObservationAttemptId = raid.AttemptId;
    uint64 const hostileObservationRouteGeneration = Party().ValidationRouteGeneration;
    std::string const hostileObservationNodeId = Cohort().Config.ValidationRouteNodeId;
    bool const hostileObservationScopeChanged = raid.NativeHostileObservationAttemptId != hostileObservationAttemptId
        || raid.NativeHostileObservationRouteGeneration != hostileObservationRouteGeneration
        || raid.NativeHostileObservationNodeId != hostileObservationNodeId;
    if (hostileObservationScopeChanged)
    {
        raid.NativeHostileObservationAttemptId = hostileObservationAttemptId;
        raid.NativeHostileObservationRouteGeneration = hostileObservationRouteGeneration;
        raid.NativeHostileObservationNodeId = hostileObservationNodeId;
        raid.NativeHostileActivityActive = false;
        raid.NativeHostileActivitySeen = false;
        raid.NativeHostileActivitySeenAtWipe = false;
        raid.NativeHostileInactivityObserved = false;
        raid.NativeHostileInactiveSinceMs = 0;
        raid.NativeHostileResetGeneration = 0;
        raid.NativeHostileResetGenerationAtWipe = 0;
        raid.NativeHostileActivityEntry = 0;
        raid.NativeHostileActivityGuid.Clear();
        raid.NativeHostileActivityReason = "native_hostile_observation_scope_reset";
    }

    // Boss state is not a complete reset signal for trash-only route nodes.
    // Observe every loaded hostile creature in the exact native instance and
    // retain the activity edge so recovery can distinguish an evaded/reset
    // pack from an idle-looking pack that still owns combat state.
    if (raidValidation)
    {
        Map* nativeRaidMap = instanceMapObserver
            ? instanceMapObserver->GetMap()
            : sMapMgr->FindMap(raid.MapId, raid.InstanceId);
        Player* hostilityObserver = members.empty() ? nullptr : members.front();
        bool hostileActive = false;
        std::string hostileReason;
        uint32 hostileEntry = 0;
        ObjectGuid hostileGuid;
        bool const hostileObservationValid = ObserveNativeRaidHostileActivity(nativeRaidMap, hostilityObserver,
            hostileActive, hostileReason, hostileEntry, hostileGuid);
        if (!hostileObservationValid)
            hostileActive = true;
        raid.NativeHostileActivityActive = hostileActive;
        raid.NativeHostileActivityReason = hostileReason;
        raid.NativeHostileActivityEntry = hostileEntry;
        raid.NativeHostileActivityGuid = hostileGuid;
        uint64 const nowMs = NowMs();
        if (hostileActive)
        {
            raid.NativeHostileActivitySeen = true;
            raid.NativeHostileInactiveSinceMs = 0;
        }
        else if (raid.WipeGeneration > 0
            && (raid.NativeHostileActivitySeenAtWipe || raid.NativeHostileActivitySeen))
        {
            if (!raid.NativeHostileInactiveSinceMs)
                raid.NativeHostileInactiveSinceMs = nowMs;
            if (nowMs - raid.NativeHostileInactiveSinceMs >= 5000)
            {
                raid.NativeHostileInactivityObserved = true;
                if (raid.NativeHostileResetGeneration == raid.NativeHostileResetGenerationAtWipe)
                    ++raid.NativeHostileResetGeneration;
            }
        }
    }

    bool const allDead = raid.ActiveSize > 0 && raid.AliveSize == 0;
    bool const allAlive = raid.ActiveSize > 0 && raid.AliveSize == raid.ActiveSize;
    if (allDead)
    {
        if (previousWipeState != "wiped")
        {
            ++raid.WipeGeneration;
            // A prepared or delivered trash charge belongs to the exact
            // pre-wipe attempt. Never allow a same-node recovery to consume
            // it as a new-attempt lane decision or interval baseline.
            if (Cohort().Config.ValidationRouteMechanicProfile == "trash_two_tank_charge_lanes")
            {
                Party().ValidationRouteDrudgeChargeObservations.clear();
                Party().ValidationRouteDrudgeLastChargeMsBySpawn.clear();
                Party().ValidationRouteDrudgeChargePreparedCount = 0;
                Party().ValidationRouteDrudgeChargeDeliveredCount = 0;
                Party().ValidationRouteDrudgeChargeQueueOverflow = false;
                Party().ValidationRouteDrudgeDeliveredBySpawn.clear();
                Party().ValidationRouteDrudgeValidIntervalsBySpawn.clear();
                Party().ValidationRouteDrudgeReseparatedRosterGuids.clear();
                Party().ValidationRouteDrudgeOwnershipRosterGuids.clear();
                Party().ValidationRouteDrudgeTauntRosterGuids.clear();
                Party().ValidationRouteDrudgeHealthSyncRosterGuids.clear();
                Party().ValidationRouteDrudgeHealthSyncEvaluatedRosterGuids.clear();
                Party().ValidationRouteDrudgeProfileActionRosterGuids.clear();
                Party().ValidationRouteDrudgePrepullStaged = false;
                Party().ValidationRouteDrudgePrepullAttemptId = 0;
                Party().ValidationRouteDrudgePrepullWipeGeneration = 0;
                Party().ValidationRouteDrudgePrepullRouteGeneration = 0;
                Party().ValidationRouteDrudgeHealthSyncEvidenceAttemptId = 0;
                Party().ValidationRouteDrudgeHealthSyncEvidenceWipeGeneration = 0;
                Party().ValidationRouteDrudgeHealthSyncEvidenceRouteGeneration = 0;
                Party().ValidationRouteDrudgeHealthSyncHoldSourceSpawnId = 0;
                Party().ValidationRouteDrudgeHealthSyncHoldTankGuid = 0;
                Party().ValidationRouteDrudgeHealthSyncHoldLowerPct = 0.0f;
                Party().ValidationRouteDrudgeHealthSyncHoldPeerPct = 0.0f;
                Party().ValidationRouteDrudgeHealthSyncHoldLowerAlive = false;
                Party().ValidationRouteDrudgeHealthSyncHoldPeerAlive = false;
                Party().ValidationRouteDrudgeDeathAttemptId = 0;
                Party().ValidationRouteDrudgeDeathWipeGeneration = 0;
                Party().ValidationRouteDrudgeDeathRouteGeneration = 0;
                Party().ValidationRouteDrudgeDeathSourceSpawnId = 0;
                Party().ValidationRouteDrudgeDeathSourceGuid = 0;
                Party().ValidationRouteDrudgeSurvivorSourceSpawnId = 0;
                Party().ValidationRouteDrudgeSurvivorSourceGuid = 0;
                Party().ValidationRouteDrudgeDeathEvidenceSequence = 0;
                Party().ValidationRouteDrudgeRageWaitEvidenceSequence = 0;
                Party().ValidationRouteDrudgeRageAuraEvidenceSequence = 0;
                Party().ValidationRouteDrudgeThreatSeedAttemptId = Cohort().AttemptId;
                Party().ValidationRouteDrudgeThreatSeedWipeGeneration = raid.WipeGeneration;
                Party().ValidationRouteDrudgeThreatSeedRouteGeneration =
                    Party().ValidationRouteGeneration;
                Party().ValidationRouteDrudgeThreatSeedClosed = false;
                Party().ValidationRouteDrudgeThreatSeedComplete = false;
                Party().ValidationRouteDrudgeThreatSeedFailure = false;
                Party().ValidationRouteDrudgeThreatSeedRosterGuids.clear();
                Party().ValidationRouteDrudgeThreatSeedEvidenceRows.clear();
                for (WorldBotState& botState : Party().Bots)
                {
                    botState.LastValidationRouteDrudgeChargeGenerationHandled = 0;
                    botState.LastValidationRouteDrudgeChargeGenerationObserved = 0;
                    botState.ValidationRouteDrudgeAnchorValid = false;
                    botState.ValidationRouteDrudgeAnchorPathProven = false;
                    botState.ValidationRouteDrudgeRecoveryAnchorPathProven = false;
                    botState.ValidationRouteDrudgeRecoveryAnchorX = 0.0f;
                    botState.ValidationRouteDrudgeRecoveryAnchorY = 0.0f;
                    botState.ValidationRouteDrudgeRecoveryAnchorZ = 0.0f;
                    botState.ValidationRouteDrudgeAnchorMapId = 0;
                    botState.ValidationRouteDrudgeAnchorInstanceId = 0;
                    botState.ValidationRouteDrudgeAnchorSource0Identity = 0;
                    botState.ValidationRouteDrudgeAnchorSource1Identity = 0;
                }
            }
            // Latch recovery authority at the native all-dead edge.  The
            // first post-resurrection all-alive sample must not reopen route
            // decisions while the ready-check action and the final evidence
            // refresh are still pending.
            bool const nativeRecoveryPolicy =
                Cohort().Config.ValidationRouteBossRecovery
                    == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly;
            raid.NativeRecoveryHoldActive = nativeRecoveryPolicy;
            raid.NativeRecoveryRouteGeneration = nativeRecoveryPolicy
                ? Party().ValidationRouteGeneration : 0;
            raid.NativeRecoveryNodeId = nativeRecoveryPolicy
                ? Cohort().Config.ValidationRouteNodeId : std::string();
            // Sampling may observe the last death and the native instance
            // IN_PROGRESS -> reset transition together.  Preserve the
            // generation immediately before that transition so the observed
            // native reset counts without requiring an impossible second
            // reset transition.
            raid.BossResetGenerationAtWipe = bossResetObserved && raid.BossResetGeneration > 0
                ? raid.BossResetGeneration - 1 : raid.BossResetGeneration;
            raid.NativeHostileResetGenerationAtWipe = raid.NativeHostileResetGeneration;
            raid.NativeHostileActivitySeenAtWipe = raid.NativeHostileActivitySeen;
            // Activity observed after this wipe can arm the same transition
            // if the first post-death sample missed the pack while it was
            // still active. Keep only the pre-wipe edge in SeenAtWipe.
            raid.NativeHostileActivitySeen = false;
            raid.NativeHostileInactivityObserved = false;
            raid.NativeHostileInactiveSinceMs = 0;
            for (auto& [guid, signal] : raid.NativeSignalsByGuid)
            {
                signal.WipeGeneration = raid.WipeGeneration;
                signal.DeathSequence = ++raid.EvidenceSequence;
                signal.CorpseSequence = signal.HasCorpse ? ++raid.EvidenceSequence : 0;
                signal.ReleaseSequence = 0;
                signal.RunbackSequence = 0;
                signal.ReentrySequence = 0;
                signal.ResurrectionSequence = 0;
            }
            raid.NativeReleaseObserved = false;
            raid.NativeResurrectionObserved = false;
            raid.NativeRunbackObserved = false;
            // A ready check issued before this native wipe cannot authorize
            // post-wipe recovery. Keep the monotonic action generation for
            // auditability, but clear its acceptance identity.
            raid.NativeReadyCheckActionObserved = false;
            raid.NativeReadyCheckActionAttemptId = 0;
            raid.NativeReadyCheckActionWipeGeneration = 0;
            raid.NativeReadyCheckAssignmentGeneration = 0;
            raid.NativeReadyCheckActionEvidenceSequence = 0;
            raid.NativeReadyCheckResponseCount = 0;
            raid.NativeReadyCheckResponders.clear();
            raid.NativeReadyCheckPending = false;
        }
    }

    // Reconstruct the native recovery path independently for every immutable
    // roster GUID. Sequence fields are wipe-scoped and can only advance in the
    // order death -> corpse -> release -> moved ghost -> instance re-entry ->
    // resurrection. Invoking movement or an area-trigger handler is never, by
    // itself, evidence that the transition succeeded.
    if (raid.WipeGeneration > 0)
        for (auto& [guid, signal] : raid.NativeSignalsByGuid)
        {
            auto const previousSignal = previousNativeSignals.find(guid);
            RaidNativeSignalState const* prior = previousSignal == previousNativeSignals.end()
                ? nullptr : &previousSignal->second;
            WorldBotState const* botState = nullptr;
            for (WorldBotState const& candidate : Party().Bots)
                if (candidate.Guid.GetCounter() == guid)
                {
                    botState = &candidate;
                    break;
                }
            if (signal.WipeGeneration != raid.WipeGeneration)
                continue;
            if (!signal.DeathSequence && !signal.Alive)
                signal.DeathSequence = ++raid.EvidenceSequence;
            if (!signal.CorpseSequence && signal.DeathSequence && signal.HasCorpse)
                signal.CorpseSequence = ++raid.EvidenceSequence;
            if (!signal.ReleaseSequence && signal.CorpseSequence && signal.Released)
                signal.ReleaseSequence = ++raid.EvidenceSequence;
            bool const releaseLandingIdentityBound = botState
                && botState->NativeReleaseRequested
                && botState->NativeReleaseLandingObserved
                && botState->NativeReleaseLandingWipeGeneration == raid.WipeGeneration
                && raid.AdmissionRecoveryEntranceAreaTriggerId
                && botState->NativeRunbackAreaTriggerId
                    == raid.AdmissionRecoveryEntranceAreaTriggerId
                && !signal.Alive && signal.HasCorpse && signal.Released && signal.OutsideOriginalInstance
                && signal.MapId == botState->NativeReleaseLandingMapId
                && signal.InstanceId == botState->NativeReleaseLandingInstanceId;
            bool const progressedFromReleaseLanding = releaseLandingIdentityBound
                && (Distance2d(signal.X, signal.Y,
                        botState->NativeReleaseLandingX, botState->NativeReleaseLandingY) > 2.0f
                    || std::fabs(signal.Z - botState->NativeReleaseLandingZ) > 2.0f);
            bool const movedOutsideAsGhost = prior && prior->Released && signal.Released
                && prior->OutsideOriginalInstance && progressedFromReleaseLanding;
            if (!signal.RunbackSequence && signal.ReleaseSequence && movedOutsideAsGhost)
                signal.RunbackSequence = ++raid.EvidenceSequence;
            bool const enteredOriginalInstance = prior && prior->Released && prior->OutsideOriginalInstance
                && !signal.OutsideOriginalInstance;
            if (!signal.ReentrySequence && signal.RunbackSequence && enteredOriginalInstance)
                signal.ReentrySequence = ++raid.EvidenceSequence;
            if (!signal.ResurrectionSequence && signal.ReentrySequence && signal.Alive
                && prior && !prior->Alive)
                signal.ResurrectionSequence = ++raid.EvidenceSequence;
        }

    auto signalComplete = [&raid](RaidNativeSignalState const& signal)
    {
        return signal.WipeGeneration == raid.WipeGeneration
            && signal.DeathSequence > 0
            && signal.DeathSequence < signal.CorpseSequence
            && signal.CorpseSequence < signal.ReleaseSequence
            && signal.ReleaseSequence < signal.RunbackSequence
            && signal.RunbackSequence < signal.ReentrySequence
            && signal.ReentrySequence < signal.ResurrectionSequence;
    };
    bool const exactSignalRoster = raid.RosterComplete
        && raid.NativeSignalsByGuid.size() == raid.RosterByGuid.size()
        && std::all_of(raid.RosterByGuid.begin(), raid.RosterByGuid.end(),
            [&raid](auto const& row) { return raid.NativeSignalsByGuid.count(row.first) == 1; });
    raid.NativeDeathObserved = exactSignalRoster && std::all_of(raid.NativeSignalsByGuid.begin(), raid.NativeSignalsByGuid.end(),
        [&raid](auto const& row) { return row.second.WipeGeneration == raid.WipeGeneration && row.second.DeathSequence > 0; });
    raid.NativeCorpseObserved = exactSignalRoster && std::all_of(raid.NativeSignalsByGuid.begin(), raid.NativeSignalsByGuid.end(),
        [&raid](auto const& row) { return row.second.WipeGeneration == raid.WipeGeneration && row.second.CorpseSequence > row.second.DeathSequence; });
    raid.NativeReleaseObserved = exactSignalRoster && std::all_of(raid.NativeSignalsByGuid.begin(), raid.NativeSignalsByGuid.end(),
        [&raid](auto const& row) { return row.second.WipeGeneration == raid.WipeGeneration && row.second.ReleaseSequence > row.second.CorpseSequence; });
    raid.NativeRunbackObserved = exactSignalRoster && std::all_of(raid.NativeSignalsByGuid.begin(), raid.NativeSignalsByGuid.end(),
        [&raid](auto const& row) { return row.second.WipeGeneration == raid.WipeGeneration && row.second.RunbackSequence > row.second.ReleaseSequence; });
    raid.NativeResurrectionObserved = exactSignalRoster && std::all_of(raid.NativeSignalsByGuid.begin(), raid.NativeSignalsByGuid.end(),
        [signalComplete](auto const& row) { return signalComplete(row.second); });
    bool const nativeHostileResetObserved = raid.NativeHostileInactivityObserved
        && raid.NativeHostileResetGeneration > raid.NativeHostileResetGenerationAtWipe;
    bool const nativeResetObserved = raid.BossResetGeneration > raid.BossResetGenerationAtWipe
        || nativeHostileResetObserved;
    bool const nativeRecoverySignals = raid.NativeDeathObserved
        && raid.NativeCorpseObserved && raid.NativeReleaseObserved
        && raid.NativeResurrectionObserved && raid.NativeRunbackObserved
        && nativeResetObserved;
    raid.NativeRecoveryEvidenceComplete = nativeRecoverySignals && raid.NativeReadyCheckActionObserved
        && raid.NativeReadyCheckActionAttemptId == raid.AttemptId
        && raid.NativeReadyCheckActionWipeGeneration == raid.WipeGeneration
        && raid.NativeReadyCheckAssignmentGeneration == raid.AssignmentGeneration;
    if (raid.NativeRecoveryEvidenceComplete)
        raid.NativeRecoveryHoldActive = false;

    // A partial death is not a native wipe.  Keep the full recovery state
    // machine scoped to an observed all-dead latch with a real wipe
    // generation; otherwise a partial-death recovery string can manufacture a
    // wiped/recovery-pending state when the roster becomes all-alive again.
    bool const nativeWipeRecovery = previousWipeState == "wiped" && raid.WipeGeneration > 0;

    if (allDead)
    {
        raid.WipeState = "wiped";
        raid.RecoveryState = raid.EncounterInProgress ? "awaiting_native_reset" : "release_resurrection_pending";
    }
    else if (!allAlive)
    {
        raid.WipeState = previousWipeState == "wiped" ? "wiped" : "partial_deaths";
        raid.RecoveryState = nativeWipeRecovery ? "native_resurrection_runback" : "none";
    }
    else if (raid.EncounterInProgress)
    {
        raid.WipeState = "engaged";
        raid.RecoveryState = "none";
    }
    else if (nativeWipeRecovery
        || (raid.WipeGeneration > 0 && previousRecoveryState == "awaiting_native_reset")
        || (raid.WipeGeneration > 0 && previousRecoveryState == "release_resurrection_pending")
        || (raid.WipeGeneration > 0 && previousRecoveryState == "native_resurrection_runback"))
    {
        if (raid.NativeRecoveryEvidenceComplete)
        {
            raid.WipeState = "ready";
            raid.RecoveryState = "recovered_ready_check";
            ++raid.RecoveryGeneration;
        }
        else
        {
            raid.WipeState = "wiped";
            raid.RecoveryState = "recovery_evidence_pending";
        }
    }
    else if (raid.WipeGeneration > 0 && previousRecoveryState == "recovered_ready_check")
    {
        if (raid.NativeRecoveryEvidenceComplete)
        {
            raid.WipeState = "ready";
            raid.RecoveryState = "recovered_ready_check";
        }
        else
        {
            raid.WipeState = "wiped";
            raid.RecoveryState = "recovery_evidence_pending";
        }
    }
    else
    {
        raid.WipeState = "ready";
        raid.RecoveryState = "none";
    }

    bool bossInProgress = false;
    bool bossDone = false;
    for (uint8 bossState : raid.BossStates)
    {
        bossInProgress = bossInProgress || bossState == uint8(IN_PROGRESS);
        bossDone = bossDone || bossState == uint8(DONE);
    }
    if (bossInProgress || raid.EncounterInProgress)
        raid.EncounterPhase = "combat";
    else if (raid.RecoveryState == "awaiting_native_reset"
        || raid.RecoveryState == "release_resurrection_pending"
        || raid.RecoveryState == "native_resurrection_runback"
        || raid.RecoveryState == "recovery_evidence_pending"
        || bossResetObserved)
        raid.EncounterPhase = "recovery";
    else if (bossDone)
        raid.EncounterPhase = "completed";
    else
        raid.EncounterPhase = "formation";

    raid.ReadyCheckSatisfied = raid.RosterComplete && raid.UniqueLeases && raid.DifficultyMatches
        && raid.RosterCompositionValid && allAlive && !raid.EncounterInProgress
        && (previousWipeState != "wiped" || raid.NativeRecoveryEvidenceComplete);
}
