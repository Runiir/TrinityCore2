"""Execute a Laya-selected forward camera view using measured owned yaw."""
import fcntl
import math
import time
from . import inputs,runtime,native_control
from .observe import observe
from .camera_steering import CameraSteering,angle
from .sticky_input import StickyInput,observation_lease


def align(folder,before,target=None,*,ground_view=False):
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    from .camera_input import Input
    folder.mkdir(parents=True,exist_ok=False)
    ctl._launcher_env=runtime.client_environment
    native_input_adapter.lab=runtime;native_input_adapter.control=native_control
    desired=before['movement']['facing_radians']
    if target:
        world=before['archaeology']['world']
        desired=math.atan2(target['west']-world['west'],target['north']-world['north'])
    rows=[];steering=CameraSteering();started=time.monotonic()
    pitch_steering=CameraSteering(minimum_deadband=.01,maximum_deadband=.03)
    desired_pitch=math.pi/4 if ground_view else 0
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=inputs.focus('World of Warcraft');sender=Input();sticky=StickyInput(sender,lease=observation_lease(before))
        try:
            sticky.renew();sender.move(640,150);sticky.button(3,True)
            if ground_view and (before['archaeology']['flying'] or before['archaeology']['falling']):
                raise RuntimeError('ground camera view requires a grounded character')
            # Obtain a current owned movement sample even after a stationary
            # teleport. The tiny yaw probe also calibrates this input device.
            steering.pending={'facing':before['movement']['facing_radians'],
                'uptime':before['movement']['client_uptime_ms'],'pixels':-8}
            sticky.relative(-8,0)
            last_sequence=before['movement']['sequence'];aligned=0
            while time.monotonic()-started<8:
                row=observe(folder/'view.png');m=row['movement'];a=row['archaeology']
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead']
                        or m['in_combat'] or m['on_taxi'] or a['casting'] or m['speed']>0):
                    raise RuntimeError('camera view interrupted by player state')
                sticky.renew()
                if m['sequence']==last_sequence:time.sleep(.01);continue
                last_sequence=m['sequence'];error=angle(desired-m['facing_radians'])
                pixels,info=steering.update(m['facing_radians'],m['client_uptime_ms'],error,1,.18)
                pose=row.get('owned_pose') or {};pitch=pose.get('pitch_radians');vertical=0
                pitch_aligned=False;pitch_info=None
                if pitch is not None:
                    vertical,pitch_info=pitch_steering.update(pitch,pose['client_uptime_ms'],
                        desired_pitch-pitch,1,.03)
                    pitch_aligned=abs(desired_pitch-pitch)<=.03 and not pitch_steering.pending
                rows.append({'observed_at':row['observed_at'],**info,
                    'pitch_radians':pitch,'desired_pitch_radians':desired_pitch,'pitch_steering':pitch_info})
                if pixels or vertical:sticky.relative(pixels,vertical)
                aligned=aligned+1 if abs(error)<=.18 and not steering.pending and pitch_aligned else 0
                if aligned>=2:return rows
                time.sleep(.1)
            raise RuntimeError('camera view did not reach forward alignment')
        finally:
            sticky.close()
            runtime.write(folder/'camera_view.json',{'identity':identity,'observations':rows,
                'alignment_heading_radians':desired,'yaw_samples':list(steering.samples),
                'keyboard_turns':0,'forward_key_presses':0,'ground_view':ground_view,
                'desired_pitch_radians':desired_pitch,'pitch_samples':list(pitch_steering.samples),
                'pitch_basis':'authenticated owned pitch and measured EI sensitivity'})
