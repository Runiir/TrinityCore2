"""Bounded position estimates for ordinary native ground movement splines.

Packet start coordinates are not a moving creature's current position. Decode
the native linear path, including quarter-yard packed deltas, then use its
recorded duration. Curved paths are explicitly approximate, never private state.
"""
import math
import struct


def signed(value,width):
    value&=(1<<width)-1
    return value-(1<<width) if value&(1<<(width-1)) else value


def path(spline):
    start=list(spline['position']);points=spline['points']
    if not points:return [start]
    if spline['flags']&0x400000:return [start,*points]
    end=points[0];middle=[(a+b)/2 for a,b in zip(start,end)];result=[start]
    for packed, in struct.iter_unpack('<I',spline['deltas']):
        delta=[signed(packed,11)*.25,signed(packed>>11,11)*.25,signed(packed>>22,10)*.25]
        result.append([a-b for a,b in zip(middle,delta)])
    return [*result,list(end)]


def estimate(spline,now):
    points=path(spline);duration=spline['duration']/1000
    elapsed=max(0,now-spline['observed_at'])
    if duration<=0 or len(points)==1:return points[0]
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])];total=sum(lengths)
    if not total:return points[-1]
    distance=total*min(1,elapsed/duration)
    for a,b,length in zip(points,points[1:],lengths):
        if distance<=length and length:
            ratio=distance/length;return [x+(y-x)*ratio for x,y in zip(a,b)]
        distance-=length
    return points[-1]
