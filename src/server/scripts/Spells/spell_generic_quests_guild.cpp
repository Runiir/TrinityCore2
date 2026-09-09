/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

/*
 * Scripts for spells with SPELLFAMILY_GENERIC which cannot be included in AI script file
 * of creature using it or can't be bound to any player class.
 * Ordered alphabetically using scriptname.
 * Scriptnames of files in this file should be prefixed with "spell_gen_"
 */

#include "ScriptMgr.h"
#include "Battleground.h"
#include "CellImpl.h"
#include "Containers.h"
#include "DBCStores.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "InstanceScript.h"
#include "Item.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "ReputationMgr.h"
#include "SkillDiscovery.h"
#include "SpellAuraEffects.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "Vehicle.h"
#include "CreatureAIImpl.h"

#include "spell_generic_registration.h"

namespace Spells::Generic
{
enum GilneasPrison
{
    SPELL_SUMMON_RAVENOUS_WORGEN_1 = 66836,
    SPELL_SUMMON_RAVENOUS_WORGEN_2 = 66925,

    NPC_WORGEN_RUNT                = 35456,
};

Position const WorgenRuntHousePos[] =
{
    // House Roof
    { -1729.345f, 1526.495f, 55.47962f, 6.188943f },
    { -1709.63f, 1527.464f, 56.86086f, 3.258752f },
    { -1717.75f, 1513.727f, 55.47941f, 4.704845f },
    { -1724.719f, 1526.731f, 55.66177f, 6.138319f },
    { -1713.974f, 1526.625f, 56.21981f, 3.306195f },
    { -1718.104f, 1524.071f, 55.81641f, 4.709816f },
    { -1718.262f, 1518.557f, 55.55954f, 4.726997f },
    // Cathdral Roof
    { -1618.054f, 1489.644f, 68.45153f, 3.593639f },
    { -1625.62f, 1487.033f, 71.27762f, 3.531424f },
    { -1638.569f, 1489.736f, 68.55273f, 4.548815f },
    { -1630.399f, 1481.66f, 71.41516f, 3.484555f },
    { -1622.424f, 1483.882f, 67.67381f, 3.404875f },
    { -1634.344f, 1491.3f, 70.10101f, 4.6248f },
    { -1631.979f, 1491.585f, 71.11481f, 4.032866f },
    { -1627.273f, 1499.689f, 68.89395f, 4.251452f },
    { -1622.665f, 1489.818f, 71.03797f, 3.776179f },
};

class spell_gen_gilneas_prison_periodic_dummy : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_SUMMON_RAVENOUS_WORGEN_1, // House roof
                SPELL_SUMMON_RAVENOUS_WORGEN_2, // Cathedral roof
            });
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        if (Unit* caster = GetCaster())
        {
            switch (RAND(0, 1))
            {
                case 0:
                    caster->CastSpell(caster, SPELL_SUMMON_RAVENOUS_WORGEN_1, true);
                    for (uint8 i = 0; i < 7; i++)
                        if (Creature* runt = caster->SummonCreature(NPC_WORGEN_RUNT, WorgenRuntHousePos[i]))
                            runt->AI()->DoAction(i);
                    break;
                case 1:
                    caster->CastSpell(caster, SPELL_SUMMON_RAVENOUS_WORGEN_2, true);
                    for (uint8 i = 7; i < 16; i++)
                        if (Creature* runt = caster->SummonCreature(NPC_WORGEN_RUNT, WorgenRuntHousePos[i]))
                            runt->AI()->DoAction(i);
                    if (RAND(0, 1) == 1)
                        for (uint8 i = 0; i < RAND(1, 3); i++)
                            if (Creature* runt = caster->SummonCreature(NPC_WORGEN_RUNT, WorgenRuntHousePos[i]))
                                runt->AI()->DoAction(i);
                    break;
            }
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_gilneas_prison_periodic_dummy::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

enum ThrowTorch
{
    CREDIT_ROUND_UP_WORGEN  = 35582,
    SPELL_THROW_TORCH       = 67063
};

class spell_gen_throw_torch : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo( { SPELL_THROW_TORCH });
    }

    void HandleEffect()
    {
        if (Player* player = GetCaster()->ToPlayer())
            if (GetHitUnit() && !GetHitUnit()->HasAura(SPELL_THROW_TORCH))
                player->KilledMonsterCredit(CREDIT_ROUND_UP_WORGEN);
    }

    void Register() override
    {
        BeforeHit.Register(&spell_gen_throw_torch::HandleEffect);
    }
};

class spell_gen_revserse_cast_mirror_image : public SpellScript
{
    void HandleScript(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            GetHitUnit()->CastSpell(caster, GetSpellInfo()->Effects[effIndex].BasePoints, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_revserse_cast_mirror_image::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_gen_mirror_image_aura : public SpellScript
{
    void HandleScript(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            GetHitUnit()->CastSpell(caster, GetSpellInfo()->Effects[effIndex].BasePoints, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_mirror_image_aura::HandleScript, EFFECT_1, SPELL_EFFECT_SCRIPT_EFFECT);
        OnEffectHitTarget.Register(&spell_gen_mirror_image_aura::HandleScript, EFFECT_2, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};


class spell_gen_reverse_cast_ride_vehicle : public SpellScript
{
    void HandleScript(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            GetHitUnit()->CastSpell(caster, GetSpellInfo()->Effects[effIndex].BasePoints, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_reverse_cast_ride_vehicle::HandleScript, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class GroupMemberCheck
{
public:
    GroupMemberCheck(Player* player) : _player(player) { }

    bool operator()(WorldObject* object)
    {
        if (Player* player = object->ToPlayer())
            return !player->IsInSameGroupWith(_player);

        return false;
    }
private:
    Player* _player;
};

class spell_gen_launch_quest : public SpellScript
{
    bool Load() override
    {
        return GetCaster()->GetTypeId() == TYPEID_UNIT;
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.size() > 1)
            if (Player* player = GetCaster()->ToCreature()->GetLootRecipient())
                targets.remove_if(GroupMemberCheck(player));
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_gen_launch_quest::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENTRY);
    }
};

// Used for some spells cast by vehicles or charmed creatures that do not send a cooldown event on their own
class spell_gen_charmed_unit_spell_cooldown : public SpellScript
{
    void HandleCast()
    {
        Unit* caster = GetCaster();
        if (Player* owner = caster->GetCharmerOrOwnerPlayerOrPlayerItself())
        {
            WorldPacket data;
            caster->GetSpellHistory()->BuildCooldownPacket(data, SPELL_COOLDOWN_FLAG_NONE, GetSpellInfo()->Id, GetSpellInfo()->RecoveryTime);
            owner->SendDirectMessage(&data);
        }
    }

    void Register() override
    {
        OnCast.Register(&spell_gen_charmed_unit_spell_cooldown::HandleCast);
    }
};

class spell_gen_flurry_of_claws : public AuraScript
{
    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        PreventDefaultAction();
        Unit* target = GetTarget();
        if (Unit* victim = target->GetVictim())
            target->CastSpell(victim, GetSpellInfo()->Effects[EFFECT_0].TriggerSpell, true);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_gen_flurry_of_claws::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

enum Sunflower
{
    SPELL_SINGING_SUNFLOWER_DND = 93972
};

// 93971 - Sunflower (DND)
class spell_gen_sunflower_dnd : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_SINGING_SUNFLOWER_DND });
    }

    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        GetTarget()->CastSpell(GetTarget(), SPELL_SINGING_SUNFLOWER_DND);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_gen_sunflower_dnd::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

enum GuildBattleStandard
{
    // Spells
    SPELL_GUILD_BATTLE_STANDARD_ALLIANCE    = 90216,
    SPELL_GUILD_BATTLE_STANDARD_HORDE       = 90708,

    // Creatures
    NPC_GUILD_BATTLE_STANDARD_ALLIANCE_1    = 48115,
    NPC_GUILD_BATTLE_STANDARD_ALLIANCE_2    = 48633,
    NPC_GUILD_BATTLE_STANDARD_ALLIANCE_3    = 48634,
    NPC_GUILD_BATTLE_STANDARD_HORDE_1       = 48636,
    NPC_GUILD_BATTLE_STANDARD_HORDE_2       = 48637,
    NPC_GUILD_BATTLE_STANDARD_HORDE_3       = 48638
};

// 89481 - Guild Battle Standard
class spell_gen_guild_battle_standard : public AuraScript
{
    bool Load() override
    {
        return GetCaster()->IsCreature();
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_GUILD_BATTLE_STANDARD_ALLIANCE,
                SPELL_GUILD_BATTLE_STANDARD_HORDE
            });
    }

    void HandlePeriodic(AuraEffect const* aurEff)
    {
        int32 bp = 0;
        uint32 spellId = 0;

        Unit* target = GetTarget();
        switch (target->GetEntry())
        {
            case NPC_GUILD_BATTLE_STANDARD_ALLIANCE_1:
                bp = 5;
                spellId = SPELL_GUILD_BATTLE_STANDARD_ALLIANCE;
                break;
            case NPC_GUILD_BATTLE_STANDARD_ALLIANCE_2:
                bp = 10;
                spellId = SPELL_GUILD_BATTLE_STANDARD_ALLIANCE;
                break;
            case NPC_GUILD_BATTLE_STANDARD_ALLIANCE_3:
                bp = 15;
                spellId = SPELL_GUILD_BATTLE_STANDARD_ALLIANCE;
                break;
            case NPC_GUILD_BATTLE_STANDARD_HORDE_1:
                bp = 5;
                spellId = SPELL_GUILD_BATTLE_STANDARD_HORDE;
                break;
            case NPC_GUILD_BATTLE_STANDARD_HORDE_2:
                bp = 10;
                spellId = SPELL_GUILD_BATTLE_STANDARD_HORDE;
                break;
            case NPC_GUILD_BATTLE_STANDARD_HORDE_3:
                bp = 15;
                spellId = SPELL_GUILD_BATTLE_STANDARD_HORDE;
                break;
            default:
                break;
        }

        if (spellId)
            target->CastSpell(target, spellId, CastSpellExtraArgs(aurEff).AddSpellBP0(bp).AddSpellMod(SPELLVALUE_BASE_POINT1, bp).AddSpellMod(SPELLVALUE_BASE_POINT2, bp));
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_gen_guild_battle_standard::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

// 90216 - Guild Battle Standard
// 90708 - Guild Battle Standard
class spell_gen_guild_battle_standard_buff : public SpellScript
{
    bool Load() override
    {
        return GetCaster()->IsSummon();
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        ObjectGuid guildGuid = GetCaster()->GetGuidValue(OBJECT_FIELD_DATA);
        targets.remove_if([guildGuid](WorldObject* target)->bool
        {
            return !target->IsPlayer() || target->ToPlayer()->GetGuidValue(OBJECT_FIELD_DATA) != guildGuid;
        });
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_gen_guild_battle_standard_buff::FilterTargets, EFFECT_ALL, TARGET_UNIT_SRC_AREA_ALLY);
    }
};

enum MobileBanking
{
    SPELL_GUILD_CHEST_HORDE     = 88306,
    SPELL_GUILD_CHEST_ALLIANCE  = 88304
};

// 83958 - Mobile Banking
class spell_gen_mobile_banking : public SpellScript
{
    bool Load() override
    {
        return GetCaster()->IsPlayer();
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_GUILD_CHEST_HORDE,
                SPELL_GUILD_CHEST_ALLIANCE
            });
    }

    SpellCastResult CheckRequirement()
    {
        // The player must have a guild reputation rank of friendly or higher to use the mobile banking ability
        if (GetCaster()->ToPlayer()->GetReputationRank(FACTION_GUILD) < REP_FRIENDLY)
            return SPELL_FAILED_REPUTATION;

        return SPELL_CAST_OK;
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        target->CastSpell(target, target->ToPlayer()->GetTeamId() == TEAM_HORDE ? SPELL_GUILD_CHEST_HORDE : SPELL_GUILD_CHEST_ALLIANCE);
    }

    void Register() override
    {
        OnCheckCast.Register(&spell_gen_mobile_banking::CheckRequirement);
        OnEffectHitTarget.Register(&spell_gen_mobile_banking::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

// 92649 - Cauldron of Battle
// 92712 - Big Cauldron of Battle
class spell_gen_cauldron_of_battle : public SpellScript
{
    bool Load() override
    {
        return GetCaster()->IsPlayer();
    }

    void HandleDummyEffect(SpellEffIndex effIndex)
    {
        Player* target = GetHitPlayer();
        if (!target)
            return;

        bool handleEffect = false;

        // EFFECT_0 = Alliance Cauldron, EFFECT_1 = Horde Cauldron
        if ((effIndex == EFFECT_0 && target->GetTeamId() == TEAM_ALLIANCE) ||
            (effIndex == EFFECT_1 && target->GetTeamId() == TEAM_HORDE))
            handleEffect = true;

        if (handleEffect)
        {
            Position dest = target->GetPosition();
            uint32 spellId = GetEffectValue();

            if (SpellInfo const* spell = sSpellMgr->GetSpellInfo(spellId))
            {
                float radius = spell->Effects[EFFECT_0].CalcRadius(target) - target->GetCombatReach();
                target->GetNearPoint(target, dest.m_positionX, dest.m_positionY, dest.m_positionZ, radius, target->GetOrientation());
                target->CastSpell(Position{ dest.GetPositionX(), dest.GetPositionY(), dest.GetPositionZ() }, spellId);
            }
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_cauldron_of_battle::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
        OnEffectHitTarget.Register(&spell_gen_cauldron_of_battle::HandleDummyEffect, EFFECT_1, SPELL_EFFECT_DUMMY);
    }
};

enum FlaskOfBattle
{
    // According to WoWHead comments the Flask of Flowing Waters effect is not being used for healers
    SPELL_FLASK_OF_STEELSKIN        = 79469,
    SPELL_FLASK_OF_TITANIC_STRENGTH = 79472,
    SPELL_FLASK_OF_THE_WINDS        = 79471,
    SPELL_FLASK_OF_DRACONIC_MIND    = 79470,
    SPELL_CHUG_A_LUG_R1             = 83945,
    SPELL_CHUG_A_LUG_R2             = 83961
};

// 92679 - Flask of Battle
class spell_gen_flask_of_battle : public SpellScript
{
    bool Load() override
    {
        return GetCaster()->IsPlayer();
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_FLASK_OF_STEELSKIN,
                SPELL_FLASK_OF_TITANIC_STRENGTH,
                SPELL_FLASK_OF_THE_WINDS,
                SPELL_FLASK_OF_DRACONIC_MIND,
                SPELL_CHUG_A_LUG_R1,
                SPELL_CHUG_A_LUG_R2
            });
    }

    void HandleBuffEffect(SpellEffIndex /*effIndex*/)
    {
        Player* player = GetHitPlayer();
        if (!player)
            return;

        uint32 spellId = 0;

        uint32 primaryTalentTree = player->GetPrimaryTalentTree(player->GetActiveSpec());
        switch (player->getClass())
        {
            case CLASS_WARLOCK:
            case CLASS_MAGE:
            case CLASS_PRIEST:
                spellId = SPELL_FLASK_OF_DRACONIC_MIND;
                break;
            case CLASS_ROGUE:
            case CLASS_HUNTER:
                spellId = SPELL_FLASK_OF_THE_WINDS;
                break;
            case CLASS_DRUID:
                if (primaryTalentTree == TALENT_TREE_DRUID_FERAL_COMBAT)
                {
                    if (player->GetShapeshiftForm() == FORM_BEAR)
                        spellId = SPELL_FLASK_OF_STEELSKIN;
                    else
                        spellId = SPELL_FLASK_OF_THE_WINDS;
                }
                else
                    spellId = SPELL_FLASK_OF_DRACONIC_MIND;
                break;
            case CLASS_SHAMAN:
                spellId = primaryTalentTree == TALENT_TREE_SHAMAN_ENHANCEMENT ? SPELL_FLASK_OF_THE_WINDS : SPELL_FLASK_OF_DRACONIC_MIND;
                break;
            case CLASS_WARRIOR:
                spellId = primaryTalentTree == TALENT_TREE_WARRIOR_PROTECTION ? SPELL_FLASK_OF_STEELSKIN : SPELL_FLASK_OF_TITANIC_STRENGTH;
                break;
            case CLASS_DEATH_KNIGHT:
                spellId = primaryTalentTree == TALENT_TREE_DEATH_KNIGHT_BLOOD ? SPELL_FLASK_OF_STEELSKIN : SPELL_FLASK_OF_TITANIC_STRENGTH;
                break;
            case CLASS_PALADIN:
                if (primaryTalentTree == TALENT_TREE_PALADIN_HOLY)
                    spellId = SPELL_FLASK_OF_DRACONIC_MIND;
                else if (primaryTalentTree == TALENT_TREE_PALADIN_PROTECTION)
                    spellId = SPELL_FLASK_OF_STEELSKIN;
                else
                    spellId = SPELL_FLASK_OF_TITANIC_STRENGTH;
                break;
            default:
                break;
        }

        if (spellId)
        {
            uint32 chugALugSpellId = 0;
            if (player->HasSpell(SPELL_CHUG_A_LUG_R2))
                chugALugSpellId = SPELL_CHUG_A_LUG_R2;
            else if (player->HasSpell(SPELL_CHUG_A_LUG_R1))
                chugALugSpellId = SPELL_CHUG_A_LUG_R1;

            if (chugALugSpellId)
            {
                int32 durationBonus = sSpellMgr->AssertSpellInfo(chugALugSpellId)->Effects[EFFECT_0].CalcValue();
                int32 duration = sSpellMgr->AssertSpellInfo(spellId)->GetMaxDuration();
                AddPct(duration, durationBonus);
                player->CastSpell(player, spellId, { SPELLVALUE_DURATION, duration });
            }
            else
                player->CastSpell(player, spellId);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_flask_of_battle::HandleBuffEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

enum TheQuickAndTheDead
{
    SPELL_THE_QUICK_AND_THE_DEAD_PERK = 83950,
    SPELL_THE_QUICK_AND_THE_DEAD_BUFF = 84559
};

// 8326 - Ghost
class spell_gen_ghost : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_THE_QUICK_AND_THE_DEAD_PERK,
                SPELL_THE_QUICK_AND_THE_DEAD_BUFF
            });
    }

    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        if (target->HasAura(SPELL_THE_QUICK_AND_THE_DEAD_PERK))
            target->CastSpell(target, SPELL_THE_QUICK_AND_THE_DEAD_BUFF);
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        if (target->HasAura(SPELL_THE_QUICK_AND_THE_DEAD_BUFF))
            target->RemoveAurasDueToSpell(SPELL_THE_QUICK_AND_THE_DEAD_BUFF);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_gen_ghost::AfterApply, EFFECT_0, SPELL_AURA_GHOST, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove.Register(&spell_gen_ghost::AfterRemove, EFFECT_0, SPELL_AURA_GHOST, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_gen_zero_energy_zero_regen : public AuraScript
{
    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        GetTarget()->SetPower(POWER_ENERGY, 0);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_gen_zero_energy_zero_regen::AfterApply, EFFECT_0, SPELL_AURA_MOD_POWER_REGEN_PERCENT, AURA_EFFECT_HANDLE_REAL);
    }
};

enum LaunchQuestAura
{
    SPELL_LAUNCH_QUEST_PERSONAL_SUMMONS_HORDE       = 93079,
    SPELL_LAUNCH_QUEST_PERSONAL_SUMMONS_ALLIANCE    = 93217,
};

// 93081 - Launch Quest Aura
// 93216 - Launch Quest Aura
class spell_gen_launch_quest_aura : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_LAUNCH_QUEST_PERSONAL_SUMMONS_HORDE,
                SPELL_LAUNCH_QUEST_PERSONAL_SUMMONS_ALLIANCE
            });
    }

    // According to sniffs the quests are being launched when the aura expires, not when it gets applied.
    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Player* player = GetTarget()->ToPlayer();
        if (!player)
            return;

        uint32 spellId = player->GetTeamId() == TEAM_ALLIANCE ? SPELL_LAUNCH_QUEST_PERSONAL_SUMMONS_ALLIANCE : SPELL_LAUNCH_QUEST_PERSONAL_SUMMONS_HORDE;
        GetTarget()->CastSpell(GetTarget(), spellId);
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_gen_launch_quest_aura::AfterRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

// 46577 - Wounded
class spell_gen_wounded : public SpellScript
{
    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        if (target->GetHealthPct() > 55.f)
            target->SetHealth(CalculatePct(target->GetMaxHealth(), frand(15.f, 55.f)));
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_gen_wounded::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

// 69041 - Rocket Barrage (Racial)
class spell_gen_rocket_barrage : public SpellScript
{
    void CalculateDamage(Unit* /*victim*/, int32& /*damage*/, int32& flatMod, float& /*pctMod*/)
    {
        flatMod += GetCaster()->getLevel() * 2;
    }

    void Register() override
    {
        CalcDamage.Register(&spell_gen_rocket_barrage::CalculateDamage);
    }
};

enum AuraProcRemoveSpells
{
    SPELL_FACE_RAGE = 99947
};

class spell_gen_face_rage : public AuraScript
{
    bool Validate(SpellInfo const* /*spell*/) override
    {
        return ValidateSpellInfo({ SPELL_FACE_RAGE });
    }

    void OnRemove(AuraEffect const* /*effect*/, AuraEffectHandleModes /*mode*/)
    {
        GetTarget()->RemoveAurasDueToSpell(GetSpellInfo()->Effects[EFFECT_2].TriggerSpell);
    }

    void Register() override
    {
        OnEffectRemove.Register(&spell_gen_face_rage::OnRemove, EFFECT_0, SPELL_AURA_MOD_STUN, AURA_EFFECT_HANDLE_REAL);
    }
};

enum Shadowmeld
{
    SPELL_RACIAL_ELUSIVENESS = 21009
};

// 58984 Shadowmeld (Racial)
class spell_gen_shadowmeld : public AuraScript
{
    bool Validate(SpellInfo const* /*spell*/) override
    {
        return ValidateSpellInfo({ SPELL_RACIAL_ELUSIVENESS });
    }

    void HandleStealthLevel(AuraEffect const* /*aurEff*/, int32& amount, bool& /*canBeRecalculated*/)
    {
        if (AuraEffect const* aurEff = GetUnitOwner()->GetAuraEffect(SPELL_RACIAL_ELUSIVENESS, EFFECT_0))
            amount += aurEff->GetAmount();
    }

    void Register() override
    {
        DoEffectCalcAmount.Register(&spell_gen_shadowmeld::HandleStealthLevel, EFFECT_2, SPELL_AURA_MOD_STEALTH);
    }
};

enum SiegeTankControl
{
    SPELL_SIEGE_TANK_CONTROL = 47963
};

class spell_gen_vehicle_control_link : public AuraScript
{
    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        GetTarget()->RemoveAurasDueToSpell(SPELL_SIEGE_TANK_CONTROL); //aurEff->GetAmount()
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_gen_vehicle_control_link::OnRemove, EFFECT_1, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

enum PolymorphCastVisual
{
    // Spells
    SPELL_MAGE_SQUIRREL_FORM    = 32813,
    SPELL_MAGE_GIRAFFE_FORM     = 32816,
    SPELL_MAGE_SERPENT_FORM     = 32817,
    SPELL_MAGE_DRAGONHAWK_FORM  = 32818,
    SPELL_MAGE_WORGEN_FORM      = 32819,
    SPELL_MAGE_SHEEP_FORM       = 32820,

    NPC_AUROSALIA               = 18744

};

/// @todo move out of here and rename - not a mage spell
// 32826 - Polymorph (Visual)
class spell_gen_polymorph_cast_visual : public SpellScript
{
    static const uint32 PolymorhForms[6];

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        // check if spell ids exist in dbc
        return ValidateSpellInfo(PolymorhForms);
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        if (Unit* target = GetCaster()->FindNearestCreature(NPC_AUROSALIA, 30.0f))
            if (target->GetTypeId() == TYPEID_UNIT)
                target->CastSpell(target, PolymorhForms[urand(0, 5)], true);
    }

    void Register() override
    {
        // add dummy effect spell handler to Polymorph visual
        OnEffectHitTarget.Register(&spell_gen_polymorph_cast_visual::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

uint32 const spell_gen_polymorph_cast_visual::PolymorhForms[6] =
{
    SPELL_MAGE_SQUIRREL_FORM,
    SPELL_MAGE_GIRAFFE_FORM,
    SPELL_MAGE_SERPENT_FORM,
    SPELL_MAGE_DRAGONHAWK_FORM,
    SPELL_MAGE_WORGEN_FORM,
    SPELL_MAGE_SHEEP_FORM
};


void RegisterQuestsGuild7()
{
    RegisterSpellScript(spell_gen_flurry_of_claws);
}

void RegisterQuestsGuild9()
{
    RegisterSpellScript(spell_gen_launch_quest_aura);
}

void RegisterQuestsGuild15()
{
    RegisterSpellScript(spell_gen_gilneas_prison_periodic_dummy);
    RegisterSpellScript(spell_gen_throw_torch);
    RegisterSpellScript(spell_gen_revserse_cast_mirror_image);
    RegisterSpellScript(spell_gen_mirror_image_aura);
    RegisterSpellScript(spell_gen_reverse_cast_ride_vehicle);
    RegisterSpellScript(spell_gen_launch_quest);
    RegisterSpellScript(spell_gen_charmed_unit_spell_cooldown);
    RegisterSpellScript(spell_gen_sunflower_dnd);
    RegisterSpellScript(spell_gen_guild_battle_standard);
    RegisterSpellScript(spell_gen_guild_battle_standard_buff);
    RegisterSpellScript(spell_gen_mobile_banking);
    RegisterSpellScript(spell_gen_cauldron_of_battle);
    RegisterSpellScript(spell_gen_flask_of_battle);
    RegisterSpellScript(spell_gen_ghost);
    RegisterSpellScript(spell_gen_zero_energy_zero_regen);
    RegisterSpellScript(spell_gen_wounded);
    RegisterSpellScript(spell_gen_rocket_barrage);
    RegisterSpellScript(spell_gen_face_rage);
    RegisterSpellScript(spell_gen_shadowmeld);
    RegisterSpellScript(spell_gen_vehicle_control_link);
    RegisterSpellScript(spell_gen_polymorph_cast_visual);
}
}
