#ifndef TRINITY_BOT_TYPES_H
#define TRINITY_BOT_TYPES_H

#include "Define.h"
#include "ObjectGuid.h"
#include <map>
#include <string>
#include <vector>

class Unit;

enum class BotCombatArchetype : uint8
{
    MeleeDps,
    RangedCaster,
    RangedPhysical,
    PetClass,
    TankLikeMelee,
    HealerSolo
};

enum class BotCombatIntent : uint8
{
    PullTarget,
    MaintainRotation,
    UseBuilder,
    UseSpender,
    UseDot,
    UseProc,
    Interrupt,
    Stun,
    UseDefensive,
    HealSelf,
    MoveToRange,
    Kite,
    Wait,
    Loot,
    Recover
};

enum class BotRole : uint8
{
    HolyPaladinHealer,
    Warrior,
    Hunter,
    Rogue,
    Priest,
    DeathKnight,
    Shaman,
    Mage,
    Warlock,
    Druid,
    Generic
};

enum class BotRoleCategory : uint8
{
    Tank,
    Healer,
    Damage
};

enum class BotMovementMode : uint8
{
    Follow,
    Stay,
    Stop,
    MoveTo,
    ReturnToGroup,
    MoveSafe,
    Unstuck
};

struct BotMovementTarget
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    bool Active = false;
};

struct BotMovementFrame
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    float Orientation = 0.0f;
    bool Moving = false;
    bool Mounted = false;
    bool InCombat = false;
    float HpPct = 1.0f;
    float DistanceToLeader = 0.0f;
    float DistanceToGroupCenter = 0.0f;
    bool LineOfSightToLeader = false;
    bool OnTransport = false;
    bool Indoors = false;
    float CurrentPathLength = 0.0f;
    bool PathAvailable = false;
    float StuckScore = 0.0f;
    uint32 LastProgressTimeMs = 0;
    bool NearbyHazard = false;
    bool SafePositionAvailable = false;
};

struct BotCombatState
{
    ObjectGuid TargetGuid;
    uint32 TargetEntry = 0;
    float SelfHpPct = 1.0f;
    float SelfPowerPct = 1.0f;
    uint8 ClassId = 0;
    uint32 SpecId = 0;
    bool Moving = false;
    bool Casting = false;
    bool GcdReady = true;
    uint32 ActiveAuraCount = 0;
    float TargetHpPct = 0.0f;
    float TargetDistance = 0.0f;
    uint32 TargetCastingSpellId = 0;
    float TargetCastRemaining = 0.0f;
    bool TargetInterruptible = false;
    uint32 NearbyHostileCount = 0;
    bool EliteNearby = false;
    float ExtraPullRisk = 0.0f;
    bool SafePositionAvailable = false;
    bool TargetDead = false;
    bool TargetLootable = false;
    bool InCombat = false;
};

struct BotInventoryMaterial
{
    uint32 ItemId = 0;
    uint32 Count = 0;
};

struct BotProfessionState
{
    std::string ProfessionId = "cooking";
    uint32 SkillId = 0;
    uint16 SkillCurrent = 0;
    uint16 SkillTarget = 0;
    std::vector<uint32> KnownRecipes;
    std::vector<uint32> TrainableRecipes;
    uint32 BagFreeSlots = 0;
};

struct BotInventoryState
{
    std::vector<BotInventoryMaterial> Materials;
    uint64 Gold = 0;
};

struct BotProfessionFrame
{
    ObjectGuid OwnerGuid;
    ObjectGuid BotGuid;
    uint8 ClassId = 0;
    uint32 SpecId = 0;
    BotProfessionState Profession;
    BotInventoryState Inventory;
};

struct BotRecipeScore
{
    uint32 RecipeSpellId = 0;
    float ExpectedSkillupValue = 0.0f;
    float MaterialCost = 0.0f;
    float TravelCost = 0.0f;
    float RecipeAcquisitionCost = 0.0f;
    float Score = 0.0f;
    bool Known = false;
    bool MaterialsAvailable = false;
};

struct BotGearEvaluation
{
    uint32 ItemId = 0;
    uint8 Bag = 0;
    uint8 Slot = 0;
    uint8 Quality = 0;
    uint8 InventoryType = 0;
    float Score = 0.0f;
    float EquippedScore = 0.0f;
    std::string Decision = "keep";
};

struct BotGatheringNodeFrame
{
    uint32 NodeEntry = 0;
    std::string NodeType;
    uint32 ZoneId = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    float Distance = 0.0f;
    bool LineOfSight = false;
    bool PathAvailable = false;
    bool BagSpaceAvailable = false;
    bool Mounted = false;
    bool InCombat = false;
    bool EliteNearby = false;
};

struct BotCombatDecision
{
    std::string Mode = "single_target";
    BotCombatIntent Intent = BotCombatIntent::Wait;
    ObjectGuid TargetGuid;
};

struct ResolvedCombatAction
{
    std::string Type = "wait";
    uint32 SpellId = 0;
    ObjectGuid TargetGuid;
    bool Valid = false;
    std::string DebugName;
    std::string MovementDirective;
    std::string AutoAttackMode;
    float MinRange = 0.0f;
    float MaxRange = 0.0f;
};

enum class HealerMode : uint8
{
    Conserve,
    PrepareTankBurst,
    PrepareGroupAoe,
    HoldUntilDamage,
    Precast,
    RecoverAfterDamage,
    Emergency
};

enum class HealerIntent : uint8
{
    Wait,
    EfficientSingleHeal,
    FastSingleHeal,
    BigSingleHeal,
    InstantSingleHeal,
    AoeHeal,
    Dispel,
    ThroughputCooldown,
    ExternalDefensive,
    MoveSafe
};

struct HealerUnitFrame
{
    ObjectGuid Guid;
    std::string Name;
    uint8 Role = 0;
    uint8 Subgroup = 0;
    uint8 HealthPct = 100;
    float Distance = 0.0f;
    bool Alive = false;
    bool Friendly = false;
    bool LineOfSight = false;
    bool IsOwner = false;
    uint32 CastSpellId = 0;
    uint32 ChannelSpellId = 0;
    uint32 AuraCount = 0;
    uint32 DebuffCount = 0;
    uint32 RecentDamageTaken = 0;
    uint32 RecentHealingReceived = 0;
};

struct BotRecentEvents
{
    uint32 DamageTaken = 0;
    uint32 HealingDone = 0;
    uint32 HealingReceived = 0;
    std::map<ObjectGuid, uint32> PartyDamageTaken;
    std::map<ObjectGuid, uint32> PartyHealingReceived;
};

struct HealerFrame
{
    ObjectGuid OwnerGuid;
    ObjectGuid BotGuid;
    uint32 MapId = 0;
    uint32 BotHealthPct = 100;
    uint32 BotManaPct = 100;
    bool BotAlive = false;
    bool BotCasting = false;
    uint32 BotCastSpellId = 0;
    uint32 BotChannelSpellId = 0;
    uint32 BotAuraCount = 0;
    uint32 BotDebuffCount = 0;
    bool GcdReady = true;
    bool InCombat = false;
    uint32 RecentDamageTaken = 0;
    uint32 RecentHealingDone = 0;
    uint32 RecentHealingReceived = 0;
    BotMovementMode MovementMode = BotMovementMode::Follow;
    std::vector<HealerUnitFrame> Party;
};

struct HealerDecision
{
    HealerMode Mode = HealerMode::Conserve;
    HealerIntent Intent = HealerIntent::Wait;
    ObjectGuid TargetGuid;
    float Confidence = 1.0f;
    std::vector<HealerIntent> Fallbacks;
};

struct ResolvedBotAction
{
    HealerIntent Intent = HealerIntent::Wait;
    ObjectGuid TargetGuid;
    uint32 SpellId = 0;
    std::string DebugName;
};

enum class BotActionResult : uint8
{
    Ok,
    Disabled,
    NoOwner,
    NoBot,
    InvalidTarget,
    NotFriendly,
    DeadTarget,
    OutOfRange,
    NoLineOfSight,
    Casting,
    GlobalCooldown,
    Cooldown,
    NoMana,
    BadSpell,
    CastFailed,
    Throttled,
    NoAction
};

struct BotEconomyActionResult
{
    BotActionResult Result = BotActionResult::NoAction;
    uint32 ItemCount = 0;
    uint64 Money = 0;
};

char const* ToString(BotMovementMode mode);
char const* ToString(BotCombatArchetype archetype);
char const* ToString(BotCombatIntent intent);
char const* ToString(BotRole role);
char const* ToString(HealerMode mode);
char const* ToString(HealerIntent intent);
char const* ToString(BotActionResult result);
std::string NormalizeBotRole(std::string const& role);
BotRole ParseBotRole(std::string const& role);
BotRoleCategory GetBotRoleCategory(BotRole role);
bool IsKnownBotRole(std::string const& role);
bool IsMixedBotRoleSelector(std::string const& role);
bool IsHealerBotRole(BotRole role);
BotCombatArchetype GetSoloCombatArchetype(BotRole role);

#endif
