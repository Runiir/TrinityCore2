#ifndef TRINITY_BOT_RAID_HEALTH_RECOVERY_GATE_H
#define TRINITY_BOT_RAID_HEALTH_RECOVERY_GATE_H

namespace BotRaidHealthRecoveryGate
{
// A profile row tagged health_recovery trades damage for the caster's own
// health (Demonology Drain Life, bucket 0, max self health 90%). That is the
// solo calibration lane's Hellfire recovery. In a raid with a living healer,
// the healer restores ordinary health, so the channel is an emergency only.
// r02-b1 Atramedes spirit pack: the Demonology warlock channelled Drain Life
// on every decision below 90% health (274 already_casting attempts in the
// trace, 10 of 11 diagnose snapshots chose 689) and ended at 1.6k DPS.
inline constexpr char const* HealthRecoveryTag = "health_recovery";
inline constexpr char const* RejectReason = "raid_healer_owned_health_recovery";
inline constexpr float EmergencySelfHealthPct = 0.35f;

// The healer probe is only called for a tagged row in a raid above the
// emergency floor, so ordinary resolutions never walk the group.
template <typename LivingHealerProbe>
bool Holds(bool raidInstance, bool healthRecoveryAction, float selfHealthPct,
    LivingHealerProbe&& livingHealerInGroup)
{
    return raidInstance && healthRecoveryAction
        && selfHealthPct > EmergencySelfHealthPct
        && livingHealerInGroup();
}
}

#endif
