#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_HELPERS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_HELPERS_H

#include "Define.h"

#include <string>

class Player;
class SpellInfo;
class Unit;
class WorldObject;
struct BotActionProfileSpell;

namespace BotWorldPopulationMgrNativeHelpers
{
bool IsNativeCombatResSpell(SpellInfo const* spellInfo);
bool IsNativeCombatObserved(Player const* bot, Unit const* target);
bool SubmitNativeQuestAccept(Player* bot, WorldObject* giver, uint32 questId);
bool SubmitNativeQuestReward(Player* bot, WorldObject* giver, uint32 questId, uint32 rewardChoice);
uint64 ReadLastInsertId();
float Distance2d(float ax, float ay, float bx, float by);
bool UsesRangedAoeCalibrationLane(std::string const& spec);
float UnitHealthPct(Unit const* unit);
bool HasPowerForSpell(Player const* bot, SpellInfo const* spellInfo);
uint32 ControlledDispelAuraForHealer(Player const* healer);
Player* CombatOwnerPlayer(Unit* unit);
bool CancelRemovableShapeshifts(Player* bot);
bool MaintainedProfileAuraBlocksRefresh(Unit const* target, BotActionProfileSpell const& spell);
}

#endif
