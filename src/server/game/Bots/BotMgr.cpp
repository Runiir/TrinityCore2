#include "Bots/BotMgr.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Chat.h"
#include "Config.h"
#include "DataStores/DBCStores.h"
#include "DataStores/DBCStructure.h"
#include "DatabaseEnv.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Entities/Unit/CharmInfo.h"
#include "GameClient.h"
#include "Group.h"
#include "GroupMgr.h"
#include "LFG.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Pet.h"
#include "Player.h"
#include "QueryHolder.h"
#include "SpellInfo.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "World.h"
#include "WorldSession.h"
#include <algorithm>
#include <memory>
#include <sstream>

BotMgr* BotMgr::instance()
{
    static BotMgr instance;
    return &instance;
}

void BotMgr::Update(uint32 diff)
{
    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
    {
        if (!_controllersByBot.empty())
            RemoveAll();
        return;
    }

    for (auto itr = _controllersByBot.begin(); itr != _controllersByBot.end();)
    {
        ObjectGuid botGuid = itr->first;
        if (_worldBots.find(botGuid) != _worldBots.end())
        {
            ++itr;
            continue;
        }

        Player* owner = FindLoadedPlayer(itr->second->GetOwnerGuid());
        Player* bot = FindLoadedPlayer(botGuid);
        if (!owner || !bot || owner->GetMap() != bot->GetMap())
        {
            ++itr;
            CleanupBot(botGuid, true);
            continue;
        }

        itr->second->Update(diff, _executor, owner, bot);
        ++itr;
    }
}

Player* BotMgr::Spawn(Player* owner, std::string const& role, std::string const& selector)
{
    if (!owner || !sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return nullptr;

    std::string normalizedRole = NormalizeBotRole(role);
    if (!IsKnownBotRole(normalizedRole) && !IsMixedBotRoleSelector(normalizedRole))
    {
        TC_LOG_ERROR("server", "PlayerBot spawn failed owner=%s role=%s reason=unknown_role", owner->GetGUID().ToString().c_str(), role.c_str());
        return nullptr;
    }

    TC_LOG_INFO("server", "PlayerBot spawn requested owner=%s role=%s selector=%s", owner->GetGUID().ToString().c_str(), normalizedRole.c_str(), selector.empty() ? "<auto>" : selector.c_str());
    Player* bot = LoadBotFromPool(owner, normalizedRole, selector);
    if (!bot)
    {
        TC_LOG_ERROR("server", "PlayerBot spawn failed owner=%s role=%s stage=load_from_pool", owner->GetGUID().ToString().c_str(), normalizedRole.c_str());
        return nullptr;
    }

    BotController const* controller = GetController(bot->GetGUID());
    BotRole botRole = controller ? controller->GetRole() : ParseBotRole(normalizedRole);
    std::string runtimeRole = controller ? controller->GetRuntimeRole() : normalizedRole;
    if (!AddToOwnerGroup(owner, bot, runtimeRole, botRole))
    {
        TC_LOG_ERROR("server", "PlayerBot spawn failed owner=%s bot=%s stage=add_to_group", owner->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str());
        Remove(owner, bot->GetGUID());
        return nullptr;
    }

    TC_LOG_INFO("server", "PlayerBot spawn complete owner=%s bot=%s name=%s", owner->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str(), bot->GetName().c_str());
    return bot;
}

Player* BotMgr::SpawnWorldBot(std::string const& role, std::string const& selector, uint32 mapId, float x, float y, float z, float o)
{
    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return nullptr;

    std::string normalizedRole = NormalizeBotRole(role);
    if (!IsKnownBotRole(normalizedRole) && !IsMixedBotRoleSelector(normalizedRole))
        return nullptr;

    BotSpawnPlacement placement = { mapId, x, y, z, o };
    Player* bot = LoadBotFromPool(nullptr, normalizedRole, selector, &placement);
    if (!bot)
        return nullptr;

    ObjectGuid botGuid = bot->GetGUID();
    bot->CastStop();
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    _worldBots.insert(botGuid);
    TC_LOG_INFO("server", "PlayerBot world spawn complete bot=%s name=%s map=%u position=%f,%f,%f", botGuid.ToString().c_str(), bot->GetName().c_str(), mapId, x, y, z);
    return bot;
}

Player* BotMgr::SpawnWorldBotInGroup(Player* groupAnchor, std::string const& role, std::string const& selector, uint32 mapId, float x, float y, float z, float o)
{
    if (!groupAnchor || !groupAnchor->GetGroup())
        return SpawnWorldBot(role, selector, mapId, x, y, z, o);

    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return nullptr;

    std::string normalizedRole = NormalizeBotRole(role);
    if (!IsKnownBotRole(normalizedRole) && !IsMixedBotRoleSelector(normalizedRole))
        return nullptr;

    BotSpawnPlacement placement = { mapId, x, y, z, o };
    Player* bot = LoadBotFromPool(nullptr, normalizedRole, selector, &placement, groupAnchor);
    if (!bot)
        return nullptr;

    ObjectGuid botGuid = bot->GetGUID();
    bot->CastStop();
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    _worldBots.insert(botGuid);
    TC_LOG_INFO("server", "PlayerBot world grouped spawn complete bot=%s name=%s leader=%s map=%u instance=%u position=%f,%f,%f",
        botGuid.ToString().c_str(), bot->GetName().c_str(), groupAnchor->GetGUID().ToString().c_str(), bot->GetMapId(), bot->GetInstanceId(), x, y, z);
    return bot;
}

Player* BotMgr::ProvisionWorldBot(std::string const& role, std::string const& selector, uint32 mapId,
    float x, float y, float z, float o, uint8 dungeonDifficulty, uint8 raidDifficulty)
{
    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false)
        || (dungeonDifficulty == NoProvisionedDungeonDifficulty
            && raidDifficulty == NoProvisionedRaidDifficulty)
        || (dungeonDifficulty != NoProvisionedDungeonDifficulty
            && dungeonDifficulty >= MAX_DUNGEON_DIFFICULTY)
        || (raidDifficulty != NoProvisionedRaidDifficulty
            && raidDifficulty >= MAX_RAID_DIFFICULTY))
        return nullptr;

    std::string normalizedRole = NormalizeBotRole(role);
    if (!IsKnownBotRole(normalizedRole) && !IsMixedBotRoleSelector(normalizedRole))
        return nullptr;

    BotSpawnPlacement placement = { mapId, x, y, z, o };
    Player* bot = LoadBotFromPool(nullptr, normalizedRole, selector, &placement,
        nullptr, dungeonDifficulty, raidDifficulty);
    if (!bot)
        return nullptr;

    ObjectGuid botGuid = bot->GetGUID();
    bot->CastStop();
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    _worldBots.insert(botGuid);
    TC_LOG_INFO("server", "PlayerBot server provision complete bot=%s name=%s map=%u instance=%u dungeon_difficulty=%u raid_difficulty=%u position=%f,%f,%f",
        botGuid.ToString().c_str(), bot->GetName().c_str(), bot->GetMapId(), bot->GetInstanceId(),
        uint32(dungeonDifficulty), uint32(raidDifficulty), x, y, z);
    return bot;
}

Player* BotMgr::ProvisionWorldBotRaidSeed(std::string const& role, std::string const& selector, uint32 mapId,
    float x, float y, float z, float o, uint8 raidDifficulty)
{
    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false)
        || raidDifficulty == NoProvisionedRaidDifficulty
        || raidDifficulty >= MAX_RAID_DIFFICULTY)
        return nullptr;

    std::string normalizedRole = NormalizeBotRole(role);
    if (!IsKnownBotRole(normalizedRole) && !IsMixedBotRoleSelector(normalizedRole))
        return nullptr;

    BotSpawnPlacement placement = { mapId, x, y, z, o };
    Player* bot = LoadBotFromPool(nullptr, normalizedRole, selector, &placement,
        nullptr, NoProvisionedDungeonDifficulty, raidDifficulty, true);
    if (!bot)
        return nullptr;

    ObjectGuid botGuid = bot->GetGUID();
    bot->CastStop();
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    _worldBots.insert(botGuid);
    TC_LOG_INFO("server", "PlayerBot raid seed provision complete bot=%s name=%s map=%u instance=%u raid_difficulty=%u position=%f,%f,%f",
        botGuid.ToString().c_str(), bot->GetName().c_str(), bot->GetMapId(), bot->GetInstanceId(),
        uint32(raidDifficulty), x, y, z);
    return bot;
}

Player* BotMgr::ProvisionWorldBotInGroup(Player* groupAnchor, std::string const& role, std::string const& selector,
    uint32 mapId, float x, float y, float z, float o, uint8 dungeonDifficulty, uint8 raidDifficulty)
{
    if (!groupAnchor || !groupAnchor->GetGroup())
        return ProvisionWorldBot(role, selector, mapId, x, y, z, o,
            dungeonDifficulty, raidDifficulty);

    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false)
        || (dungeonDifficulty == NoProvisionedDungeonDifficulty
            && raidDifficulty == NoProvisionedRaidDifficulty)
        || (dungeonDifficulty != NoProvisionedDungeonDifficulty
            && (dungeonDifficulty >= MAX_DUNGEON_DIFFICULTY
                || groupAnchor->GetGroup()->GetDungeonDifficulty() != Difficulty(dungeonDifficulty)))
        || (raidDifficulty != NoProvisionedRaidDifficulty
            && (raidDifficulty >= MAX_RAID_DIFFICULTY
                || groupAnchor->GetGroup()->GetRaidDifficulty() != Difficulty(raidDifficulty))))
        return nullptr;

    std::string normalizedRole = NormalizeBotRole(role);
    if (!IsKnownBotRole(normalizedRole) && !IsMixedBotRoleSelector(normalizedRole))
        return nullptr;

    BotSpawnPlacement placement = { mapId, x, y, z, o };
    Player* bot = LoadBotFromPool(nullptr, normalizedRole, selector, &placement,
        groupAnchor, dungeonDifficulty, raidDifficulty);
    if (!bot)
        return nullptr;

    ObjectGuid botGuid = bot->GetGUID();
    bot->CastStop();
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    _worldBots.insert(botGuid);
    TC_LOG_INFO("server", "PlayerBot server grouped provision complete bot=%s name=%s leader=%s map=%u instance=%u dungeon_difficulty=%u raid_difficulty=%u position=%f,%f,%f",
        botGuid.ToString().c_str(), bot->GetName().c_str(), groupAnchor->GetGUID().ToString().c_str(), bot->GetMapId(), bot->GetInstanceId(),
        uint32(dungeonDifficulty), uint32(raidDifficulty), x, y, z);
    return bot;
}

Player* BotMgr::SpawnWorldBotAtSavedPosition(std::string const& role, std::string const& selector)
{
    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return nullptr;

    std::string normalizedRole = NormalizeBotRole(role);
    if (!IsKnownBotRole(normalizedRole) && !IsMixedBotRoleSelector(normalizedRole))
        return nullptr;

    Player* bot = LoadBotFromPool(nullptr, normalizedRole, selector, nullptr);
    if (!bot)
        return nullptr;

    ObjectGuid botGuid = bot->GetGUID();
    bot->CastStop();
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    _worldBots.insert(botGuid);
    TC_LOG_INFO("server", "PlayerBot world spawn complete bot=%s name=%s map=%u source=saved_position position=%f,%f,%f",
        botGuid.ToString().c_str(), bot->GetName().c_str(), bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    return bot;
}

Player* BotMgr::SpawnHolyPaladin(Player* owner, std::string const& selector)
{
    return Spawn(owner, "holy_paladin", selector);
}

Player* BotMgr::GetOrLoadHeadlessOwner(std::string const& selector)
{
    if (selector.empty())
        return nullptr;

    ObjectGuid ownerGuid;
    uint32 accountId = 0;
    if (selector.find_first_not_of("0123456789") == std::string::npos)
    {
        ownerGuid = ObjectGuid(HighGuid::Player, uint32(atoul(selector.c_str())));
        if (QueryResult result = CharacterDatabase.PQuery("SELECT account FROM characters WHERE guid = %u", ownerGuid.GetCounter()))
            accountId = result->Fetch()[0].GetUInt32();
    }
    else
    {
        std::string escapedSelector = selector;
        CharacterDatabase.EscapeString(escapedSelector);
        if (QueryResult result = CharacterDatabase.PQuery("SELECT guid, account FROM characters WHERE name = '%s'", escapedSelector.c_str()))
        {
            Field* fields = result->Fetch();
            ownerGuid = ObjectGuid(HighGuid::Player, fields[0].GetUInt32());
            accountId = fields[1].GetUInt32();
        }
    }

    if (ownerGuid.IsEmpty() || !accountId)
    {
        TC_LOG_ERROR("server", "PlayerBot headless owner load failed selector=%s reason=not_found", selector.c_str());
        return nullptr;
    }

    if (Player* owner = FindLoadedPlayer(ownerGuid))
        return owner;

    TC_LOG_INFO("server", "PlayerBot headless owner load begin owner=%s account=%u", ownerGuid.ToString().c_str(), accountId);
    Player* owner = LoadCharacterAsBotSession(ownerGuid, accountId, nullptr);
    if (!owner)
    {
        TC_LOG_ERROR("server", "PlayerBot headless owner load failed owner=%s account=%u stage=load_character", ownerGuid.ToString().c_str(), accountId);
        return nullptr;
    }

    auto sessionItr = _botSessions.find(ownerGuid);
    if (sessionItr != _botSessions.end())
    {
        _headlessOwnerSessions[ownerGuid] = std::move(sessionItr->second);
        _botSessions.erase(sessionItr);
    }

    TC_LOG_INFO("server", "PlayerBot headless owner load complete owner=%s name=%s", ownerGuid.ToString().c_str(), owner->GetName().c_str());
    return owner;
}

void BotMgr::ReleaseHeadlessOwnerIfIdle(Player* owner)
{
    if (!owner || !GetOwnedBots(owner->GetGUID()).empty())
        return;

    auto sessionItr = _headlessOwnerSessions.find(owner->GetGUID());
    if (sessionItr == _headlessOwnerSessions.end())
        return;

    ObjectGuid ownerGuid = owner->GetGUID();
    owner->CombatStop(true);
    owner->CastStop();
    owner->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    owner->GetMotionMaster()->MoveIdle();
    if (Group* group = owner->GetGroup())
        group->RemoveMember(ownerGuid);

    if (owner->GetSession())
        owner->GetSession()->LogoutPlayer(false);

    SetBotCharacterOnline(ownerGuid, false);
    _headlessOwnerSessions.erase(sessionItr);
    TC_LOG_INFO("server", "PlayerBot headless owner released owner=%s", ownerGuid.ToString().c_str());
}

BotActionResult BotMgr::AddExistingHolyPaladin(Player* owner, Player* bot)
{
    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return BotActionResult::Disabled;

    if (!owner)
        return BotActionResult::NoOwner;
    if (!bot || !bot->IsAlive() || !bot->GetSession() || !bot->GetSession()->IsBotSession())
        return BotActionResult::NoBot;
    if (bot->GetMap() != owner->GetMap())
        return BotActionResult::NoBot;

    if (!AddToOwnerGroup(owner, bot, "healer", BotRole::HolyPaladinHealer))
        return BotActionResult::InvalidTarget;

    return BotActionResult::Ok;
}

std::vector<Player*> BotMgr::PartyFill(Player* owner, std::string const& partyType, std::string const& role)
{
    std::vector<Player*> spawned;
    std::string normalizedRole = NormalizeBotRole(role);
    if (!owner || stricmp(partyType.c_str(), "dungeon5") != 0 || (!IsKnownBotRole(normalizedRole) && !IsMixedBotRoleSelector(normalizedRole)))
        return spawned;

    Group* group = owner->GetGroup();
    uint32 currentSize = group ? group->GetMembersCount() : 1;
    while (currentSize < 5)
    {
        Player* bot = Spawn(owner, normalizedRole, "");
        if (!bot)
            break;

        spawned.push_back(bot);
        group = owner->GetGroup();
        currentSize = group ? group->GetMembersCount() : currentSize + 1;
    }

    return spawned;
}

uint32 BotMgr::Remove(Player* owner, std::string const& selector)
{
    uint32 removed = 0;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
        if (Remove(owner, botGuid))
            ++removed;

    return removed;
}

bool BotMgr::Remove(Player* owner, ObjectGuid botGuid)
{
    if (!owner || botGuid.IsEmpty() || GetOwnerGuid(botGuid) != owner->GetGUID() || _removingBots.find(botGuid) != _removingBots.end())
        return false;

    CleanupBot(botGuid, true);
    return true;
}

bool BotMgr::RemoveWorldBot(ObjectGuid botGuid)
{
    if (botGuid.IsEmpty() || _worldBots.find(botGuid) == _worldBots.end() || _removingBots.find(botGuid) != _removingBots.end())
        return false;

    CleanupBot(botGuid, true);
    return true;
}

uint32 BotMgr::SetMovement(Player* owner, BotMovementMode mode, std::string const& selector)
{
    uint32 changed = 0;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        if (BotController* controller = GetController(botGuid))
        {
            controller->SetMovementMode(mode);
            ++changed;
        }
    }

    return changed;
}

uint32 BotMgr::SetMoveTarget(Player* owner, float x, float y, float z, std::string const& selector)
{
    uint32 changed = 0;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        if (BotController* controller = GetController(botGuid))
        {
            controller->SetMoveTarget(x, y, z);
            ++changed;
        }
    }

    return changed;
}

uint32 BotMgr::SetCombatTarget(Player* owner, std::string const& targetSelector, std::string const& botSelector)
{
    Unit* target = ResolveHostileTarget(owner, targetSelector);
    if (!target)
        return 0;

    uint32 changed = 0;
    for (ObjectGuid botGuid : ResolveTargets(owner, botSelector))
    {
        if (BotController* controller = GetController(botGuid))
        {
            controller->SetCombatTarget(target->GetGUID());
            ++changed;
        }
    }

    return changed;
}

uint32 BotMgr::ClearCombatTarget(Player* owner, std::string const& selector)
{
    uint32 changed = 0;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        if (BotController* controller = GetController(botGuid))
        {
            controller->ClearCombatTarget();
            ++changed;
        }
    }

    return changed;
}

std::vector<BotRecipeScore> BotMgr::ScoreCookingRecipes(Player* owner, std::string const& selector) const
{
    std::vector<BotRecipeScore> scores;
    if (!owner)
        return scores;

    std::vector<ObjectGuid> botGuids = ResolveTargets(owner, selector);
    if (botGuids.empty())
        return scores;

    Player* bot = FindLoadedPlayer(botGuids.front());
    if (!bot || !bot->HasSkill(SKILL_COOKING))
        return scores;

    std::vector<SkillLineAbilityEntry const*> const* abilities = sDBCManager.GetSkillLineAbilitiesBySkill(SKILL_COOKING);
    if (!abilities)
        return scores;

    uint32 skill = bot->GetSkillValue(SKILL_COOKING);
    for (SkillLineAbilityEntry const* ability : *abilities)
    {
        if (!ability || !ability->Spell || ability->MinSkillLineRank > skill)
            continue;

        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(ability->Spell);
        if (!spellInfo)
            continue;

        BotRecipeScore score;
        score.RecipeSpellId = ability->Spell;
        score.Known = bot->HasSpell(ability->Spell);
        if (ability->TrivialSkillLineRankHigh && skill >= ability->TrivialSkillLineRankHigh)
            score.ExpectedSkillupValue = 0.0f;
        else if (ability->TrivialSkillLineRankLow && skill >= ability->TrivialSkillLineRankLow)
            score.ExpectedSkillupValue = 0.5f;
        else
            score.ExpectedSkillupValue = 1.0f;

        score.MaterialsAvailable = true;
        for (uint8 i = 0; i < MAX_SPELL_REAGENTS; ++i)
        {
            if (spellInfo->Reagent[i] <= 0)
                continue;

            uint32 required = spellInfo->ReagentCount[i];
            uint32 owned = bot->GetItemCount(uint32(spellInfo->Reagent[i]));
            score.MaterialCost += float(required);
            if (owned < required)
            {
                score.MaterialsAvailable = false;
                score.MaterialCost += float(required - owned) * 5.0f;
            }
        }

        score.RecipeAcquisitionCost = score.Known ? 0.0f : 25.0f;
        score.Score = score.ExpectedSkillupValue * 100.0f - score.MaterialCost - score.TravelCost - score.RecipeAcquisitionCost;
        scores.push_back(score);
    }

    std::sort(scores.begin(), scores.end(), [](BotRecipeScore const& left, BotRecipeScore const& right)
    {
        if (left.Score != right.Score)
            return left.Score > right.Score;
        return left.RecipeSpellId < right.RecipeSpellId;
    });

    return scores;
}
