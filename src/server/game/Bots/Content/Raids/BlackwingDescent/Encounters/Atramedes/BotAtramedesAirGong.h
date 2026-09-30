#ifndef TRINITY_BOT_ATRAMEDES_AIR_GONG_H
#define TRINITY_BOT_ATRAMEDES_AIR_GONG_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesArenaFloor.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesIceBlock.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <vector>

// Air phase: the Roaring Flame Breath kite ring, the gong relays and the
// rescue strike. A strike redirects the Reverberating Flame natively
// (spell_atramedes_resonating_clash_air): the flame stops, waits 2 s, flies
// to the struck shield, destroys it and then tracks the striker.
namespace BotEncounter::Atramedes
{
// Reverberating Flame: speed_run 0.714 of the 7 yd/s base (5 yd/s), +20% of
// that per Building Speed stack, one stack per second up to the server cap
// (BuildingSpeedMaxStacks); its breath (78353) reaches 5 yd every 0.5 s.
inline constexpr float FlameBaseSpeed = 5.0f;
inline constexpr float FlameSpeedPerStack = 1.0f;
// Unbuffed player run speed; a running speed buff (Sprint, Dash, ...) is read
// from the kiter's auras (Mobility::RunSpeed).
inline constexpr float KiterSpeed = Mobility::BaseRunSpeed;
// Strike when contact is this close: the spellclick lands within one
// decision tick and the flame stops at once (SetGUID interrupts and stops it).
inline constexpr float RescueLeadSeconds = 1.0f;
// A kite extension is only worth taking when it pushes contact at least this
// much later (and past the rescue lead).
inline constexpr float ExtensionGainSeconds = 0.5f;
// Speed buffs gain over their whole duration, so a chased player takes one
// once contact is this close; leaps (Blink, Disengage) wait for contact.
inline constexpr float SpeedBuffLeadSeconds = 4.0f;
// Inside the breath, an extension may still be tried while the flame has at
// most this many Building Speed stacks (it has just spawned on or re-tracked
// the kiter): a failed cast then costs at most 2 s of breath.
inline constexpr uint8 ExtensionGraceStacks = 1;
// Striker ranking: yards of ready mobility and flame distance add up; keeping
// an in-range relay shield for a later first catch is worth this much.
inline constexpr float RelayKeepBonusYards = 15.0f;
// A shield counts as ahead of the kiter unless it lies more than this far
// behind it (toward the flame) around the arena centre.
inline constexpr float AheadToleranceRad = 10.0f * Geometry::Pi / 180.0f;
// Ring waypoints sit this far onward (arc) past their shield's inset point,
// so a runner who reaches one has passed its shield inside spellclick reach.
inline constexpr float RingWaypointAheadArc = 3.0f;
// A runner this close to a waypoint has reached it and heads for the next.
inline constexpr float WaypointArrivalYards = 2.0f;
// Atramedes hovers at LiftoffPosition for the air phase (boss_atramedes_shared.h).
inline constexpr Vector3 HoverPoint{ 130.655f, -226.637f, 113.21f };
// Spell::CheckRange is 3D: 40 yd spell range + 1.5 player reach + 20 boss
// reach. The relays are the best ranged damage dealers and must keep casting.
inline constexpr float RangedEnvelope = 40.0f + 1.5f + BossCombatReach;
// Relay stations stand this far from their shield toward the hover point
// (10.15 yd 3D from the shield; 10.5 plus the hold tolerance would leave the
// 11.5 yd click reach) ...
inline constexpr float RelayStationInset = 10.0f;
// ... and are held within this. The whole hold area must stay inside both
// the click reach (<= 11.14 yd 3D from the shield) and the spell envelope
// less a small margin.
inline constexpr float RelayStationTolerance = 1.0f;
inline constexpr float RelayRangeMargin = 0.25f;
// With this few shields left and none with a station in range, a relay still
// guards the shield nearest the hover point, if the budget allows a strike:
// the rescue outweighs the damage.
inline constexpr std::size_t SparseShieldCount = 3;

// Circling direction around the arena centre away from `chaser`, clockwise
// while it sits on `self`.
inline int RingDirectionAwayFrom(Vector3 const& self, Vector3 const& chaser)
{
    int const away = Geometry::AwayFromChaser(ArenaCenter, self, chaser);
    return away ? away : -1;
}

// Air kite direction: away from the flame chasing the kiter.
inline int AirKiteDirection(Facts const& facts, ActorSnapshot const& kiter)
{
    if (ActorSnapshot const* flame = KiterFlame(facts, kiter))
        return RingDirectionAwayFrom(kiter.Position, flame->Position);
    return -1;
}

// The striker of an air gong while its flame is still being redirected (no
// kiter yet): it is the next kiter and must already run. The aura lasts 15 s
// and strikes can come 6-10 s apart, so the latest striker (the aura that
// expires last) is the one the flame will track.
inline ActorSnapshot const* AirRedirectRunner(Blackboard const& board,
    Facts const& facts)
{
    if (facts.CurrentPhase != Phase::Air || !facts.AirKiter.IsEmpty()
        || facts.ReverberatingFlames.empty())
        return nullptr;
    ActorSnapshot const* latest = nullptr;
    uint64 latestExpiry = 0;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive)
            if (AuraSnapshot const* clash = FindAura(player, AirClashAura))
                if (!latest || clash->ExpiresAtMs > latestExpiry)
                {
                    latest = &player;
                    latestExpiry = clash->ExpiresAtMs;
                }
    return latest;
}

// Ring waypoint of one shield spawn for a runner circling in `direction`:
// 4 yd inside the shield toward the arena centre, then RingWaypointAheadArc
// onward (2D 5 yd, 3D about 5.3 yd from the shield: inside spellclick reach).
inline Vector3 RingWaypoint(ShieldSpawn const& spawn, int direction)
{
    Vector3 const shield{ spawn.X, spawn.Y, spawn.Z };
    Vector3 const inset = Geometry::PointAt(shield,
        Geometry::Bearing(shield, ArenaCenter), ShieldStandInset, ArenaCenter.Z);
    float const radius = std::max(1.0f, Geometry::Distance2d(ArenaCenter, inset));
    return Geometry::PointAt(ArenaCenter, Geometry::Bearing(ArenaCenter, inset)
        + float(direction) * RingWaypointAheadArc / radius, radius, ArenaCenter.Z);
}

// The next ring waypoint ahead of `self` in `direction`: the smallest angular
// step ahead, skipping the one it is standing on. Every waypoint is reached
// (none is skipped for being close), so the runner passes every shield.
inline std::optional<Vector3> NextRingWaypoint(Vector3 const& self, int direction)
{
    float const selfBearing = Geometry::Bearing(ArenaCenter, self);
    std::optional<Vector3> best;
    float bestAhead = 0.0f;
    for (ShieldSpawn const& spawn : ShieldSpawns)
    {
        Vector3 const waypoint = RingWaypoint(spawn, direction);
        if (Geometry::Distance2d(self, waypoint) <= WaypointArrivalYards)
            continue;
        float const ahead = Geometry::AngleDelta(
            Geometry::Bearing(ArenaCenter, waypoint), selfBearing) * float(direction);
        if (ahead <= 0.0f)
            continue;
        if (!best || ahead < bestAhead)
        {
            best = waypoint;
            bestAhead = ahead;
        }
    }
    if (best)
        return best;
    // Every waypoint lies behind within half a turn: take the nearest-ahead
    // one past the half turn.
    for (ShieldSpawn const& spawn : ShieldSpawns)
    {
        Vector3 const waypoint = RingWaypoint(spawn, direction);
        float ahead = Geometry::AngleDelta(Geometry::Bearing(ArenaCenter, waypoint),
            selfBearing) * float(direction);
        if (ahead <= 0.0f)
            ahead += Geometry::TwoPi;
        if (Geometry::Distance2d(self, waypoint) > WaypointArrivalYards
            && (!best || ahead < bestAhead))
        {
            best = waypoint;
            bestAhead = ahead;
        }
    }
    return best;
}

// Seconds until the flame's breath (5 yd) reaches the kiter, with the kiter
// running at `speed` from `extraYards` farther away and the flame gaining one
// stack a second until the cap. Separation d(t) = d0 + c t - a t^2 / 2. A
// kiter already inside the breath that cannot get out before the flame
// accelerates past it is in contact now; one that gets out is caught again
// at the later root.
inline float FlameTimeToContact(ActorSnapshot const& flame, ActorSnapshot const& kiter,
    float speed, float extraYards = 0.0f)
{
    constexpr float never = std::numeric_limits<float>::infinity();
    uint8 const stacks = BuildingSpeedStacks(flame);
    float const d0 = Geometry::Distance2d(flame.Position, kiter.Position) + extraYards;
    float const c = speed - (FlameBaseSpeed + FlameSpeedPerStack * float(stacks));
    float const a = stacks < BuildingSpeedMaxStacks ? FlameSpeedPerStack : 0.0f;
    float const reach = FlameBreathRadius;
    if (d0 <= reach)
    {
        if (c <= 0.0f)
            return 0.0f;
        if (a <= 0.0f)
            return never;
        if (d0 + c * c / (2.0f * a) <= reach)
            return 0.0f;
        return (c + std::sqrt(c * c + 2.0f * a * (d0 - reach))) / a;
    }
    if (a <= 0.0f)
        return c >= 0.0f ? never : (d0 - reach) / -c;
    return (c + std::sqrt(c * c + 2.0f * a * (d0 - reach))) / a;
}

// At the kiter's current run speed (a running Sprint or Dash included).
inline float FlameTimeToContact(ActorSnapshot const& flame, ActorSnapshot const& kiter)
{
    return FlameTimeToContact(flame, kiter, Mobility::RunSpeed(kiter));
}

// Contact time once `extension` is used: a speed buff runs the kiter faster,
// a leap (Blink, Disengage) puts its yards between it and the flame.
inline float TimeToContactAfter(ActorSnapshot const& flame, ActorSnapshot const& kiter,
    Mobility::Ability const& extension)
{
    if (extension.Type == Mobility::Kind::Speed)
        return FlameTimeToContact(flame, kiter, std::max(Mobility::RunSpeed(kiter),
            Mobility::BaseRunSpeed * (1.0f + extension.SpeedPct / 100.0f)));
    return FlameTimeToContact(flame, kiter, Mobility::RunSpeed(kiter), extension.Yards);
}

// The chased player's next kite extension (user raid experience,
// 2026-09-25: mobile players "can outrun the laser longer"): among the ready
// abilities, the one that puts contact latest. Speed buffs from
// SpeedBuffLeadSeconds, leaps only at contact. Inside the breath (contact
// now) only right after the flame took the kiter (ExtensionGraceStacks) or
// right out of Ice Block (Hypothermia), so a failed cast costs at most 2 s.
inline std::optional<Mobility::Extension> KiteExtension(ActorSnapshot const& flame,
    ActorSnapshot const& kiter, float timeToContact)
{
    if (IsIced(kiter) || timeToContact > SpeedBuffLeadSeconds)
        return std::nullopt;
    if (timeToContact <= 0.0f && BuildingSpeedStacks(flame) > ExtensionGraceStacks
        && !FindAura(kiter, HypothermiaAura))
        return std::nullopt;
    Mobility::Ability const* best = nullptr;
    float bestContact = std::max(timeToContact, 0.0f) + ExtensionGainSeconds;
    for (Mobility::Ability const* ability : Mobility::ReadyAbilities(kiter))
    {
        if (ability->Type != Mobility::Kind::Speed && timeToContact > RescueLeadSeconds)
            continue;
        float const contact = TimeToContactAfter(flame, kiter, *ability);
        if (contact > bestContact && contact > RescueLeadSeconds + ExtensionGainSeconds)
        {
            best = ability;
            bestContact = contact;
        }
    }
    if (!best)
        return std::nullopt;
    return Mobility::ExtensionFor(kiter, *best);
}

// A shield is ahead of the kiter unless it lies behind it (toward the flame)
// around the arena centre in the kite direction.
inline bool ShieldAhead(ShieldFact const& shield, ActorSnapshot const& kiter,
    int direction)
{
    float const offset = Geometry::AngleDelta(
        Geometry::Bearing(ArenaCenter, shield.Position),
        Geometry::Bearing(ArenaCenter, kiter.Position)) * float(direction);
    return offset >= -AheadToleranceRad;
}

// The flame is on top of the kiter: "ahead" no longer means anything (a
// faster flame's predictive follow can overshoot it), any shield will do.
inline bool FlameOnKiter(ActorSnapshot const* flame, ActorSnapshot const& kiter)
{
    return flame && Geometry::Distance2d(flame->Position, kiter.Position)
        <= FlameBreathRadius;
}

// Seconds the kiter needs to come within reach of the next available shield
// ahead of `current` (the one it can strike now). Infinite when none is left.
inline float SecondsToNextShield(Facts const& facts, ActorSnapshot const& kiter,
    ShieldFact const& current, int direction)
{
    float const selfBearing = Geometry::Bearing(ArenaCenter, kiter.Position);
    std::optional<ShieldFact> next;
    float nextAhead = 0.0f;
    for (ShieldFact const& shield : facts.Shields)
    {
        if (shield.Guid == current.Guid
            || Geometry::Distance3d(kiter.Position, shield.Position) <= ShieldClickDistance)
            continue;
        float ahead = Geometry::AngleDelta(Geometry::Bearing(ArenaCenter, shield.Position),
            selfBearing) * float(direction);
        if (ahead <= 0.0f)
            ahead += Geometry::TwoPi;
        if (!next || ahead < nextAhead)
        {
            next = shield;
            nextAhead = ahead;
        }
    }
    if (!next)
        return std::numeric_limits<float>::infinity();
    float const distance = Geometry::Distance2d(kiter.Position, next->Position)
        - (ShieldClickDistance - 1.0f);
    return std::max(0.0f, distance) / Mobility::RunSpeed(kiter);
}

inline std::optional<ShieldFact> NearestAheadShield(Facts const& facts,
    ActorSnapshot const& kiter, int direction)
{
    std::optional<ShieldFact> best;
    float bestDistance = 0.0f;
    for (ShieldFact const& shield : facts.Shields)
    {
        if (!ShieldAhead(shield, kiter, direction))
            continue;
        float const distance = Geometry::Distance3d(kiter.Position, shield.Position);
        if (!best || distance < bestDistance)
        {
            best = shield;
            bestDistance = distance;
        }
    }
    return best ? best : NearestShield(facts, kiter.Position);
}

// Relay station: RelayStationInset from the shield toward the hover point.
inline Vector3 AirStationPoint(ShieldFact const& shield)
{
    return Geometry::PointAt(shield.Position,
        Geometry::Bearing(shield.Position, HoverPoint), RelayStationInset,
        ArenaCenter.Z);
}

// A relay held anywhere within RelayStationTolerance of the station can
// still cast at the hovering boss.
inline bool StationInRange(Vector3 const& station)
{
    return Geometry::Distance3d(station, HoverPoint) + RelayStationTolerance
        <= RangedEnvelope - RelayRangeMargin;
}

// ... and still click its shield.
inline bool StationInReach(Vector3 const& station, ShieldFact const& shield)
{
    return Geometry::Distance3d(station, shield.Position) + RelayStationTolerance
        <= ShieldClickDistance;
}

// A hold point no Sonar Bomb zone or fire patch reaches, with half a yard
// more than the exits keep (BombMarkerExit, FirePatchExit), so a relay
// holding it never steps out again.
inline bool StationHazardFree(Facts const& facts, Vector3 const& point)
{
    for (ActorSnapshot const* bomb : facts.BombMarkers)
        if (Geometry::Distance2d(bomb->Position, point) < SonarBombRadius + 2.0f)
            return false;
    for (ActorSnapshot const* patch : facts.FirePatches)
        if (Geometry::Distance2d(patch->Position, point) < FirePatchRadius + 2.0f)
            return false;
    return true;
}

// The relay's hold point at `shield`: its station, or, while a Sonar Bomb
// marker or fire patches cover it (the redirected flame lays its trail across
// the stations), the clear point in click reach of the same shield nearest
// to it, in spell range of the hovering boss when one is. A relay pushed off
// its station by a hazard would otherwise stand out of reach when the catch
// comes (the kiter Sound bound needs the strike at once).
inline Vector3 AirStationFor(Facts const& facts, ShieldFact const& shield)
{
    Vector3 const station = AirStationPoint(shield);
    if (StationHazardFree(facts, station))
        return station;
    float const toward = Geometry::Bearing(shield.Position, HoverPoint);
    std::optional<Vector3> best;
    bool bestInRange = false;
    float bestDistance = 0.0f;
    for (float radius : { RelayStationInset, 7.0f, 4.0f })
        for (float degrees : { 0.0f, 25.0f, -25.0f, 50.0f, -50.0f, 75.0f, -75.0f, 100.0f, -100.0f })
        {
            Vector3 const point = Geometry::PointAt(shield.Position,
                toward + degrees * Geometry::Pi / 180.0f, radius, ArenaCenter.Z);
            if (!StationHazardFree(facts, point) || !StationInReach(point, shield)
                || !ArenaFloor::Solid(point.X, point.Y))
                continue;
            bool const inRange = StationInRange(point);
            float const distance = Geometry::Distance2d(point, station);
            if (!best || (inRange && !bestInRange)
                || (inRange == bestInRange && distance < bestDistance))
            {
                best = point;
                bestInRange = inRange;
                bestDistance = distance;
            }
        }
    return best ? *best : station;
}

// Shields whose relay station is in spell range of the hovering boss and in
// click reach of its shield, nearest the hover point first. On the native
// spawns: 250128 (57.5 yd), 250126 (59.1), 250125 (59.5), 250122 (59.7) and
// 250129 (60.0); 250124 (60.5 + 1) misses the margin. When none is in range,
// SparseShieldCount or fewer shields are left and the budget still allows an
// air rescue, the one nearest the hover point is guarded anyway.
inline std::vector<ShieldFact> RelayShields(Facts const& facts)
{
    std::vector<ShieldFact> shields = facts.Shields;
    std::stable_sort(shields.begin(), shields.end(),
        [](ShieldFact const& left, ShieldFact const& right)
        {
            return Geometry::Distance3d(left.Position, HoverPoint)
                < Geometry::Distance3d(right.Position, HoverPoint);
        });
    std::vector<ShieldFact> inRange;
    for (ShieldFact const& shield : shields)
    {
        Vector3 const station = AirStationPoint(shield);
        if (StationInRange(station) && StationInReach(station, shield))
            inRange.push_back(shield);
    }
    if (inRange.empty() && !shields.empty() && shields.size() <= SparseShieldCount
        && BuildShieldBudget(facts).AllowsAirStrike())
        inRange.push_back(shields.front());
    return inRange;
}

// The gong owner's ground shield: the one nearest the tank anchor that is
// not an air relay shield, else the nearest at all.
inline std::optional<ShieldFact> GroundDutyShield(Facts const& facts)
{
    std::vector<ShieldFact> const relays = RelayShields(facts);
    std::optional<ShieldFact> best;
    std::optional<ShieldFact> bestAny;
    for (ShieldFact const& shield : facts.Shields)
    {
        float const distance = Geometry::Distance2d(shield.Position, TankAnchor);
        auto nearer = [distance](std::optional<ShieldFact> const& current)
        {
            return !current || distance < Geometry::Distance2d(current->Position, TankAnchor);
        };
        if (nearer(bestAny))
            bestAny = shield;
        bool const relay = std::any_of(relays.begin(), relays.end(),
            [&shield](ShieldFact const& candidate) { return candidate.Guid == shield.Guid; });
        if (!relay && nearer(best))
            best = shield;
    }
    return best ? best : bestAny;
}

// Relay shield of `guid`. The gong owner takes the station nearest the hover
// point and the backup the in-range one farthest from the owner's, so a
// strike far from the flame is at hand on either side of the room. The third
// gonger takes the shield farthest from both (a melee third, which cannot
// reach the flying boss anyway, any shield; a ranged one an in-range
// station). A relay that is the kiter or the redirect runner leaves its
// station empty; only when there is a single station does the backup take
// the owner's over.
inline std::optional<ShieldFact> AirRelayShieldFor(Blackboard const& board,
    Facts const& facts, DutyPlan const& duties, ObjectGuid guid)
{
    if (guid.IsEmpty() || (guid != duties.GongOwner && guid != duties.GongBackup
            && guid != duties.GongThird))
        return std::nullopt;
    ActorSnapshot const* runner = AirRedirectRunner(board, facts);
    auto active = [&board, &facts, runner](ObjectGuid relay)
    {
        return FindLivingPlayer(board, relay) && relay != facts.AirKiter
            && !(runner && runner->Guid == relay);
    };
    if (!active(guid))
        return std::nullopt;
    std::vector<ShieldFact> const shields = RelayShields(facts);
    if (guid == duties.GongThird)
    {
        ActorSnapshot const* third = FindLivingPlayer(board, guid);
        std::vector<ShieldFact> const& pool = IsMelee(*third) ? facts.Shields : shields;
        std::vector<ShieldFact> taken;
        for (ObjectGuid relay : { duties.GongOwner, duties.GongBackup })
            if (std::optional<ShieldFact> const other =
                    AirRelayShieldFor(board, facts, duties, relay))
                taken.push_back(*other);
        std::optional<ShieldFact> best;
        float bestApart = -1.0f;
        for (ShieldFact const& shield : pool)
        {
            float apart = std::numeric_limits<float>::max();
            for (ShieldFact const& other : taken)
                apart = std::min(apart, other.Guid == shield.Guid ? -1.0f
                    : Geometry::Distance2d(shield.Position, other.Position));
            if (apart > bestApart)
            {
                bestApart = apart;
                best = shield;
            }
        }
        return bestApart >= 0.0f ? best : std::nullopt;
    }
    if (shields.empty())
        return std::nullopt;
    if (guid == duties.GongOwner)
        return shields.front();
    // Backup.
    if (shields.size() == 1)
        return active(duties.GongOwner) ? std::nullopt
            : std::optional<ShieldFact>(shields.front());
    std::optional<ShieldFact> farthest;
    float apart = 0.0f;
    for (ShieldFact const& shield : shields)
    {
        float const distance = Geometry::Distance2d(shield.Position, shields.front().Position);
        if (shield.Guid != shields.front().Guid && distance > apart)
        {
            apart = distance;
            farthest = shield;
        }
    }
    return farthest;
}

// An assigned relay stands in reach of its own station's shield, or will
// before `withinSeconds` (a relay still walking to its station at liftoff):
// it will strike at contact, so a lone-kiter early strike would only waste a
// shield.
inline bool RelayInReach(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties, float withinSeconds = 0.0f)
{
    for (ObjectGuid relay : { duties.GongOwner, duties.GongBackup, duties.GongThird })
        if (ActorSnapshot const* player = FindLivingPlayer(board, relay))
            if (std::optional<ShieldFact> const shield =
                    AirRelayShieldFor(board, facts, duties, relay))
            {
                if (Geometry::Distance3d(player->Position, shield->Position)
                    <= ShieldClickDistance)
                    return true;
                float const walk = Geometry::Distance2d(player->Position,
                    AirStationFor(facts, *shield)) / Mobility::RunSpeed(*player);
                if (walk + RescueLeadSeconds <= withinSeconds)
                    return true;
            }
    return false;
}

// Best in-reach strike. The striker is the flame's next target, so its ready
// mobility (yards a kite extension adds) counts, as does the struck shield's
// distance from the flame (its next stop: the longer the relief), and a
// shield that is not an in-range relay shield (those few stations are every
// air phase's first catch) earns RelayKeepBonusYards. The kiter (the tank
// included: in the air Atramedes has no victim) may use shields ahead of it;
// any other bot but the tank may relay from its own shield. The Ice Block
// rescuer waiting for the flame holds still for its block and never strikes
// again.
inline void ChooseAirStrike(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties, ActorSnapshot const* kiter, ActorSnapshot const* flame,
    GongDecision& decision)
{
    int const direction = kiter ? AirKiteDirection(facts, *kiter) : -1;
    bool const anySide = kiter && FlameOnKiter(flame, *kiter);
    std::vector<ShieldFact> const relays = RelayShields(facts);
    auto isRelay = [&relays](ShieldFact const& shield)
    {
        return std::any_of(relays.begin(), relays.end(),
            [&shield](ShieldFact const& relay) { return relay.Guid == shield.Guid; });
    };
    float bestScore = -1.0f;
    for (ActorSnapshot const& player : board.Players)
    {
        bool const isKiter = kiter && player.Guid == kiter->Guid;
        if (!player.Alive || IsIced(player) || IceBaiting(board, facts, player)
            || (player.Guid == duties.Tank && !isKiter))
            continue;
        float const mobility = Mobility::ReadyYards(player);
        for (ShieldFact const& shield : facts.Shields)
        {
            if (Geometry::Distance3d(player.Position, shield.Position) > ShieldClickDistance)
                continue;
            if (isKiter && !anySide && !ShieldAhead(shield, *kiter, direction))
                continue;
            float const flameDistance = flame
                ? Geometry::Distance2d(flame->Position, shield.Position) : 0.0f;
            float const score = mobility + flameDistance
                + (isRelay(shield) ? 0.0f : RelayKeepBonusYards);
            if (score > bestScore)
            {
                bestScore = score;
                decision.Clicker = player.Guid;
                decision.Shield = shield;
            }
        }
    }
}

// The Ice Block rescue: a mage with Ice Block ready, not the kiter, in reach
// of a shield strikes, taking the flame on itself. Its shield: a non-relay
// one when it can, then the farthest from the flame.
inline bool ChooseIceBlockStrike(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties, ActorSnapshot const* kiter, ActorSnapshot const* flame,
    GongDecision& decision)
{
    ActorSnapshot const* mage = IceMage(board, facts, duties);
    if (!mage || (kiter && mage->Guid == kiter->Guid))
        return false;
    std::vector<ShieldFact> const relays = RelayShields(facts);
    float bestScore = -1.0f;
    for (ShieldFact const& shield : facts.Shields)
    {
        if (Geometry::Distance3d(mage->Position, shield.Position) > ShieldClickDistance)
            continue;
        bool const relay = std::any_of(relays.begin(), relays.end(),
            [&shield](ShieldFact const& other) { return other.Guid == shield.Guid; });
        float const score = (flame ? Geometry::Distance2d(flame->Position, shield.Position)
            : 0.0f) + (relay ? 0.0f : RelayKeepBonusYards);
        if (score > bestScore)
        {
            bestScore = score;
            decision.Clicker = mage->Guid;
            decision.Shield = shield;
        }
    }
    return bestScore >= 0.0f;
}

inline GongDecision DecideAirGong(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    GongDecision decision;
    ShieldBudget const budget = BuildShieldBudget(facts);
    ActorSnapshot const* kiter = FindLivingPlayer(board, facts.AirKiter);
    ActorSnapshot const* flame = kiter ? KiterFlame(facts, *kiter) : nullptr;
    // An iced kiter is immune to the breath: nothing to rescue.
    bool const iced = kiter && IsIced(*kiter);
    float const timeToContact = kiter && flame && !iced
        ? FlameTimeToContact(*flame, *kiter) : std::numeric_limits<float>::infinity();
    bool contact = timeToContact <= RescueLeadSeconds;
    // The kiter Sound bound (BotAtramedesSoundBound.h): the chased player
    // above the no-margin Sound, or about to be hit past the bound (the next
    // breath tick: within a tick of contact, or still inside the breath while
    // escaping it), is struck for at once: mobility and its own Ice Block
    // lower no Sound. During a redirect the same holds for the striker the
    // flame will track next. The Ice Block rescuer waiting for the flame
    // blocks it before the breath reaches it.
    std::string_view bound;
    if (kiter && flame && !iced && !IceBaiting(board, facts, *kiter))
        bound = SoundBoundGong(facts, *kiter, timeToContact <= BreathTickSeconds
            || Geometry::Distance2d(flame->Position, kiter->Position) <= BreathReachYards);
    else if (!kiter)
        if (ActorSnapshot const* runner = AirRedirectRunner(board, facts))
            if (!IceBaiting(board, facts, *runner))
                bound = SoundBoundGong(facts, *runner, false);
    // A chased mage with Ice Block available blocks the breath itself (after
    // its own rescue strike, or when the flame spawned on it): the
    // once-a-fight play, and no shield for this catch. A global cooldown
    // still running only delays the block (KiterAbility keeps it kiting), but
    // only while the block beats the breath: castable now, or ready by the
    // predicted contact less a decision step (IceBlockInTime). A block that
    // would come after contact takes breath ticks meanwhile, so the rescue
    // (or the mage's mobility) goes ahead instead.
    std::optional<Mobility::Extension> extension;
    if (bound.empty() && contact && IceBlockInTime(facts, *kiter, timeToContact))
    {
        contact = false;
        decision.Withheld = "kiter_ice_block";
    }
    // Otherwise the chased player uses its mobility before anyone strikes,
    // so the catch (and the shield) comes as late as the flame allows.
    else if (bound.empty() && contact
        && (extension = KiteExtension(*flame, *kiter, timeToContact)))
    {
        contact = false;
        decision.Withheld = "kiter_mobility_extension";
    }
    // A lone kiter at a shield ahead strikes now if the flame would catch it
    // before the next one (the west side has none for 105 yd). With a relay
    // in reach the relay strikes at contact instead: no shield is spent early.
    // A kiter with mobility left keeps running instead, and so does one whose
    // relay reaches its station before the flame reaches it.
    if (bound.empty() && kiter && flame && !iced && !contact && decision.Withheld.empty()
        && Mobility::ReadyAbilities(*kiter).empty() && !IceBlockUsable(facts, *kiter)
        && !RelayInReach(board, facts, duties, timeToContact))
    {
        int const direction = AirKiteDirection(facts, *kiter);
        for (ShieldFact const& shield : facts.Shields)
            if (Geometry::Distance3d(kiter->Position, shield.Position) <= ShieldClickDistance
                && ShieldAhead(shield, *kiter, direction)
                && timeToContact <= SecondsToNextShield(facts, *kiter, shield, direction)
                    + RescueLeadSeconds)
                contact = true;
    }
    bool const emergency = facts.MaxSound >= SoundEmergency;
    // Air strikes keep every Searing Flame interrupt still expected
    // (ShieldBudget); the Sound bound spends like a rescue.
    bool const rescue = (contact || !bound.empty()) && budget.AllowsAirStrike();
    // Both reset every Sound bar, so an emergency still gongs when contact
    // is true but the rescue budget is spent.
    bool const soundGong = emergency && budget.AllowsEmergency();
    if (!rescue && !soundGong)
    {
        if (!bound.empty())
            decision.Withheld = SoundBoundWithheld(bound);
        else if (contact)
            decision.Withheld = "air_breath_rescue_at_reserve";
        else if (emergency)
            decision.Withheld = "sound_emergency_at_reserve";
        return decision;
    }
    decision.Reason = !rescue ? std::string_view("sound_emergency")
        : !bound.empty() ? bound : std::string_view("air_breath_rescue");
    decision.Withheld = {};
    decision.Required = true;
    decision.Urgent = true;

    // The mage Ice Block play first while it is available, then the ranked
    // strike (user raid experience, 2026-09-25).
    if (rescue && ChooseIceBlockStrike(board, facts, duties, kiter, flame, decision))
    {
        decision.Reason = "air_ice_block_rescue";
        return decision;
    }
    ChooseAirStrike(board, facts, duties, kiter, flame, decision);
    if (!decision.Clicker.IsEmpty())
        return decision;
    if (kiter && rescue)
    {
        // Nobody in reach: the kiter runs for the nearest shield ahead, or
        // for the nearest at all once the flame is on top of it.
        decision.Clicker = kiter->Guid;
        decision.Shield = FlameOnKiter(flame, *kiter)
            ? NearestShield(facts, kiter->Position)
            : NearestAheadShield(facts, *kiter, AirKiteDirection(facts, *kiter));
        return decision;
    }
    if (ActorSnapshot const* walker =
            FindLivingPlayer(board, GroundGonger(board, facts, duties)))
    {
        decision.Clicker = walker->Guid;
        decision.Shield = NearestShield(facts, walker->Position);
    }
    return decision;
}

// A ground strike by a clicker in reach of a non-relay shield uses that one:
// the in-range relay shields are what the next air phase's first catch needs.
inline void KeepRelayShields(Blackboard const& board, Facts const& facts,
    GongDecision& decision)
{
    ActorSnapshot const* clicker = FindLivingPlayer(board, decision.Clicker);
    if (!clicker || !decision.Shield)
        return;
    std::vector<ShieldFact> const relays = RelayShields(facts);
    auto isRelay = [&relays](ShieldFact const& shield)
    {
        return std::any_of(relays.begin(), relays.end(),
            [&shield](ShieldFact const& relay) { return relay.Guid == shield.Guid; });
    };
    if (!isRelay(*decision.Shield))
        return;
    std::optional<ShieldFact> best;
    for (ShieldFact const& shield : facts.Shields)
    {
        float const distance = Geometry::Distance3d(clicker->Position, shield.Position);
        if (isRelay(shield) || distance > ShieldClickDistance)
            continue;
        if (!best || distance < Geometry::Distance3d(clicker->Position, best->Position))
            best = shield;
    }
    if (best)
        decision.Shield = best;
}

inline GongDecision DecideGong(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    if (!facts.Boss || facts.Shields.empty())
        return {};
    if (facts.CurrentPhase == Phase::Ground)
    {
        GongDecision decision = DecideGroundGong(board, facts, duties);
        KeepRelayShields(board, facts, decision);
        return decision;
    }
    if (facts.CurrentPhase == Phase::Air)
        return DecideAirGong(board, facts, duties);
    return {};
}
}

#endif
