#ifndef TRINITY_BOT_RAID_DRUDGE_SEED_APPROACH_H
#define TRINITY_BOT_RAID_DRUDGE_SEED_APPROACH_H

#include <algorithm>
#include <cmath>

namespace BotRaidDrudgeSeedApproach
{
struct Point
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
};

struct Input
{
    Point Actor;
    Point Source;
    float MidpointX = 0.0f;
    float MidpointY = 0.0f;
    float AxisX = 0.0f;
    float AxisY = 0.0f;
    float LaneSign = 0.0f;
    float MinimumLaneProjection = 0.0f;
    float MinimumSourceDistance = 0.0f;
    float ActionMaxRange = 0.0f;
};

struct Result
{
    Point Destination;
    float Travel = 0.0f;
    float DesiredDistance = 0.0f;
    bool Needed = false;
    bool Safe = false;
};

inline Result Plan(Input const& input)
{
    Result result;
    float const dx = input.Source.X - input.Actor.X;
    float const dy = input.Source.Y - input.Actor.Y;
    float const distance = std::hypot(dx, dy);
    float const rangeInset = 1.0f;
    result.DesiredDistance = std::max(input.MinimumSourceDistance,
        input.ActionMaxRange - rangeInset);
    if (distance <= 0.001f || input.ActionMaxRange <= input.MinimumSourceDistance)
        return result;
    if (distance <= result.DesiredDistance)
    {
        result.Destination = input.Actor;
        result.Safe = true;
        return result;
    }

    result.Needed = true;
    result.Travel = distance - result.DesiredDistance;
    result.Destination = {
        input.Actor.X + dx * result.Travel / distance,
        input.Actor.Y + dy * result.Travel / distance,
        input.Actor.Z + (input.Source.Z - input.Actor.Z) * result.Travel / distance
    };
    float const projection =
        (result.Destination.X - input.MidpointX) * input.AxisX
        + (result.Destination.Y - input.MidpointY) * input.AxisY;
    result.Safe = input.LaneSign * projection >= input.MinimumLaneProjection;
    return result;
}
}

#endif
