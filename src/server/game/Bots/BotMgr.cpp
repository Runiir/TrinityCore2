#include "Bots/BotMgr.h"
#include "Chat.h"
#include "Config.h"
#include "DataStores/DBCStores.h"
#include "DataStores/DBCStructure.h"
#include "DatabaseEnv.h"
#include "Entities/Item/Container/Bag.h"
#include "Entities/Item/Item.h"
#include "Group.h"
#include "GroupMgr.h"
#include "LFG.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "QueryHolder.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "WorldSession.h"
#include <algorithm>
#include <memory>
#include <sstream>

namespace
{
float GetStatWeight(uint8 classId, uint32 statType)
{
    switch (classId)
    {
        case CLASS_WARRIOR:
        case CLASS_DEATH_KNIGHT:
            if (statType == ITEM_MOD_STRENGTH) return 2.0f;
            if (statType == ITEM_MOD_STAMINA) return 1.1f;
            break;
        case CLASS_HUNTER:
        case CLASS_ROGUE:
            if (statType == ITEM_MOD_AGILITY) return 2.0f;
            if (statType == ITEM_MOD_STAMINA) return 0.9f;
            break;
        case CLASS_MAGE:
        case CLASS_PRIEST:
        case CLASS_WARLOCK:
            if (statType == ITEM_MOD_INTELLECT) return 2.0f;
            if (statType == ITEM_MOD_SPIRIT) return 1.0f;
            if (statType == ITEM_MOD_STAMINA) return 0.7f;
            break;
        case CLASS_DRUID:
        case CLASS_SHAMAN:
        case CLASS_PALADIN:
            if (statType == ITEM_MOD_INTELLECT || statType == ITEM_MOD_STRENGTH || statType == ITEM_MOD_AGILITY) return 1.4f;
            if (statType == ITEM_MOD_STAMINA) return 1.0f;
            break;
        default:
            break;
    }

    switch (statType)
    {
        case ITEM_MOD_HIT_RATING:
        case ITEM_MOD_CRIT_RATING:
        case ITEM_MOD_HASTE_RATING:
        case ITEM_MOD_MASTERY_RATING:
            return 1.2f;
        case ITEM_MOD_STAMINA:
            return 0.8f;
        default:
            return 0.25f;
    }
}

float ScoreItemForBot(Player const* bot, ItemTemplate const* proto)
{
    if (!bot || !proto)
        return 0.0f;

    float score = float(proto->GetBaseItemLevel()) * 0.5f;
    for (uint32 i = 0; i < MAX_ITEM_PROTO_STATS; ++i)
    {
        int32 statValue = proto->GetItemStatValue(i);
        if (!statValue)
            continue;

        score += float(statValue) * GetStatWeight(bot->getClass(), uint32(proto->GetItemStatType(i)));
    }

    return score;
}

uint8 GetRepresentativeEquipSlot(uint8 inventoryType)
{
    switch (inventoryType)
    {
        case INVTYPE_HEAD: return EQUIPMENT_SLOT_HEAD;
        case INVTYPE_NECK: return EQUIPMENT_SLOT_NECK;
        case INVTYPE_SHOULDERS: return EQUIPMENT_SLOT_SHOULDERS;
        case INVTYPE_BODY: return EQUIPMENT_SLOT_BODY;
        case INVTYPE_CHEST:
        case INVTYPE_ROBE: return EQUIPMENT_SLOT_CHEST;
        case INVTYPE_WAIST: return EQUIPMENT_SLOT_WAIST;
        case INVTYPE_LEGS: return EQUIPMENT_SLOT_LEGS;
        case INVTYPE_FEET: return EQUIPMENT_SLOT_FEET;
        case INVTYPE_WRISTS: return EQUIPMENT_SLOT_WRISTS;
        case INVTYPE_HANDS: return EQUIPMENT_SLOT_HANDS;
        case INVTYPE_FINGER: return EQUIPMENT_SLOT_FINGER1;
        case INVTYPE_TRINKET: return EQUIPMENT_SLOT_TRINKET1;
        case INVTYPE_CLOAK: return EQUIPMENT_SLOT_BACK;
        case INVTYPE_WEAPON:
        case INVTYPE_2HWEAPON:
        case INVTYPE_WEAPONMAINHAND: return EQUIPMENT_SLOT_MAINHAND;
        case INVTYPE_WEAPONOFFHAND:
        case INVTYPE_SHIELD:
        case INVTYPE_HOLDABLE: return EQUIPMENT_SLOT_OFFHAND;
        case INVTYPE_RANGED:
        case INVTYPE_THROWN:
        case INVTYPE_RANGEDRIGHT:
        case INVTYPE_RELIC: return EQUIPMENT_SLOT_RANGED;
        case INVTYPE_TABARD: return EQUIPMENT_SLOT_TABARD;
        default: return EQUIPMENT_SLOT_END;
    }
}
}

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
    bot->CombatStop(true);
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
    bot->CombatStop(true);
    bot->CastStop();
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    _worldBots.insert(botGuid);
    TC_LOG_INFO("server", "PlayerBot world grouped spawn complete bot=%s name=%s leader=%s map=%u instance=%u position=%f,%f,%f",
        botGuid.ToString().c_str(), bot->GetName().c_str(), groupAnchor->GetGUID().ToString().c_str(), bot->GetMapId(), bot->GetInstanceId(), x, y, z);
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
    bot->CombatStop(true);
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

std::map<ObjectGuid, BotActionResult> BotMgr::CraftCookingRecipe(Player* owner, uint32 recipeSpellId, uint32 count, std::string const& selector)
{
    std::map<ObjectGuid, BotActionResult> results;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        Player* bot = FindLoadedPlayer(botGuid);
        results[botGuid] = _executor.CraftRecipe(owner, bot, recipeSpellId, count);
    }

    return results;
}

std::map<ObjectGuid, BotEconomyActionResult> BotMgr::VendorTrash(Player* owner, std::string const& selector)
{
    std::map<ObjectGuid, BotEconomyActionResult> results;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        Player* bot = FindLoadedPlayer(botGuid);
        results[botGuid] = _executor.VendorTrash(owner, bot);
    }

    return results;
}

std::map<ObjectGuid, BotEconomyActionResult> BotMgr::Repair(Player* owner, std::string const& selector)
{
    std::map<ObjectGuid, BotEconomyActionResult> results;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        Player* bot = FindLoadedPlayer(botGuid);
        results[botGuid] = _executor.Repair(owner, bot);
    }

    return results;
}

std::map<ObjectGuid, std::vector<BotGearEvaluation>> BotMgr::EvaluateGear(Player* owner, std::string const& selector) const
{
    std::map<ObjectGuid, std::vector<BotGearEvaluation>> results;
    for (ObjectGuid botGuid : ResolveTargets(owner, selector))
    {
        Player* bot = FindLoadedPlayer(botGuid);
        if (!bot)
            continue;

        std::vector<Item*> items;
        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            if (Item* item = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                items.push_back(item);

        for (uint8 bagSlot = INVENTORY_SLOT_BAG_START; bagSlot < INVENTORY_SLOT_BAG_END; ++bagSlot)
        {
            if (Bag* bag = bot->GetBagByPos(bagSlot))
                for (uint32 slot = 0; slot < bag->GetBagSize(); ++slot)
                    if (Item* item = bag->GetItemByPos(slot))
                        items.push_back(item);
        }

        std::vector<BotGearEvaluation>& evaluations = results[botGuid];
        for (Item* item : items)
        {
            ItemTemplate const* proto = item->GetTemplate();
            if (!proto || (proto->GetClass() != ITEM_CLASS_ARMOR && proto->GetClass() != ITEM_CLASS_WEAPON))
                continue;

            uint16 equipDest = 0;
            bool canEquip = bot->CanEquipItem(NULL_SLOT, equipDest, item, false) == EQUIP_ERR_OK;
            uint8 representativeSlot = GetRepresentativeEquipSlot(proto->GetInventoryType());
            float equippedScore = 0.0f;
            if (representativeSlot < EQUIPMENT_SLOT_END)
                if (Item* equipped = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, representativeSlot))
                    equippedScore = ScoreItemForBot(bot, equipped->GetTemplate());

            BotGearEvaluation evaluation;
            evaluation.ItemId = item->GetEntry();
            evaluation.Bag = item->GetBagSlot();
            evaluation.Slot = item->GetSlot();
            evaluation.Quality = proto->GetQuality();
            evaluation.InventoryType = proto->GetInventoryType();
            evaluation.Score = ScoreItemForBot(bot, proto);
            evaluation.EquippedScore = equippedScore;

            if (canEquip && representativeSlot < EQUIPMENT_SLOT_END && evaluation.Score > equippedScore + 0.5f)
                evaluation.Decision = "equip";
            else if (proto->GetQuality() == ITEM_QUALITY_POOR || (!canEquip && proto->GetSellPrice() > 0))
                evaluation.Decision = "vendor";
            else
                evaluation.Decision = "keep";

            evaluations.push_back(evaluation);
        }

        std::sort(evaluations.begin(), evaluations.end(), [](BotGearEvaluation const& left, BotGearEvaluation const& right)
        {
            if (left.Decision != right.Decision)
                return left.Decision < right.Decision;
            return left.Score > right.Score;
        });
    }

    return results;
}

bool BotMgr::SetRecording(Player* owner, bool enabled)
{
    bool changed = false;
    for (ObjectGuid botGuid : GetOwnedBots(owner ? owner->GetGUID() : ObjectGuid::Empty))
    {
        if (BotController* controller = GetController(botGuid))
        {
            controller->SetRecording(enabled);
            changed = true;
        }
    }

    return changed;
}

std::string BotMgr::GetStatus(Player* owner) const
{
    std::vector<ObjectGuid> botGuids = GetOwnedBots(owner ? owner->GetGUID() : ObjectGuid::Empty);
    std::ostringstream ss;
    ss << "{\"ok\":true,\"count\":" << botGuids.size() << ",\"bots\":[";
    bool first = true;
    for (ObjectGuid botGuid : botGuids)
    {
        if (BotController const* controller = GetController(botGuid))
        {
            if (!first)
                ss << ',';
            ss << controller->GetStatus(FindLoadedPlayer(controller->GetOwnerGuid()), FindLoadedPlayer(botGuid));
            first = false;
        }
    }

    ss << "],\"failure_reason\":null}";
    return ss.str();
}

char const* BotMgr::GetBotRoleName(ObjectGuid botGuid) const
{
    if (BotController const* controller = GetController(botGuid))
        return ToString(controller->GetRole());

    return "unknown";
}

Player* BotMgr::GetLoadedPlayer(ObjectGuid guid) const
{
    return FindLoadedPlayer(guid);
}

BotRecentEvents BotMgr::ConsumeRecentEvents(ObjectGuid botGuid)
{
    BotRecentEvents events;
    auto itr = _recentEventsByBot.find(botGuid);
    if (itr == _recentEventsByBot.end())
        return events;

    events = itr->second;
    _recentEventsByBot.erase(itr);
    return events;
}

void BotMgr::OnOwnerLogout(Player* owner)
{
    if (owner && !IsOwnedBot(owner->GetGUID()))
        Remove(owner, "all");
}

void BotMgr::OnGroupRemoveMember(Group* /*group*/, ObjectGuid guid)
{
    if (IsOwnedBot(guid))
    {
        if (_removingBots.find(guid) != _removingBots.end())
            return;

        if (Player* owner = FindLoadedPlayer(GetOwnerGuid(guid)))
            Remove(owner, guid);
        return;
    }

    if (Player* owner = FindLoadedPlayer(guid))
        Remove(owner, "all");
}

void BotMgr::OnGroupDisband(Group* group)
{
    if (!group)
        return;

    std::vector<Player*> ownersToClean;
    for (auto const& ownerBots : _botsByOwner)
    {
        if (Player* owner = FindLoadedPlayer(ownerBots.first))
            if (owner->GetGroup() == group)
                ownersToClean.push_back(owner);
    }

    std::sort(ownersToClean.begin(), ownersToClean.end());
    ownersToClean.erase(std::unique(ownersToClean.begin(), ownersToClean.end()), ownersToClean.end());
    for (Player* owner : ownersToClean)
        Remove(owner, "all");
}

void BotMgr::RemoveAll()
{
    TC_LOG_INFO("server", "PlayerBot remove all begin controllers=%zu world_bots=%zu sessions=%zu headless_owners=%zu",
        _controllersByBot.size(), _worldBots.size(), _botSessions.size(), _headlessOwnerSessions.size());

    std::vector<ObjectGuid> botGuids;
    for (auto const& controller : _controllersByBot)
        botGuids.push_back(controller.first);
    for (ObjectGuid botGuid : _worldBots)
        if (std::find(botGuids.begin(), botGuids.end(), botGuid) == botGuids.end())
            botGuids.push_back(botGuid);

    for (ObjectGuid botGuid : botGuids)
    {
        ObjectGuid ownerGuid = GetOwnerGuid(botGuid);
        if (Player* owner = FindLoadedPlayer(ownerGuid))
            Remove(owner, botGuid);
        else
            CleanupBot(botGuid, true);
    }

    while (!_headlessOwnerSessions.empty())
        if (Player* owner = FindLoadedPlayer(_headlessOwnerSessions.begin()->first))
            ReleaseHeadlessOwnerIfIdle(owner);
        else
            _headlessOwnerSessions.erase(_headlessOwnerSessions.begin());

    TC_LOG_INFO("server", "PlayerBot remove all complete controllers=%zu world_bots=%zu sessions=%zu headless_owners=%zu",
        _controllersByBot.size(), _worldBots.size(), _botSessions.size(), _headlessOwnerSessions.size());
}

void BotMgr::ResetPoolUseState()
{
    if (!sConfigMgr->GetBoolDefault("PlayerBot.Enable", false))
        return;

    CharacterDatabase.Execute("UPDATE character_bot_pool SET in_use = 0");
}

void BotMgr::OnDamage(Unit* /*attacker*/, Unit* victim, uint32 damage)
{
    if (damage && victim)
    {
        ObjectGuid victimGuid = victim->GetGUID();
        for (auto const& controller : _controllersByBot)
        {
            ObjectGuid botGuid = controller.first;
            if (!IsTrackedPartyMember(botGuid, victimGuid))
                continue;

            BotRecentEvents& events = _recentEventsByBot[botGuid];
            events.PartyDamageTaken[victimGuid] += damage;
            if (victimGuid == botGuid)
                events.DamageTaken += damage;
        }
    }

    if (damage && victim && sConfigMgr->GetBoolDefault("PlayerBot.Debug", false))
        TC_LOG_DEBUG("entities.unit", "PlayerBot recorder hook damage victim=%s amount=%u", victim->GetGUID().ToString().c_str(), damage);
}

void BotMgr::OnHeal(Unit* healer, Unit* receiver, uint32 gain)
{
    if (gain && receiver)
    {
        ObjectGuid healerGuid = healer ? healer->GetGUID() : ObjectGuid::Empty;
        ObjectGuid receiverGuid = receiver->GetGUID();
        for (auto const& controller : _controllersByBot)
        {
            ObjectGuid botGuid = controller.first;
            if (!IsTrackedPartyMember(botGuid, receiverGuid) && healerGuid != botGuid)
                continue;

            BotRecentEvents& events = _recentEventsByBot[botGuid];
            if (IsTrackedPartyMember(botGuid, receiverGuid))
                events.PartyHealingReceived[receiverGuid] += gain;
            if (receiverGuid == botGuid)
                events.HealingReceived += gain;
            if (healerGuid == botGuid)
                events.HealingDone += gain;
        }
    }

    if (gain && healer && receiver && sConfigMgr->GetBoolDefault("PlayerBot.Debug", false))
        TC_LOG_DEBUG("entities.unit", "PlayerBot recorder hook heal healer=%s receiver=%s amount=%u", healer->GetGUID().ToString().c_str(), receiver->GetGUID().ToString().c_str(), gain);
}

BotController* BotMgr::GetController(ObjectGuid botGuid)
{
    auto itr = _controllersByBot.find(botGuid);
    return itr != _controllersByBot.end() ? itr->second.get() : nullptr;
}

BotController const* BotMgr::GetController(ObjectGuid botGuid) const
{
    auto itr = _controllersByBot.find(botGuid);
    return itr != _controllersByBot.end() ? itr->second.get() : nullptr;
}

Player* BotMgr::FindLoadedPlayer(ObjectGuid guid) const
{
    auto botSessionItr = _botSessions.find(guid);
    if (botSessionItr != _botSessions.end() && botSessionItr->second)
        if (Player* player = botSessionItr->second->GetPlayer())
            return player;

    auto ownerSessionItr = _headlessOwnerSessions.find(guid);
    if (ownerSessionItr != _headlessOwnerSessions.end() && ownerSessionItr->second)
        if (Player* player = ownerSessionItr->second->GetPlayer())
            return player;

    return ObjectAccessor::FindPlayer(guid);
}

std::vector<ObjectGuid> BotMgr::GetOwnedBots(ObjectGuid ownerGuid) const
{
    std::vector<ObjectGuid> botGuids;
    auto range = _botsByOwner.equal_range(ownerGuid);
    for (auto itr = range.first; itr != range.second; ++itr)
        botGuids.push_back(itr->second);

    return botGuids;
}

std::vector<ObjectGuid> BotMgr::ResolveTargets(Player* owner, std::string const& selector) const
{
    std::vector<ObjectGuid> botGuids;
    if (!owner)
        return botGuids;

    if (selector.empty() || stricmp(selector.c_str(), "all") == 0)
        return GetOwnedBots(owner->GetGUID());

    for (ObjectGuid botGuid : GetOwnedBots(owner->GetGUID()))
    {
        if (selector.find_first_not_of("0123456789") == std::string::npos && botGuid.GetCounter() == uint32(atoul(selector.c_str())))
            botGuids.push_back(botGuid);
        else if (Player* bot = FindLoadedPlayer(botGuid))
            if (stricmp(bot->GetName().c_str(), selector.c_str()) == 0 || bot->GetGUID().ToString() == selector)
                botGuids.push_back(botGuid);
    }

    return botGuids;
}

Unit* BotMgr::ResolveHostileTarget(Player* owner, std::string const& targetSelector) const
{
    if (!owner)
        return nullptr;

    Unit* target = nullptr;
    if (targetSelector.empty() || stricmp(targetSelector.c_str(), "selected") == 0)
        target = owner->GetSelectedUnit();
    else if (stricmp(targetSelector.c_str(), "nearest") == 0)
        target = owner->SelectNearbyTarget(nullptr, 40.0f);
    else if (targetSelector.find_first_not_of("0123456789") == std::string::npos)
        target = ObjectAccessor::GetUnit(*owner, ObjectGuid(HighGuid::Unit, uint32(atoul(targetSelector.c_str()))));

    if (!target || !owner->IsValidAttackTarget(target))
        return nullptr;
    return target;
}

bool BotMgr::IsOwnedBot(ObjectGuid botGuid) const
{
    return _ownerByBot.find(botGuid) != _ownerByBot.end();
}

ObjectGuid BotMgr::GetOwnerGuid(ObjectGuid botGuid) const
{
    auto itr = _ownerByBot.find(botGuid);
    return itr != _ownerByBot.end() ? itr->second : ObjectGuid::Empty;
}

bool BotMgr::IsTrackedPartyMember(ObjectGuid botGuid, ObjectGuid unitGuid) const
{
    if (unitGuid.IsEmpty() || botGuid.IsEmpty())
        return false;

    if (unitGuid == botGuid)
        return true;

    ObjectGuid ownerGuid = GetOwnerGuid(botGuid);
    if (unitGuid == ownerGuid)
        return true;

    Player* owner = FindLoadedPlayer(ownerGuid);
    if (!owner || !owner->GetGroup())
        return false;

    return owner->GetGroup()->IsMember(unitGuid);
}

Player* BotMgr::LoadBotFromPool(Player* owner, std::string const& role, std::string const& selector, BotSpawnPlacement const* placement, Player* groupAnchor)
{
    std::string normalizedRole = NormalizeBotRole(role);
    bool mixedRole = IsMixedBotRoleSelector(normalizedRole);
    std::string escapedRole = normalizedRole;
    CharacterDatabase.EscapeString(escapedRole);

    std::string selectorClause;
    if (!selector.empty())
    {
        if (selector.find_first_not_of("0123456789") == std::string::npos)
            selectorClause = " AND cbp.guid = " + selector;
        else
        {
            std::string escapedSelector = selector;
            CharacterDatabase.EscapeString(escapedSelector);
            selectorClause = " AND c.name = '" + escapedSelector + "'";
        }
    }

    std::string roleClause = mixedRole ? "" : " AND cbp.role = '" + escapedRole + "'";
    std::string query = "SELECT cbp.guid, c.account, cbp.role, cbp.class_spec FROM character_bot_pool cbp INNER JOIN characters c ON c.guid = cbp.guid WHERE cbp.enabled = 1 AND cbp.in_use = 0" + roleClause + selectorClause + " ORDER BY cbp.guid LIMIT 1";
    QueryResult result = CharacterDatabase.Query(query.c_str());
    if (!result)
    {
        TC_LOG_ERROR("server", "PlayerBot load failed role=%s selector=%s reason=no_available_pool_character", normalizedRole.c_str(), selector.empty() ? "<auto>" : selector.c_str());
        return nullptr;
    }

    Field* fields = result->Fetch();
    ObjectGuid botGuid(HighGuid::Player, fields[0].GetUInt32());
    uint32 accountId = fields[1].GetUInt32();
    std::string selectedRole = fields[2].GetString();
    std::string selectedClassSpec = fields[3].GetString();
    BotRole botRole = ParseBotRole(selectedRole);
    TC_LOG_INFO("server", "PlayerBot load selected bot=%s account=%u role=%s class_spec=%s", botGuid.ToString().c_str(), accountId, selectedRole.c_str(), selectedClassSpec.c_str());

    if (Player* loadedBot = FindLoadedPlayer(botGuid))
    {
        bool managedAsWorldBotOrSession = _worldBots.find(botGuid) != _worldBots.end() || _botSessions.find(botGuid) != _botSessions.end();
        TC_LOG_ERROR("server", "PlayerBot load skipped bot=%s name=%s role=%s selector=%s reason=pool_character_already_loaded managed=%u in_world=%u map=%u",
            botGuid.ToString().c_str(), loadedBot->GetName().c_str(), selectedRole.c_str(), selector.empty() ? "<auto>" : selector.c_str(),
            managedAsWorldBotOrSession ? 1 : 0, loadedBot->IsInWorld() ? 1 : 0, loadedBot->GetMapId());

        if (managedAsWorldBotOrSession)
            CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 1 WHERE guid = %u", botGuid.GetCounter());
        else
            CleanupBot(botGuid, true);

        return nullptr;
    }

    Player* bot = LoadCharacterAsBotSession(botGuid, accountId, owner, placement, groupAnchor);
    if (!bot)
        return nullptr;

    CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 1 WHERE guid = %u", botGuid.GetCounter());
    auto sessionItr = _botSessions.find(botGuid);
    if (sessionItr == _botSessions.end())
        return nullptr;

    std::unique_ptr<WorldSession> session = std::move(sessionItr->second);
    _botSessions.erase(sessionItr);
    Register(owner, bot, botRole, selectedRole, selectedClassSpec, std::move(session));
    return bot;
}

Player* BotMgr::LoadCharacterAsBotSession(ObjectGuid guid, uint32 accountId, Player* nearPlayer, BotSpawnPlacement const* placement, Player* groupAnchor)
{
    uint8 expansion = nearPlayer && nearPlayer->GetSession() ? nearPlayer->GetSession()->GetExpansion() : uint8(sWorld->getIntConfig(CONFIG_EXPANSION));
    LocaleConstant locale = nearPlayer && nearPlayer->GetSession() ? nearPlayer->GetSession()->GetSessionDbcLocale() : LOCALE_enUS;
    std::unique_ptr<WorldSession> session(new WorldSession(accountId, "playerbot", nullptr, SEC_PLAYER, expansion, 0, locale, 0, false, true));
    std::shared_ptr<LoginQueryHolder> holder = std::make_shared<LoginQueryHolder>(accountId, guid);
    if (!holder->Initialize())
    {
        TC_LOG_ERROR("server", "PlayerBot load failed character=%s stage=query_holder_initialize", guid.ToString().c_str());
        return nullptr;
    }

    SQLQueryHolderCallback queryCallback = CharacterDatabase.DelayQueryHolder(holder);
    queryCallback.m_future.get();

    Player* bot = new Player(session.get());
    if (!bot->LoadFromDB(guid, *holder))
    {
        TC_LOG_ERROR("server", "PlayerBot load failed character=%s stage=load_from_db", guid.ToString().c_str());
        delete bot;
        return nullptr;
    }
    TC_LOG_INFO("server", "PlayerBot load_from_db complete character=%s name=%s", guid.ToString().c_str(), bot->GetName().c_str());

    bot->GetMotionMaster()->Initialize();
    bot->SetFullHealth();
    bot->SetFullPower(POWER_MANA);
    session->SetPlayer(bot);

    Group* prejoinedGroup = groupAnchor ? groupAnchor->GetGroup() : nullptr;
    if (prejoinedGroup && !bot->GetGroup())
    {
        if (!prejoinedGroup->AddMember(bot))
        {
            TC_LOG_ERROR("server", "PlayerBot load failed character=%s stage=prejoin_group group=%s", guid.ToString().c_str(), prejoinedGroup->GetGUID().ToString().c_str());
            session->SetPlayer(nullptr);
            delete bot;
            return nullptr;
        }
    }

    if (placement)
    {
        if (bot->FindMap())
            bot->ResetMap();
        bot->SetMap(sMapMgr->CreateMap(placement->MapId, bot));
        bot->Relocate(placement->X, placement->Y, placement->Z, placement->O);
    }
    else if (nearPlayer)
    {
        Position pos = nearPlayer->GetNearPosition(2.5f, float(M_PI) / 2.0f);
        if (bot->FindMap() && bot->FindMap() != nearPlayer->GetMap())
            bot->ResetMap();
        if (!bot->FindMap())
            bot->SetMap(nearPlayer->GetMap());
        bot->Relocate(pos);
    }
    else if (!bot->FindMap())
        bot->SetMap(sMapMgr->CreateMap(bot->GetMapId(), bot));

    if (!bot->GetMap() || !bot->GetMap()->AddPlayerToMap(bot))
    {
        TC_LOG_ERROR("server", "PlayerBot load failed character=%s stage=add_player_to_map map=%u", guid.ToString().c_str(), bot->GetMapId());
        if (prejoinedGroup && bot->GetGroup() == prejoinedGroup)
            prejoinedGroup->RemoveMember(bot->GetGUID());
        session->SetPlayer(nullptr);
        delete bot;
        return nullptr;
    }
    TC_LOG_INFO("server", "PlayerBot add_to_map complete character=%s map=%u", guid.ToString().c_str(), bot->GetMapId());

    ObjectAccessor::AddObject(bot);
    TC_LOG_INFO("server", "PlayerBot object_accessor_add complete character=%s", guid.ToString().c_str());

    bot->LoadPetsFromDB(holder->GetPreparedResult(PLAYER_LOGIN_QUERY_LOAD_ALL_PETS));
    if (bot->getClass() == CLASS_HUNTER && !bot->GetPlayerPetDataCurrent())
    {
        for (uint8 slot = PET_SLOT_FIRST_ACTIVE_SLOT; slot <= PET_SLOT_LAST_ACTIVE_SLOT; ++slot)
        {
            PlayerPetData* petData = bot->GetPlayerPetDataBySlot(slot);
            if (!petData || petData->Type != HUNTER_PET)
                continue;

            petData->Active = true;
            TC_LOG_INFO("server", "PlayerBot hunter active-slot pet selected character=%s pet_id=%u entry=%u slot=%u",
                guid.ToString().c_str(), petData->PetId, petData->CreatureId, petData->Slot);
            break;
        }
    }
    if (bot->IsMounted())
    {
        bot->RemoveAurasByType(SPELL_AURA_MOUNTED);
        if (bot->IsMounted())
            bot->Dismount();
        TC_LOG_INFO("server", "PlayerBot dismounted before pet load character=%s", guid.ToString().c_str());
    }
    bot->LoadPet();
    Pet* loadedPet = bot->GetPet();
    std::string petGuid = loadedPet ? loadedPet->GetGUID().ToString() : ObjectGuid::Empty.ToString();
    TC_LOG_INFO("server", "PlayerBot pets loaded character=%s pet=%s",
        guid.ToString().c_str(), petGuid.c_str());

    bot->UpdateObjectVisibility(true);
    if (Map* map = bot->GetMap())
    {
        Map::PlayerList const& players = map->GetPlayers();
        for (Map::PlayerList::const_iterator itr = players.begin(); itr != players.end(); ++itr)
        {
            Player* player = itr->GetSource();
            if (!player || player == bot || !player->IsInWorld() || player->GetMap() != map)
                continue;

            WorldSession* session = player->GetSession();
            if (!session || session->IsBotSession())
                continue;

            if (!bot->IsWithinDistInMap(player, bot->GetVisibilityRange()))
                continue;

            player->UpdateVisibilityOf(bot);
        }
    }
    TC_LOG_INFO("server", "PlayerBot visibility refresh complete character=%s", guid.ToString().c_str());
    SetBotCharacterOnline(guid, true);
    _botSessions[guid] = std::move(session);
    return bot;
}

bool BotMgr::AddToOwnerGroup(Player* owner, Player* bot, std::string const& runtimeRole, BotRole role)
{
    TC_LOG_INFO("server", "PlayerBot group add begin owner=%s bot=%s", owner->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str());
    Group* group = owner->GetGroup();
    if (!group)
    {
        group = new Group();
        if (!group->Create(owner))
        {
            TC_LOG_ERROR("server", "PlayerBot group add failed owner=%s bot=%s stage=create_owner_group", owner->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str());
            delete group;
            return false;
        }

        sGroupMgr->AddGroup(group);
        TC_LOG_INFO("server", "PlayerBot group created owner=%s group=%s", owner->GetGUID().ToString().c_str(), group->GetGUID().ToString().c_str());
    }

    if (!group->AddMember(bot))
    {
        TC_LOG_ERROR("server", "PlayerBot group add failed owner=%s bot=%s group=%s stage=add_member", owner->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str(), group->GetGUID().ToString().c_str());
        return false;
    }

    std::string normalizedRole = NormalizeBotRole(runtimeRole);
    if (normalizedRole == "tank")
        group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_TANK);
    else if (normalizedRole == "healer" || normalizedRole == "heal")
        group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_HEALER);
    else if (normalizedRole == "dps" || normalizedRole == "damage")
        group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_DAMAGE);
    else switch (GetBotRoleCategory(role))
    {
        case BotRoleCategory::Tank:
            group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_TANK);
            break;
        case BotRoleCategory::Healer:
            group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_HEALER);
            break;
        case BotRoleCategory::Damage:
        default:
            group->SetLfgRoles(bot->GetGUID(), lfg::PLAYER_ROLE_DAMAGE);
            break;
    }

    bot->GetMotionMaster()->MoveFollow(owner, 3.5f, float(M_PI) / 2.0f);
    TC_LOG_INFO("server", "PlayerBot group add complete owner=%s bot=%s group=%s", owner->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str(), group->GetGUID().ToString().c_str());
    return true;
}

void BotMgr::CleanupBot(ObjectGuid botGuid, bool logoutPlayer)
{
    if (botGuid.IsEmpty() || _removingBots.find(botGuid) != _removingBots.end())
        return;

    TC_LOG_INFO("server", "PlayerBot cleanup begin bot=%s logout=%u", botGuid.ToString().c_str(), logoutPlayer ? 1 : 0);
    _removingBots.insert(botGuid);
    if (logoutPlayer)
    {
        if (Player* bot = FindLoadedPlayer(botGuid))
        {
            bot->CombatStop(true);
            bot->CastStop();
            bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            bot->GetMotionMaster()->MoveIdle();
            if (Group* group = bot->GetGroup())
                group->RemoveMember(botGuid);

            if (bot->GetSession())
                bot->GetSession()->LogoutPlayer(false);
        }
    }

    _executor.ResetThrottle(botGuid);
    _ownerByBot.erase(botGuid);
    for (auto itr = _botsByOwner.begin(); itr != _botsByOwner.end();)
    {
        if (itr->second == botGuid)
            itr = _botsByOwner.erase(itr);
        else
            ++itr;
    }

    _controllersByBot.erase(botGuid);
    _botSessions.erase(botGuid);
    _worldBots.erase(botGuid);
    _recentEventsByBot.erase(botGuid);
    SetBotCharacterOnline(botGuid, false);
    ReleasePoolCharacter(botGuid);
    _removingBots.erase(botGuid);
    TC_LOG_INFO("server", "PlayerBot cleanup complete bot=%s sessions=%zu world_bots=%zu", botGuid.ToString().c_str(), _botSessions.size(), _worldBots.size());
}

void BotMgr::SetBotCharacterOnline(ObjectGuid botGuid, bool online)
{
    CharacterDatabase.DirectPExecute("UPDATE characters SET online = %u WHERE guid = %u", online ? 1 : 0, botGuid.GetCounter());
}

void BotMgr::ReleasePoolCharacter(ObjectGuid botGuid)
{
    CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", botGuid.GetCounter());
}

void BotMgr::Register(Player* owner, Player* bot, BotRole role, std::string const& runtimeRole, std::string const& classSpec, std::unique_ptr<WorldSession> session)
{
    _botSessions[bot->GetGUID()] = std::move(session);
    if (!owner)
    {
        _worldBots.insert(bot->GetGUID());
        return;
    }

    _ownerByBot[bot->GetGUID()] = owner->GetGUID();
    _botsByOwner.emplace(owner->GetGUID(), bot->GetGUID());
    _controllersByBot[bot->GetGUID()].reset(new BotController(owner->GetGUID(), bot->GetGUID(), role, runtimeRole, classSpec));
}
