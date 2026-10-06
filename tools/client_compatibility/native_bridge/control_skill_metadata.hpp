#pragma once
#include "buffer.hpp"

namespace bridge
{
// Public class-skill metadata only; never changes native learned spell state.
Array control_skill_hotfixes(View native, Value const &config);
}
