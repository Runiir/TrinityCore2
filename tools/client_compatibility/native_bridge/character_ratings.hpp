#pragma once
#include "character_combat.hpp"

namespace bridge
{
void rating_creation(Protocol const &p, Value const &snapshot, Object &unit, Object &active);
void rating_changes(Protocol const &p, Value const &snapshot, Value const &changed, CombatChanges &result);
}
