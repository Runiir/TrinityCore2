"""Read public addon facts through the own relay, or the explicit pixel mode."""
import argparse
import json
import time
from pathlib import Path
from PIL import Image
from tools.client_compatibility.observation.telemetry import decode_image
from . import runtime
from .snapshot import decode_image as archaeology_image
from . import own_pose
from . import farm_ui
from . import addon_relay


def attach_pose(row):
    row.setdefault('owned_pose',None)
    pose_file=runtime.ROOT/'run/movement_pose.json'
    if pose_file.exists():
        try:
            pose=json.loads(pose_file.read_text())
            feed=json.loads((runtime.ROOT/'run/bearing_reader.json').read_text())
            if (feed['status']=='ready' and feed['pid']==pose['reader_pid']
                    and feed['start_ticks']==pose['reader_start_ticks']
                    and runtime.proc_start(feed['pid'])==feed['start_ticks']):
                row['owned_pose']=own_pose.match(row,pose,now=time.time())
        except (ValueError,KeyError,FileNotFoundError,ProcessLookupError):pass
    if row['owned_pose']:
        row['archaeology']['altitude_yards']=row['owned_pose']['height_yards']
        row['archaeology']['altitude_source']=row['owned_pose']['source']
    from .survey_find import attach
    return attach(row,time.time())


def observe(output):
    from .resources import check
    check()
    output = Path(output).resolve()
    owner = runtime.owned_process()
    if not owner:
        raise RuntimeError('live client is absent')
    mode=runtime.ROOT/'run/observation_mode.json'
    setting=json.loads(mode.read_text()) if mode.exists() else {}
    if setting.get('transport')=='local_tiles':
        from .telemetry_tiles import observation
        try:row=observation(extension=setting.get('extension',True))
        except (ValueError,KeyError) as error:raise RuntimeError('local public tiles unavailable: '+str(error)) from error
        attach_pose(row)
        from .minimap_finds import signal
        row['minimap_finds']=signal(row)
        runtime.write(output.with_suffix('.json'),row)
        return row
    direct_required=setting.get('transport')=='addon_relay'
    if direct_required:
        # The loop never silently falls back to expensive or unavailable pixels.
        try:row=addon_relay.observation(owner,runtime.ROOT)
        except (ValueError,KeyError,FileNotFoundError) as error:
            raise RuntimeError('direct public addon feed unavailable: '+str(error)) from error
        attach_pose(row);runtime.write(output.with_suffix('.json'),row)
        return row
    errors = []
    calibration_file = runtime.ROOT / 'run/observer_calibration.json'
    calibration = json.loads(calibration_file.read_text()) if calibration_file.exists() else {'x': 16, 'y': 16, 'cell_size': 4}
    for _ in range(3):
        started = time.time()
        runtime.screenshot(output)
        try:
            with Image.open(output) as frame:
                state = decode_image(frame, **{k: calibration[k] for k in ('x','y','cell_size')})
                archaeology = archaeology_image(frame, x=calibration.get('archaeology_x', calibration['x']),
                    y=calibration.get('archaeology_y', 89.4),
                    cell_size=calibration.get('archaeology_cell_size', calibration['cell_size'] * .75))
                ui,ui_error = None,None
                try:
                    if calibration.get('farm_ui'):
                        try:ui = farm_ui.decode_image(frame, **calibration['farm_ui'])
                        except ValueError as error:
                            if str(error)=='farm UI marker is absent':
                                ui,position=farm_ui.locate(frame,calibration.get('archaeology_cell_size',3.51))
                            elif str(error)=='farm UI checksum mismatch':
                                ui,position=farm_ui.recalibrate(frame,calibration['farm_ui'])
                            else:raise
                            if position:
                                calibration['farm_ui']=position;runtime.write(calibration_file,calibration)
                    else:
                        ui, position = farm_ui.locate(frame,calibration.get('archaeology_cell_size',3.51))
                        if position:
                            calibration['farm_ui']=position
                            runtime.write(calibration_file,calibration)
                except ValueError as error:ui_error=str(error)
            row = {'observed_at': started, 'runtime': owner, 'movement': state,
                   'frame': str(output), 'server': 'Whitemane live realm',
                   'source': 'normal_public_addon_api_rendered_pixels', 'calibration': calibration,
                   'archaeology': archaeology, 'farm_ui': ui,'farm_ui_error':ui_error}
            attach_pose(row)
            runtime.write(output.with_suffix('.json'), row)
            return row
        except ValueError as error:
            errors.append(str(error))
            time.sleep(.25)
    raise RuntimeError('live public observer is unavailable: ' + '; '.join(errors))


def setup_movement(output):
    """Read only the independent movement panel when repairing addon layout."""
    output=Path(output);runtime.screenshot(output)
    calibration=json.loads((runtime.ROOT/'run/observer_calibration.json').read_text())
    with Image.open(output) as image:
        movement=decode_image(image,**{k:calibration[k] for k in ('x','y','cell_size')})
    return {'runtime':runtime.owned_process(),'movement':movement,'frame':str(output),
            'setup_only':True,'source':'public_addon_movement_pixels'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(observe(args.output)))


if __name__ == '__main__':
    main()
