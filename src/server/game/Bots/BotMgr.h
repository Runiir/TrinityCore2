#ifndef TRINITY_BOT_MGR_H
#define TRINITY_BOT_MGR_H

#include "Bots/BotActionExecutor.h"
#include "Bots/BotController.h"
#include "ObjectGuid.h"
#include <map>
#include <memory>
#include <set>
#include <vector>
#include <string>

class Group;
class Player;
class Unit;
class WorldSession;

class BotMgr
{
public:
    static BotMgr* instance();

    void Update(uint32 diff);
    Player* Spawn(Player* owner, std::string const& role, std::string const& selector);
    Player* SpawnWorldBot(std::string const& role, std::string const& selector, uint32 mapId, float x, float y, float z, float o);
    Player* SpawnWorldBotInGroup(Player* groupAnchor, std::string const& role, std::string const& selector, uint32 mapId, float x, float y, float z, float o);
    Player* SpawnWorldBotAtSavedPosition(std::string const& role, std::string const& selector);
    Player* SpawnHolyPaladin(Player* owner, std::string const& selector);
    Player* GetOrLoadHeadlessOwner(std::string const& selector);
    void ReleaseHeadlessOwnerIfIdle(Player* owner);
    BotActionResult AddExistingHolyPaladin(Player* owner, Player* bot);
    std::vector<Player*> PartyFill(Player* owner, std::string const& partyType, std::string const& role);
    uint32 Remove(Player* owner, std::string const& selector = "all");
    bool Remove(Player* owner, ObjectGuid botGuid);
    bool RemoveWorldBot(ObjectGuid botGuid);
    uint32 SetMovement(Player* owner, BotMovementMode mode, std::string const& selector = "all");
    uint32 SetMoveTarget(Player* owner, float x, float y, float z, std::string const& selector = "all");
    uint32 SetCombatTarget(Player* owner, std::string const& targetSelector, std::string const& botSelector = "all");
    uint32 ClearCombatTarget(Player* owner, std::string const& selector = "all");
    std::vector<BotRecipeScore> ScoreCookingRecipes(Player* owner, std::string const& selector = "all") const;
    std::map<ObjectGuid, BotActionResult> CraftCookingRecipe(Player* owner, uint32 recipeSpellId, uint32 count, std::string const& selector = "all");
    std::map<ObjectGuid, BotEconomyActionResult> VendorTrash(Player* owner, std::string const& selector = "all");
    std::map<ObjectGuid, BotEconomyActionResult> Repair(Player* owner, std::string const& selector = "all");
    std::map<ObjectGuid, std::vector<BotGearEvaluation>> EvaluateGear(Player* owner, std::string const& selector = "all") const;
    bool SetRecording(Player* owner, bool enabled);
    std::string GetStatus(Player* owner) const;
    char const* GetBotRoleName(ObjectGuid botGuid) const;
    Player* GetLoadedPlayer(ObjectGuid guid) const;
    BotRecentEvents ConsumeRecentEvents(ObjectGuid botGuid);
    void OnOwnerLogout(Player* owner);
    void OnGroupRemoveMember(Group* group, ObjectGuid guid);
    void OnGroupDisband(Group* group);
    void ResetPoolUseState();
    void RemoveAll();
    void OnDamage(Unit* attacker, Unit* victim, uint32 damage);
    void OnHeal(Unit* healer, Unit* receiver, uint32 gain);

private:
    BotController* GetController(ObjectGuid botGuid);
    BotController const* GetController(ObjectGuid botGuid) const;
    Player* FindLoadedPlayer(ObjectGuid guid) const;
    std::vector<ObjectGuid> GetOwnedBots(ObjectGuid ownerGuid) const;
    std::vector<ObjectGuid> ResolveTargets(Player* owner, std::string const& selector) const;
    Unit* ResolveHostileTarget(Player* owner, std::string const& targetSelector) const;
    bool IsOwnedBot(ObjectGuid botGuid) const;
    ObjectGuid GetOwnerGuid(ObjectGuid botGuid) const;
    bool IsTrackedPartyMember(ObjectGuid botGuid, ObjectGuid unitGuid) const;
    struct BotSpawnPlacement
    {
        uint32 MapId;
        float X;
        float Y;
        float Z;
        float O;
    };

    Player* LoadBotFromPool(Player* owner, std::string const& role, std::string const& selector, BotSpawnPlacement const* placement = nullptr, Player* groupAnchor = nullptr);
    Player* LoadCharacterAsBotSession(ObjectGuid guid, uint32 accountId, Player* nearPlayer, BotSpawnPlacement const* placement = nullptr, Player* groupAnchor = nullptr);
    bool AddToOwnerGroup(Player* owner, Player* bot, std::string const& runtimeRole, BotRole role);
    void CleanupBot(ObjectGuid botGuid, bool logoutPlayer);
    void SetBotCharacterOnline(ObjectGuid botGuid, bool online);
    void ReleasePoolCharacter(ObjectGuid botGuid);
    void Register(Player* owner, Player* bot, BotRole role, std::string const& runtimeRole, std::string const& classSpec, std::unique_ptr<WorldSession> session);

    std::map<ObjectGuid, std::unique_ptr<BotController>> _controllersByBot;
    std::map<ObjectGuid, ObjectGuid> _ownerByBot;
    std::multimap<ObjectGuid, ObjectGuid> _botsByOwner;
    std::map<ObjectGuid, std::unique_ptr<WorldSession>> _botSessions;
    std::map<ObjectGuid, std::unique_ptr<WorldSession>> _headlessOwnerSessions;
    std::map<ObjectGuid, BotRecentEvents> _recentEventsByBot;
    std::set<ObjectGuid> _removingBots;
    std::set<ObjectGuid> _worldBots;
    BotActionExecutor _executor;
};

#define sBotMgr BotMgr::instance()

#endif
