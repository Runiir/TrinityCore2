/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 * Licensed under the GNU General Public License, version 2 or later.
 */

#include "ScriptMgr.h"
#include "Player.h"
#include "Pet.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellScript.h"

// 13481 - Tame Beast (the final periodic trigger of the 1515 channel).
class spell_hun_tame_beast_completion : public SpellScript
{
    bool Validate(SpellInfo const* spellInfo) override
    {
        return spellInfo->Id == 13481 && spellInfo->HasEffect(SPELL_EFFECT_TAMECREATURE)
            && ValidateSpellInfo({1515});
    }

    void BeforeTame()
    {
        _channel = nullptr;
        _targetEntry = 0;
        Player* player = GetCaster()->ToPlayer();
        Creature* target = GetHitCreature();
        if (!player || player->getClass() != CLASS_HUNTER || !target || player->GetPetGUID())
            return;

        Spell* channel = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
        if (!channel || channel->getState() != SPELL_STATE_CHANNELING
            || channel->GetSpellInfo()->Id != 1515
            || !GetSpell()->IsTriggeredByAura(channel->GetSpellInfo())
            || channel->m_targets.GetUnitTargetGUID() != target->GetGUID())
            return;

        _channel = channel;
        _targetEntry = target->GetEntry();
    }

    void AfterTame()
    {
        Player* player = GetCaster()->ToPlayer();
        if (!player || !_channel || player->GetCurrentSpell(CURRENT_CHANNELED_SPELL) != _channel)
            return;

        Pet* pet = player->GetPet();
        if (!pet || !pet->IsInWorld() || pet->getPetType() != HUNTER_PET
            || pet->GetOwnerGUID() != player->GetGUID() || pet->GetEntry() != _targetEntry
            || pet->GetUInt32Value(UNIT_CREATED_BY_SPELL) != 13481
            || _channel->getState() != SPELL_STATE_CHANNELING)
            return;

        // EffectTameCreature finishes the triggered spell, not its parent channel.
        // Once pet creation succeeds, finish that exact parent before its next
        // update can mistake the despawned wild target for an interrupted tame.
        _channel->SendChannelUpdate(0);
        _channel->finish();
    }

    void Register() override
    {
        BeforeHit.Register(&spell_hun_tame_beast_completion::BeforeTame);
        AfterHit.Register(&spell_hun_tame_beast_completion::AfterTame);
    }

    Spell* _channel = nullptr;
    uint32 _targetEntry = 0;
};

void AddSC_hunter_tame_completion_spell_scripts()
{
    RegisterSpellScript(spell_hun_tame_beast_completion);
}
