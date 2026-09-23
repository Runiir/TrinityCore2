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
 * Death Knight glyph handlers kept out of spell_dk.cpp (size budget).
 * Scriptnames are bound in spell_script_names.
 */

#include "ScriptMgr.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellScript.h"
#include "Unit.h"
#include <algorithm>

namespace
{
enum DeathKnightGlyphSpells : uint32
{
    // Glyph of Death Strike: two SPELL_AURA_DUMMY effects, EFFECT_0 = 2 (% per
    // step) and EFFECT_1 = 40 (% cap). Tooltip: "Increases your Death Strike's
    // damage by $59336s1% for every 5 Runic Power you currently have (up to a
    // maximum of $59336s2%). The Runic Power is not consumed by this effect."
    SPELL_DK_GLYPH_OF_DEATH_STRIKE = 59336
};

// Runic power is stored in tenths: the 100 displayed points are 1000 internally.
constexpr int32 RUNIC_POWER_PER_DISPLAYED_POINT = 10;
// "for every 5 Runic Power": whole 5-point steps of displayed runic power.
constexpr int32 GLYPH_OF_DEATH_STRIKE_RUNIC_POWER_STEP = 5;

int32 GlyphOfDeathStrikeBonusPct(int32 runicPower, int32 pctPerStep, int32 maxPct)
{
    if (runicPower <= 0 || pctPerStep <= 0 || maxPct <= 0)
        return 0;

    int32 const steps = runicPower / RUNIC_POWER_PER_DISPLAYED_POINT / GLYPH_OF_DEATH_STRIKE_RUNIC_POWER_STEP;
    return std::min(steps * pctPerStep, maxPct);
}
}

// 49998 - Death Strike (Glyph of Death Strike)
// Damage only: healing stays in spell_dk_death_strike. A Dancing Rune Weapon
// copy resolves the glyph and runic power through its spell-mod owner, as its
// copy takes the owner's Death Strike multipliers (WoWSims Cata 70d87383
// dancing_rune_weapon.go CopySpellMultipliers).
class spell_dk_glyph_of_death_strike : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_DK_GLYPH_OF_DEATH_STRIKE });
    }

    void CalculateDamage(Unit* /*victim*/, int32& /*damage*/, int32& /*flatMod*/, float& pctMod)
    {
        Unit* caster = GetCaster();
        Player* owner = caster ? caster->GetSpellModOwner() : nullptr;
        if (!owner)
            return;

        AuraEffect const* perStep = owner->GetAuraEffect(SPELL_DK_GLYPH_OF_DEATH_STRIKE, EFFECT_0);
        AuraEffect const* cap = owner->GetAuraEffect(SPELL_DK_GLYPH_OF_DEATH_STRIKE, EFFECT_1);
        if (!perStep || !cap)
            return;

        // Reads, never spends, the current runic power.
        if (int32 bonus = GlyphOfDeathStrikeBonusPct(owner->GetPower(POWER_RUNIC_POWER), perStep->GetAmount(), cap->GetAmount()))
            AddPct(pctMod, bonus);
    }

    void Register() override
    {
        CalcDamage.Register(&spell_dk_glyph_of_death_strike::CalculateDamage);
    }
};

void AddSC_deathknight_glyph_spell_scripts()
{
    RegisterSpellScript(spell_dk_glyph_of_death_strike);
}
