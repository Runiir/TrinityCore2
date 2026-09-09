#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "Unit.h"

namespace
{
constexpr uint32 HeroicVialAura = 109725;
constexpr uint32 HeroicLightningStrike = 109724;

int32 LightningStrikeBasePoints(Unit* caster, Unit* target,
    WeaponAttackType triggeringAttack, int32 dbcBasePoints)
{
    WeaponAttackType const attack = triggeringAttack == RANGED_ATTACK ? RANGED_ATTACK : BASE_ATTACK;
    float const attackPower = caster->GetTotalAttackPowerValue(attack)
        + target->GetTotalAuraModifier(attack == RANGED_ATTACK
            ? SPELL_AURA_RANGED_ATTACK_POWER_ATTACKER_BONUS
            : SPELL_AURA_MELEE_ATTACK_POWER_ATTACKER_BONUS);
    // Pinned WoWSims 70d87383 heroic Vial contract (PTR-derived coefficient).
    // Keep the DBC die roll: this overrides base points, not final damage.
    return dbcBasePoints + int32(0.339f * attackPower);
}
}

class spell_item_vial_of_shadows : public SpellScriptLoader
{
public:
    spell_item_vial_of_shadows() : SpellScriptLoader("spell_item_vial_of_shadows") { }

    class vial_AuraScript : public AuraScript
    {
        bool Validate(SpellInfo const* spellInfo) override
        {
            return spellInfo->Id == HeroicVialAura
                && spellInfo->Effects[EFFECT_0].TriggerSpell == HeroicLightningStrike
                && ValidateSpellInfo({ HeroicLightningStrike });
        }

        void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
        {
            DamageInfo* damage = eventInfo.GetDamageInfo();
            Unit* caster = GetTarget();
            Unit* target = eventInfo.GetProcTarget();
            SpellInfo const* child = sSpellMgr->GetSpellInfo(HeroicLightningStrike);
            if (!damage || !caster || !target || !child)
                return; // Preserve the default native proc when provenance is absent.

            int32 const basePoints = LightningStrikeBasePoints(caster, target,
                damage->GetAttackType(), child->Effects[EFFECT_0].BasePoints);
            PreventDefaultAction();
            caster->CastSpell(target, HeroicLightningStrike, CastSpellExtraArgs(aurEff)
                .SetTriggeringSpell(eventInfo.GetProcSpell())
                .SetTriggerFlags(TRIGGERED_FULL_MASK & ~(TRIGGERED_IGNORE_POWER_COST | TRIGGERED_IGNORE_REAGENT_COST))
                .AddSpellBP0(basePoints));
        }

        void Register() override
        {
            OnEffectProc.Register(&vial_AuraScript::HandleProc, EFFECT_0, SPELL_AURA_PROC_TRIGGER_SPELL);
        }
    };

    AuraScript* GetAuraScript() const override { return new vial_AuraScript(); }
};

void AddSC_item_vial_of_shadows()
{
    new spell_item_vial_of_shadows();
}
