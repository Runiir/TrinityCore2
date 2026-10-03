#pragma once
#include "protocol.hpp"

namespace bridge
{
Bytes quest_rewards(Reader &r,Value *offered_choices=nullptr);
}
