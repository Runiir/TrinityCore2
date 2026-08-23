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

Group* BotMgr::FindSeedRaidGroupForLeader(ObjectGuid leaderGuid) const
{
    auto itr = _seedRaidGroupsByLeader.find(leaderGuid);
    if (itr == _seedRaidGroupsByLeader.end())
        return nullptr;

    Group* group = sGroupMgr->GetGroupByGUID(itr->second);
    return group && group->GetLeaderGUID() == leaderGuid ? group : nullptr;
}

void BotMgr::OnGroupDisband(Group* group)
{
    if (!group)
        return;

    for (auto itr = _seedRaidGroupsByLeader.begin(); itr != _seedRaidGroupsByLeader.end();)
    {
        if (itr->second == group->GetGUID().GetCounter())
            itr = _seedRaidGroupsByLeader.erase(itr);
        else
            ++itr;
    }

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
