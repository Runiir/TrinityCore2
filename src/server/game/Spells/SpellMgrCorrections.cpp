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

#include "SpellMgr.h"
#include "BattlefieldMgr.h"
#include "BattlegroundMgr.h"
#include "Chat.h"
#include "Containers.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "Log.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "SharedDefines.h"
#include "Spell.h"
#include "SpellAuraDefines.h"
#include "SpellInfo.h"
#include <G3D/g3dmath.h>

#include "SpellMgrCorrectionsInternal.h"

void SpellMgr::LoadSpellInfoCorrections()
{
    uint32 oldMSTime = getMSTime();

    SpellMgrCorrections::ApplyPart01();
    SpellMgrCorrections::ApplyPart02();
    SpellMgrCorrections::ApplyPart03();
    SpellMgrCorrections::ApplyPart04();

    for (uint32 i = 0; i < GetSpellInfoStoreSize(); ++i)
    {
        SpellInfo* spellInfo = mSpellInfoMap[i];
        if (!spellInfo)
            continue;

        // Fix range for trajectory triggered spell
        for (uint8 j = 0; j < MAX_SPELL_EFFECTS; ++j)
        {
            if (spellInfo->Effects[j].IsEffect() && (spellInfo->Effects[j].TargetA.GetTarget() == TARGET_DEST_TRAJ || spellInfo->Effects[j].TargetB.GetTarget() == TARGET_DEST_TRAJ))
            {
                // Get triggered spell if any
                if (SpellInfo* spellInfoTrigger = const_cast<SpellInfo*>(GetSpellInfo(spellInfo->Effects[j].TriggerSpell)))
                {
                    float maxRangeMain = spellInfo->RangeEntry ? spellInfo->RangeEntry->RangeMax[0] : 0.0f;
                    float maxRangeTrigger = spellInfoTrigger->RangeEntry ? spellInfoTrigger->RangeEntry->RangeMax[0] : 0.0f;

                    // check if triggered spell has enough max range to cover trajectory
                    if (maxRangeTrigger < maxRangeMain)
                        spellInfoTrigger->RangeEntry = spellInfo->RangeEntry;
                }
            }
        }

        for (uint8 j = 0; j < MAX_SPELL_EFFECTS; ++j)
        {
            switch (spellInfo->Effects[j].Effect)
            {
                case SPELL_EFFECT_CHARGE:
                case SPELL_EFFECT_CHARGE_DEST:
                case SPELL_EFFECT_JUMP:
                case SPELL_EFFECT_JUMP_DEST:
                case SPELL_EFFECT_LEAP_BACK:
                    if (!spellInfo->Speed && !spellInfo->SpellFamilyName)
                        spellInfo->Speed = SPEED_CHARGE;
                    break;
            }

            // Passive talent auras cannot target pets
            if (spellInfo->IsPassive() && sDBCManager.GetTalentSpellCost(i))
                if (spellInfo->Effects[j].TargetA.GetTarget() == TARGET_UNIT_PET)
                    spellInfo->Effects[j].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_CASTER);
            if (spellInfo->Effects[j].TargetA.GetSelectionCategory() == TARGET_SELECT_CATEGORY_CONE || spellInfo->Effects[j].TargetB.GetSelectionCategory() == TARGET_SELECT_CATEGORY_CONE)
                if (G3D::fuzzyEq(spellInfo->ConeAngle, 0.f))
                    spellInfo->ConeAngle = 90.f;
            // Area auras may not target area (they're self cast)
            if (spellInfo->Effects[j].IsAreaAuraEffect() && spellInfo->Effects[j].IsTargetingArea())
            {
                spellInfo->Effects[j].TargetA = SpellImplicitTargetInfo(TARGET_UNIT_CASTER);
                spellInfo->Effects[j].TargetB = SpellImplicitTargetInfo(0);
            }
       }

        // disable proc for magnet auras, they're handled differently
        if (spellInfo->HasAura(SPELL_AURA_SPELL_MAGNET))
            spellInfo->ProcFlags = PROC_FLAG_NONE;

        // due to the way spell system works, unit would change orientation in Spell::_cast
        if (spellInfo->HasAura(SPELL_AURA_CONTROL_VEHICLE))
            spellInfo->AttributesEx5 |= SPELL_ATTR5_AI_DOESNT_FACE_TARGET;

        if (spellInfo->ActiveIconID == 2158)  // flight
            spellInfo->Attributes |= SPELL_ATTR0_PASSIVE;

        if (spellInfo->IsSingleTarget() && !spellInfo->MaxAffectedTargets)
            spellInfo->MaxAffectedTargets = 1;

        switch (spellInfo->SpellFamilyName)
        {
            case SPELLFAMILY_PALADIN:
                // Seals of the Pure should affect Seal of Righteousness
                if (spellInfo->SpellIconID == 25 && spellInfo->HasAttribute(SPELL_ATTR0_PASSIVE))
                    spellInfo->Effects[EFFECT_0].SpellClassMask[1] |= 0x20000000;
                break;
            case SPELLFAMILY_DEATHKNIGHT:
                // Icy Touch - extend FamilyFlags (unused value) for Sigil of the Frozen Conscience to use
                if (spellInfo->SpellIconID == 2721 && spellInfo->SpellFamilyFlags[0] & 0x2)
                    spellInfo->SpellFamilyFlags[0] |= 0x40;
                break;
            case SPELLFAMILY_SHAMAN:
                // Nature's Blessing should also affect Greater Healing Wave and Riptide
                if (spellInfo->SpellIconID == 2012 && spellInfo->HasAura(SPELL_AURA_DUMMY))
                    spellInfo->Effects[EFFECT_0].SpellClassMask[2] = (0x00000010 | 0x00010000);
                break;
            default:
                break;
        }
    }

    if (SummonPropertiesEntry* properties = const_cast<SummonPropertiesEntry*>(sSummonPropertiesStore.LookupEntry(121)))
        properties->Title = AsUnderlyingType(SummonTitle::Totem);
    if (SummonPropertiesEntry* properties = const_cast<SummonPropertiesEntry*>(sSummonPropertiesStore.LookupEntry(647))) // 52893
        properties->Title = AsUnderlyingType(SummonTitle::Totem);
    if (SummonPropertiesEntry* properties = const_cast<SummonPropertiesEntry*>(sSummonPropertiesStore.LookupEntry(3069))) // Wild Mushroom
        properties->Title = AsUnderlyingType(SummonTitle::Minion);
    if (SummonPropertiesEntry* properties = const_cast<SummonPropertiesEntry*>(sSummonPropertiesStore.LookupEntry(628))) // Hungry Plaguehound
        properties->Control = SUMMON_CATEGORY_PET;

    if (LockEntry* entry = const_cast<LockEntry*>(sLockStore.LookupEntry(36))) // 3366 Opening, allows to open without proper key
        entry->Type[2] = LOCK_KEY_NONE;

    TC_LOG_INFO("server.loading", ">> Loaded SpellInfo corrections in %u ms", GetMSTimeDiffToNow(oldMSTime));
}
