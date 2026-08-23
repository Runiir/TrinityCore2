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

    // CleanupBot is the common teardown path, including headless world-bot
    // removal that bypasses BotWorldPopulationMgr.  Never let transient raid
    // damage authority survive reuse of the persistent character GUID.
    BotRaidAreaAuthority::Clear(botGuid.GetRawValue());
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
