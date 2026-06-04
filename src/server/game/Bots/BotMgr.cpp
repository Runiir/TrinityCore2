#include "Bots/BotMgr.h"
#include "Chat.h"
#include "Config.h"
#include "DatabaseEnv.h"
#include "Group.h"
#include "GroupMgr.h"
#include "LFG.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "QueryHolder.h"
#include "Unit.h"
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
    if (!AddToOwnerGroup(owner, bot, botRole))
    {
        TC_LOG_ERROR("server", "PlayerBot spawn failed owner=%s bot=%s stage=add_to_group", owner->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str());
        Remove(owner, bot->GetGUID());
        return nullptr;
    }

    TC_LOG_INFO("server", "PlayerBot spawn complete owner=%s bot=%s name=%s", owner->GetGUID().ToString().c_str(), bot->GetGUID().ToString().c_str(), bot->GetName().c_str());
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

    if (!AddToOwnerGroup(owner, bot, BotRole::HolyPaladinHealer))
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
    std::vector<ObjectGuid> botGuids;
    for (auto const& controller : _controllersByBot)
        botGuids.push_back(controller.first);

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

Player* BotMgr::LoadBotFromPool(Player* owner, std::string const& role, std::string const& selector)
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
    std::string query = "SELECT cbp.guid, c.account, cbp.role FROM character_bot_pool cbp INNER JOIN characters c ON c.guid = cbp.guid WHERE cbp.enabled = 1 AND cbp.in_use = 0" + roleClause + selectorClause + " ORDER BY cbp.guid LIMIT 1";
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
    BotRole botRole = ParseBotRole(selectedRole);
    TC_LOG_INFO("server", "PlayerBot load selected bot=%s account=%u role=%s", botGuid.ToString().c_str(), accountId, selectedRole.c_str());

    Player* bot = LoadCharacterAsBotSession(botGuid, accountId, owner);
    if (!bot)
        return nullptr;

    CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 1 WHERE guid = %u", botGuid.GetCounter());
    auto sessionItr = _botSessions.find(botGuid);
    if (sessionItr == _botSessions.end())
        return nullptr;

    std::unique_ptr<WorldSession> session = std::move(sessionItr->second);
    _botSessions.erase(sessionItr);
    Register(owner, bot, botRole, std::move(session));
    return bot;
}

Player* BotMgr::LoadCharacterAsBotSession(ObjectGuid guid, uint32 accountId, Player* nearPlayer)
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

    if (nearPlayer)
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

    bot->GetMotionMaster()->Initialize();
    bot->SetFullHealth();
    bot->SetFullPower(POWER_MANA);
    session->SetPlayer(bot);

    if (!bot->GetMap() || !bot->GetMap()->AddPlayerToMap(bot))
    {
        TC_LOG_ERROR("server", "PlayerBot load failed character=%s stage=add_player_to_map map=%u", guid.ToString().c_str(), bot->GetMapId());
        session->SetPlayer(nullptr);
        delete bot;
        return nullptr;
    }
    TC_LOG_INFO("server", "PlayerBot add_to_map complete character=%s map=%u", guid.ToString().c_str(), bot->GetMapId());

    ObjectAccessor::AddObject(bot);
    TC_LOG_INFO("server", "PlayerBot object_accessor_add complete character=%s", guid.ToString().c_str());
    SetBotCharacterOnline(guid, true);
    _botSessions[guid] = std::move(session);
    return bot;
}

bool BotMgr::AddToOwnerGroup(Player* owner, Player* bot, BotRole role)
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

    switch (GetBotRoleCategory(role))
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
    _recentEventsByBot.erase(botGuid);
    SetBotCharacterOnline(botGuid, false);
    ReleasePoolCharacter(botGuid);
    _removingBots.erase(botGuid);
}

void BotMgr::SetBotCharacterOnline(ObjectGuid botGuid, bool online)
{
    CharacterDatabase.DirectPExecute("UPDATE characters SET online = %u WHERE guid = %u", online ? 1 : 0, botGuid.GetCounter());
}

void BotMgr::ReleasePoolCharacter(ObjectGuid botGuid)
{
    CharacterDatabase.DirectPExecute("UPDATE character_bot_pool SET in_use = 0 WHERE guid = %u", botGuid.GetCounter());
}

void BotMgr::Register(Player* owner, Player* bot, BotRole role, std::unique_ptr<WorldSession> session)
{
    _ownerByBot[bot->GetGUID()] = owner->GetGUID();
    _botsByOwner.emplace(owner->GetGUID(), bot->GetGUID());
    _botSessions[bot->GetGUID()] = std::move(session);
    _controllersByBot[bot->GetGUID()].reset(new BotController(owner->GetGUID(), bot->GetGUID(), role));
}
