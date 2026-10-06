"""Feedback-calibrated mouse yaw; wait for each delta before correcting again."""
import math
import statistics
from collections import deque


def angle(value):
    return (value + math.pi) % math.tau - math.pi


class CameraSteering:
    def __init__(self, *, minimum_deadband=.04, maximum_deadband=.18):
        self.samples=deque(maxlen=12);self.pending=None;self.last_direction=0
        self.opposite_samples=0;self.previous_uptime=None
        self.minimum_deadband=minimum_deadband;self.maximum_deadband=maximum_deadband

    def update(self, facing, uptime, error, distance, tolerance):
        period=.1 if self.previous_uptime is None else ((uptime-self.previous_uptime)%2**32)/1000
        self.previous_uptime=uptime
        period=max(.02,min(.2,period))
        info={'bearing_error_radians':error,'pending_yaw':bool(self.pending),'samples':len(self.samples)}
        if self.pending:
            elapsed=((uptime-self.pending['uptime'])%2**32)/1000
            change=angle(facing-self.pending['facing'])
            if abs(change)<.002:
                if elapsed>1:raise RuntimeError('camera steering did not produce observed yaw')
                return 0,info
            rate=change/self.pending['pixels']
            if .00005<abs(rate)<.1:self.samples.append(rate)
            self.pending=None
        deadband=max(self.minimum_deadband,min(self.maximum_deadband,math.atan2(tolerance,max(distance,tolerance))))
        info['alignment_tolerance_radians']=deadband
        if abs(error)<=deadband:
            self.opposite_samples=0
            return 0,info
        direction=1 if error>0 else -1
        if self.last_direction and direction!=self.last_direction:
            self.opposite_samples+=1
            if self.opposite_samples<2:return 0,info
        else:self.opposite_samples=0
        # The first pulse is a small calibration probe, not a claimed client
        # sensitivity. Subsequent deltas use measured radians per EI pixel.
        sensitivity=statistics.median(self.samples) if self.samples else -.003
        # Mouse-look is a relative position command, not a timed turn key.
        # Once sensitivity is measured, aim at the bearing in one delta and
        # wait for feedback before issuing a correction.
        desired=direction*max(0,abs(error)-deadband*.5)
        pixels=round(desired/sensitivity) if self.samples else -8*direction
        pixels=max(-1024,min(1024,pixels))
        if not pixels:return 0,info
        self.pending={'facing':facing,'uptime':uptime,'pixels':pixels}
        self.last_direction=direction;self.opposite_samples=0
        info.update(relative_pixels=pixels,radians_per_pixel=sensitivity,
            calibration_basis='observed yaw' if self.samples else 'small calibration probe')
        return pixels,info
