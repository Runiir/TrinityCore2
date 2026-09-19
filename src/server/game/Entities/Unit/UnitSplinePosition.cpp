/*
 * This file is part of the TrinityCore Project. See AUTHORS file for more information
 * This file may be redistributed under the terms of the GNU General Public
 * License, version 2 or later.
 */

#include "Unit.h"

#include "ObjectAccessor.h"
#include "MoveSpline.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "Transport.h"
#include "WorldSession.h"

#include <cmath>

namespace
{
bool TryGetBotCastFacing(Unit const& caster, Movement::Location const& loc,
    float& orientation)
{
    Player const* player = caster.ToPlayer();
    if (!player || !caster.IsAlive() || !caster.IsInWorld()
        || !player->GetSession() || !player->GetSession()->IsBotSession()
        || caster.GetTransport() || caster.GetVehicle()
        || caster.HasUnitState(UNIT_STATE_CANNOT_TURN)
        || caster.HasFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_CANNOT_TURN))
        return false;

    Spell* spell = caster.GetCurrentSpell(CURRENT_GENERIC_SPELL);
    SpellInfo const* spellInfo = spell ? spell->GetSpellInfo() : nullptr;
    if (!spell || spell->GetCaster() != &caster
        || spell->getState() != SPELL_STATE_PREPARING
        || spell->GetCastTime() <= 0 || spell->IsTriggered()
        || !spellInfo
        || !spellInfo->FacingCasterFlags.HasFlag(SpellFacingCasterFlags::Infront)
        || spell->CheckMovement() != SPELL_CAST_OK)
        return false;

    ObjectGuid targetGuid = spell->m_targets.GetUnitTargetGUID();
    if (!targetGuid || targetGuid == caster.GetGUID())
        return false;

    Unit* target = ObjectAccessor::GetUnit(caster, targetGuid);
    if (!target || target == &caster || !target->IsInWorld()
        || !target->IsAlive() || target->GetMap() != caster.GetMap()
        || !caster.IsValidAttackTarget(target, spellInfo))
        return false;

    orientation = Position::NormalizeOrientation(std::atan2(
        target->GetPositionY() - loc.y, target->GetPositionX() - loc.x));
    return true;
}
}

void Unit::UpdateSplinePosition()
{
    Movement::Location loc = movespline->ComputePosition();

    if (movespline->onTransport)
    {
        Position& pos = m_movementInfo.transport.pos;
        pos.m_positionX = loc.x;
        pos.m_positionY = loc.y;
        pos.m_positionZ = loc.z;
        pos.SetOrientation(loc.orientation);

        if (TransportBase* transport = GetDirectTransport())
            transport->CalculatePassengerPosition(loc.x, loc.y, loc.z, &loc.orientation);
        else
            return;
    }

    if (HasUnitState(UNIT_STATE_CANNOT_TURN))
        loc.orientation = GetOrientation();
    else
    {
        float castFacing = loc.orientation;
        if (TryGetBotCastFacing(*this, loc, castFacing))
            loc.orientation = castFacing;
    }

    UpdatePosition(loc.x, loc.y, loc.z, loc.orientation);
}
