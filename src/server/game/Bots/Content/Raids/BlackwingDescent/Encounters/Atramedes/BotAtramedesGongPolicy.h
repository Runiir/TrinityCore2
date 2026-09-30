#ifndef TRINITY_BOT_ATRAMEDES_GONG_POLICY_H
#define TRINITY_BOT_ATRAMEDES_GONG_POLICY_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesGeometry.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesSoundBound.h"
#include <optional>
#include <string_view>

// When to strike an Ancient Dwarven Shield on the ground, and the shield
// budget shared with the air rules (BotAtramedesAirGong.h). The strike itself
// is the native spellclick (npc_spellclick_spells 77709 plus
// npc_atramedes_ancient_dwarven_shield::OnSpellClick); nothing here changes
// Sound, Vertigo or the breath target.
//
// Budget (ShieldBudget): the ten shields are finite. The rest of the fight
// needs one Searing Flame interrupt per ground phase still to come: this
// ground phase's while it is pending, and the next one's while the boss
// lives to reach it (ShieldReserve). Every other shield is for the air
// strikes (rescues, the kiter Sound bound's resets, the pre-liftoff reset),
// first come first served. Searing Flame may spend any shield; a 90-Sound
// emergency may spend down to this phase's pending Searing Flame; an
// elective (80 Sound) gong keeps one more spare, but when the pre-liftoff
// reset is due the stricter elective budget never suppresses it (it is an
// air strike). A strike the budget forbids is withheld with a `*_at_reserve`
// reason.
namespace BotEncounter::Atramedes
{
// 100 Sound is Devastation (78868). Ninety leaves one Sonic Breath tick (+20).
inline constexpr uint32 SoundEmergency = 90;
// Above this, spend a shield unless Searing Flame (which is gonged anyway
// and resets every bar) is due within SearingSoonMs.
inline constexpr uint32 SoundHigh = 80;
inline constexpr uint32 SearingSoonMs = 15000;
// Duty shields stand this far inside the shield.
inline constexpr float ShieldStandInset = 4.0f;

// Next-ground-phase Searing Flame reserve. The next ground phase's Searing
// Flame comes at least 51 s after landing (native schedule), and the air
// phase lasts at least 31 s, so it is >= 82 s away on the ground and >= 51 s
// away in the air. Below the health that a raid-DPS floor removes in that
// time the boss dies first and the reserve is released.
//
// The floor is the slowest matched tier-11 reference (round 3, 2026-09-30:
// the roster wears phase gear, ~359): the lowest whole-fight raid DPS of the
// seven 10N kills at raid item level 354-360 in
// atramedes_wcl_dps_reference_v1.json is 131,217 (hxz7MH8gW9BYGNdr fight 41);
// the median is 145,174. Whole-fight raid DPS already prices in the air
// phase the melee cannot hit. The old 150k floor was taken from ~409-gear
// Magmaw runs (274-279k) and overstated a T11 raid: a raid slower than its
// floor reaches the next Searing Flame with its shield spent. A lower floor
// only keeps the reserve longer. tests/test_atramedes_raid_sound.py checks
// that the floor stays at or below every matched reference.
inline constexpr float ReserveRaidDpsFloor = 130000.0f;
inline constexpr float NativeHealth10N = 26111168.0f;
inline constexpr float NextSearingSecondsFromGround = 82.0f;
inline constexpr float NextSearingSecondsFromAir = 51.0f;
// 40.8% and 25.4%.
inline constexpr float NextSearingHealthPctFromGround =
    100.0f * ReserveRaidDpsFloor * NextSearingSecondsFromGround / NativeHealth10N;
inline constexpr float NextSearingHealthPctFromAir =
    100.0f * ReserveRaidDpsFloor * NextSearingSecondsFromAir / NativeHealth10N;

struct GongDecision
{
    bool Required = false;
    bool Urgent = false;
    std::string_view Reason;
    // Set when a gong would be wanted but the budget holds it back.
    std::string_view Withheld;
    ObjectGuid Clicker;
    std::optional<ShieldFact> Shield;
};

struct ShieldReserve
{
    // This ground phase's Searing Flame (from the published timer; unknown
    // counts as pending). Never spent by anything but Searing Flame.
    uint32 CurrentPhase = 0;
    // The next ground phase's, while the boss has enough health to reach it.
    // Kept against air rescues and elective gongs, not against emergencies.
    uint32 NextPhase = 0;

    uint32 Total() const { return CurrentPhase + NextPhase; }
};

inline ActorSnapshot const* FindLivingPlayer(Blackboard const& board,
    ObjectGuid guid)
{
    if (guid.IsEmpty())
        return nullptr;
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid == guid)
            return player.Alive ? &player : nullptr;
    return nullptr;
}

inline ShieldReserve SearingFlameReserve(Facts const& facts)
{
    ShieldReserve reserve;
    if (!facts.Boss)
        return reserve;
    float threshold = NextSearingHealthPctFromAir;
    if (facts.CurrentPhase != Phase::Air)
    {
        threshold = NextSearingHealthPctFromGround;
        bool const pending = facts.SearingFlameChannel || facts.SearingFlameInMs
            || !facts.GroundTimersPublished;
        reserve.CurrentPhase = pending ? 1 : 0;
    }
    reserve.NextPhase = facts.Boss->HealthPct > threshold ? 1 : 0;
    return reserve;
}

// The shields left and what each kind of strike may spend of them.
struct ShieldBudget
{
    std::size_t Available = 0;
    ShieldReserve Reserve;

    // Searing Flame itself may take the last shield.
    bool AllowsSearingFlame() const { return Available > 0; }
    // A 90-Sound emergency (Devastation) spends down to this phase's interrupt.
    bool AllowsEmergency() const { return Available > Reserve.CurrentPhase; }
    // Air strikes (and the pre-liftoff reset) keep every interrupt.
    bool AllowsAirStrike() const { return Available > Reserve.Total(); }
    // An elective 80-Sound gong keeps one spare on top.
    bool AllowsElective() const { return Available > Reserve.Total() + 1; }
    std::size_t AirStrikesLeft() const
    {
        return AllowsAirStrike() ? Available - Reserve.Total() : 0;
    }
};

inline ShieldBudget BuildShieldBudget(Facts const& facts)
{
    return { facts.Shields.size(), SearingFlameReserve(facts) };
}

// Available shields ordered by distance to the ground tank anchor (GUID
// breaks ties). Rank 0 is the gong owner's, rank 1 the backup's.
inline std::optional<ShieldFact> DutyShield(Facts const& facts, std::size_t rank)
{
    std::vector<ShieldFact> shields = facts.Shields;
    std::stable_sort(shields.begin(), shields.end(),
        [](ShieldFact const& left, ShieldFact const& right)
        {
            return Geometry::Distance2d(left.Position, TankAnchor)
                < Geometry::Distance2d(right.Position, TankAnchor);
        });
    if (rank >= shields.size())
        return std::nullopt;
    return shields[rank];
}

// Ground stand point: inside the shield toward the tank anchor.
inline Vector3 ShieldStandPoint(ShieldFact const& shield)
{
    float const bearing = Geometry::Bearing(shield.Position, TankAnchor);
    return Geometry::PointAt(shield.Position, bearing, ShieldStandInset,
        ArenaCenter.Z);
}

inline std::optional<ShieldFact> NearestShield(Facts const& facts,
    Vector3 const& from)
{
    std::optional<ShieldFact> best;
    float bestDistance = 0.0f;
    for (ShieldFact const& shield : facts.Shields)
    {
        float const distance = Geometry::Distance3d(from, shield.Position);
        if (!best || distance < bestDistance)
        {
            best = shield;
            bestDistance = distance;
        }
    }
    return best;
}

inline bool IsKiter(Facts const& facts, ObjectGuid guid)
{
    return !guid.IsEmpty() && (guid == facts.GroundKiter || guid == facts.AirKiter);
}

// The living non-tank player closest to any shield (a kiter never leaves
// its kite to gong).
inline ObjectGuid NearestShieldPlayer(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    ObjectGuid best;
    float bestDistance = 0.0f;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || player.Guid == duties.Tank || IsKiter(facts, player.Guid))
            continue;
        std::optional<ShieldFact> const shield = NearestShield(facts, player.Position);
        if (!shield)
            continue;
        float const distance = Geometry::Distance3d(player.Position, shield->Position);
        if (best.IsEmpty() || distance < bestDistance)
        {
            best = player.Guid;
            bestDistance = distance;
        }
    }
    return best;
}

// Ground clicker: the owner, else the backup, else the living non-tank
// player closest to any shield. A kiter never leaves its kite to gong
// (GroundKiter only exists while the breath is cast or channelled).
inline ObjectGuid GroundGonger(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    for (ObjectGuid guid : { duties.GongOwner, duties.GongBackup })
        if (FindLivingPlayer(board, guid) && !IsKiter(facts, guid))
            return guid;
    return NearestShieldPlayer(board, facts, duties);
}

inline GongDecision DecideGroundGong(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    GongDecision decision;
    if (facts.BossStunned)
        return decision;
    ShieldBudget const budget = BuildShieldBudget(facts);
    if (facts.SearingFlameChannel)
        decision.Reason = "searing_flame";
    else if (facts.MaxSound >= SoundEmergency)
    {
        // A player at 90+ Sound dies to Devastation: only this phase's
        // Searing Flame outranks that.
        if (!budget.AllowsEmergency())
        {
            decision.Withheld = "sound_emergency_at_reserve";
            return decision;
        }
        decision.Reason = "sound_emergency";
    }
    else if (facts.MaxSound >= SoundHigh
        && !(facts.SearingFlameInMs && *facts.SearingFlameInMs <= SearingSoonMs))
    {
        if (budget.AllowsElective())
            decision.Reason = "sound_high";
        else if (PreLiftoffSoundResetDue(facts) && budget.AllowsAirStrike())
        {
            // Only the elective budget (one spare on top of every interrupt)
            // refuses the gong; the last seconds before liftoff are the air
            // phase's first strike, which every interrupt still expected
            // leaves room for. Withholding it would start the chase above
            // the Sound bound with a spendable shield in hand.
            decision.Reason = "pre_liftoff_sound_reset";
        }
        else
        {
            decision.Withheld = "sound_high_at_reserve";
            return decision;
        }
    }
    else if (PreLiftoffSoundResetDue(facts))
    {
        // The kiter Sound bound (BotAtramedesSoundBound.h): the air phase's
        // first strike, taken before the flame can spawn on a loud player.
        if (!budget.AllowsAirStrike())
        {
            decision.Withheld = "pre_liftoff_sound_reset_at_reserve";
            return decision;
        }
        decision.Reason = "pre_liftoff_sound_reset";
    }
    else
        return decision;
    decision.Required = true;
    decision.Urgent = true;
    // The pre-liftoff reset has seconds left: whoever stands nearest a
    // shield strikes the nearest one.
    bool const reset = decision.Reason == "pre_liftoff_sound_reset";
    decision.Clicker = reset ? NearestShieldPlayer(board, facts, duties)
        : GroundGonger(board, facts, duties);
    if (ActorSnapshot const* clicker = FindLivingPlayer(board, decision.Clicker))
    {
        // The owner and backup strike their own duty shield when it is still
        // available; anyone else strikes the nearest.
        std::optional<ShieldFact> shield;
        if (!reset && decision.Clicker == duties.GongOwner)
            shield = DutyShield(facts, 0);
        else if (!reset && decision.Clicker == duties.GongBackup)
            shield = DutyShield(facts, 1);
        std::optional<ShieldFact> const nearest = NearestShield(facts, clicker->Position);
        if (!shield || (nearest && Geometry::Distance3d(clicker->Position, nearest->Position)
                <= ShieldClickDistance))
            shield = nearest;
        decision.Shield = shield;
    }
    return decision;
}
}

#endif
