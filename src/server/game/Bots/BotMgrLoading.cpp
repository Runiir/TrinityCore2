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

Player* BotMgr::LoadBotFromPool(Player* owner, std::string const& role, std::string const& selector, BotSpawnPlacement const* placement,
    Player* groupAnchor, uint8 provisionedDungeonDifficulty, uint8 provisionedRaidDifficulty, bool seedRaidLeader)
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

    Player* bot = LoadCharacterAsBotSession(botGuid, accountId, owner, placement,
        groupAnchor, provisionedDungeonDifficulty, provisionedRaidDifficulty, seedRaidLeader);
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

Player* BotMgr::LoadCharacterAsBotSession(ObjectGuid guid, uint32 accountId, Player* nearPlayer, BotSpawnPlacement const* placement,
    Player* groupAnchor, uint8 provisionedDungeonDifficulty, uint8 provisionedRaidDifficulty, bool seedRaidLeader)
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
    session->SetPlayer(bot);

    if (provisionedDungeonDifficulty != NoProvisionedDungeonDifficulty)
    {
        if (!placement || provisionedDungeonDifficulty >= MAX_DUNGEON_DIFFICULTY)
        {
            TC_LOG_ERROR("server", "PlayerBot provision failed character=%s stage=invalid_server_provisioning_difficulty difficulty=%u",
                guid.ToString().c_str(), uint32(provisionedDungeonDifficulty));
            session->SetPlayer(nullptr);
            delete bot;
            return nullptr;
        }

        // This is run-controller provisioning, before the bot is registered or
        // allowed to make decisions. It is deliberately not a bot-session
        // opcode and cannot be reached by the active action scheduler.
        bot->SetDungeonDifficulty(Difficulty(provisionedDungeonDifficulty));
    }
    if (provisionedRaidDifficulty != NoProvisionedRaidDifficulty)
    {
        if (!placement || provisionedRaidDifficulty >= MAX_RAID_DIFFICULTY)
        {
            TC_LOG_ERROR("server", "PlayerBot provision failed character=%s stage=invalid_server_provisioning_raid_difficulty difficulty=%u",
                guid.ToString().c_str(), uint32(provisionedRaidDifficulty));
            session->SetPlayer(nullptr);
            delete bot;
            return nullptr;
        }

        bot->SetRaidDifficulty(Difficulty(provisionedRaidDifficulty));
    }

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

    if (provisionedDungeonDifficulty != NoProvisionedDungeonDifficulty && prejoinedGroup
        && (!bot->GetGroup() || bot->GetGroup()->GetDungeonDifficulty() != Difficulty(provisionedDungeonDifficulty)))
    {
        TC_LOG_ERROR("server", "PlayerBot provision failed character=%s stage=provisioned_group_difficulty_mismatch expected=%u",
            guid.ToString().c_str(), uint32(provisionedDungeonDifficulty));
        if (prejoinedGroup && bot->GetGroup() == prejoinedGroup)
            prejoinedGroup->RemoveMember(bot->GetGUID());
        session->SetPlayer(nullptr);
        delete bot;
        return nullptr;
    }
    if (provisionedRaidDifficulty != NoProvisionedRaidDifficulty && prejoinedGroup
        && (!bot->GetGroup() || bot->GetGroup()->GetRaidDifficulty() != Difficulty(provisionedRaidDifficulty)))
    {
        TC_LOG_ERROR("server", "PlayerBot provision failed character=%s stage=provisioned_group_raid_difficulty_mismatch expected=%u",
            guid.ToString().c_str(), uint32(provisionedRaidDifficulty));
        if (prejoinedGroup && bot->GetGroup() == prejoinedGroup)
            prejoinedGroup->RemoveMember(bot->GetGUID());
        session->SetPlayer(nullptr);
        delete bot;
        return nullptr;
    }

    if (placement)
    {
        Map::EnterState denyReason = Map::PlayerCannotEnter(placement->MapId, bot, false);
        if (denyReason == Map::CANNOT_ENTER_NOT_IN_RAID && seedRaidLeader)
        {
            // A validation raid admission seeds its cohort with the first
            // planned member. The raid forms here so the leader's own entry
            // creates the one native instance every later member joins.
            bool seedDiverged = false;
            if (Group* seed = new Group())
            {
                if (seed->Create(bot))
                {
                    sGroupMgr->AddGroup(seed);
                    seed->ConvertToRaid();
                    if (bot->GetGroup() == seed)
                    {
                        _seedRaidGroupsByLeader[guid] = seed->GetGUID().GetCounter();
                        TC_LOG_INFO("server", "PlayerBot raid seed group created leader=%s group=%s map=%u",
                            guid.ToString().c_str(), seed->GetGUID().ToString().c_str(), placement->MapId);
                    }
                    else
                    {
                        std::string const memberGroupGuid = bot->GetGroup()
                            ? bot->GetGroup()->GetGUID().ToString()
                            : ObjectGuid::Empty.ToString();
                        TC_LOG_ERROR("server", "PlayerBot raid seed group diverged leader=%s seed=%s member_group=%s",
                            guid.ToString().c_str(), seed->GetGUID().ToString().c_str(),
                            memberGroupGuid.c_str());
                        sGroupMgr->RemoveGroup(seed);
                        delete seed;
                        seedDiverged = true;
                    }
                }
                else
                    delete seed;
            }
            if (!seedDiverged)
                denyReason = Map::PlayerCannotEnter(placement->MapId, bot, false);
        }
        if (denyReason != Map::CAN_ENTER)
        {
            TC_LOG_ERROR("server", "PlayerBot placement failed character=%s stage=player_cannot_enter map=%u reason=%u",
                guid.ToString().c_str(), placement->MapId, uint32(denyReason));
            bot->RemoveAllAuras();
            if (prejoinedGroup && bot->GetGroup() == prejoinedGroup)
                prejoinedGroup->RemoveMember(bot->GetGUID());
            session->SetPlayer(nullptr);
            delete bot;
            return nullptr;
        }
        if (bot->FindMap())
            bot->ResetMap();
        Map* destinationMap = sMapMgr->CreateMap(placement->MapId, bot);
        if (!destinationMap || destinationMap->CannotEnter(bot))
        {
            TC_LOG_ERROR("server", "PlayerBot placement failed character=%s stage=destination_map_rejected map=%u",
                guid.ToString().c_str(), placement->MapId);
            bot->RemoveAllAuras();
            if (prejoinedGroup && bot->GetGroup() == prejoinedGroup)
                prejoinedGroup->RemoveMember(bot->GetGUID());
            session->SetPlayer(nullptr);
            delete bot;
            return nullptr;
        }
        bot->SetMap(destinationMap);
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
        bot->RemoveAllAuras();
        if (prejoinedGroup && bot->GetGroup() == prejoinedGroup)
            prejoinedGroup->RemoveMember(bot->GetGUID());
        session->SetPlayer(nullptr);
        delete bot;
        return nullptr;
    }
    TC_LOG_INFO("server", "PlayerBot add_to_map complete character=%s map=%u", guid.ToString().c_str(), bot->GetMapId());

    bool const serverProvisioning =
        provisionedDungeonDifficulty != NoProvisionedDungeonDifficulty
        || provisionedRaidDifficulty != NoProvisionedRaidDifficulty;
    if (serverProvisioning)
    {
        // A new run owns exactly one pre-activation baseline transition. This
        // capability is private to server admission and is never exposed to a
        // bot session or the decision scheduler. Death or resource loss after
        // activation must be reconciled through ordinary player mechanics.
        bot->CombatStopWithPets(true);
        bot->CastStop();
        if (!bot->IsAlive())
        {
            bot->ResurrectPlayer(1.0f, false);
            bot->SpawnCorpseBones();
        }
        bot->ResetAllPowers();
        bot->GetSpellHistory()->ResetAllCooldowns();
    }

    ObjectAccessor::AddObject(bot);
    TC_LOG_INFO("server", "PlayerBot object_accessor_add complete character=%s", guid.ToString().c_str());

    bot->LoadPetsFromDB(holder->GetPreparedResult(PLAYER_LOGIN_QUERY_LOAD_ALL_PETS));
    if (bot->getClass() == CLASS_HUNTER)
    {
        auto isLoadableHunterPet = [bot](PlayerPetData const* petData)
        {
            if (!petData || petData->Type != HUNTER_PET || !petData->PetId || !petData->CreatureId)
                return false;

            CreatureTemplate const* creatureInfo = sObjectMgr->GetCreatureTemplate(petData->CreatureId);
            return creatureInfo && creatureInfo->IsTameable(bot->CanTameExoticPets());
        };

        PlayerPetData const* currentPet = bot->GetPlayerPetDataCurrent();
        if (!isLoadableHunterPet(currentPet))
            TC_LOG_ERROR("server",
                "PlayerBot hunter active pet unavailable character=%s; provisioning must assign a valid active pet",
                guid.ToString().c_str());
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
    bot->GetGameClient()->SetMovedUnit(bot, true);
    SetBotCharacterOnline(guid, true);
    _botSessions[guid] = std::move(session);
    return bot;
}
