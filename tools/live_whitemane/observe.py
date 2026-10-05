"""Read current live movement from the owned screenshot's public addon pixels."""
import argparse
import json
import time
from pathlib import Path
from PIL import Image
from tools.client_compatibility.observation.telemetry import decode_image
from . import runtime
from .snapshot import decode_image as archaeology_image


def observe(output):
    output = Path(output).resolve()
    owner = runtime.owned_process()
    if not owner:
        raise RuntimeError('live client is absent')
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
            row = {'observed_at': started, 'runtime': owner, 'movement': state,
                   'frame': str(output), 'server': 'Whitemane live realm',
                   'source': 'normal_public_addon_api_rendered_pixels', 'calibration': calibration,
                   'archaeology': archaeology}
            runtime.write(output.with_suffix('.json'), row)
            return row
        except ValueError as error:
            errors.append(str(error))
            time.sleep(.25)
    raise RuntimeError('live public observer is unavailable: ' + '; '.join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(observe(args.output)))


if __name__ == '__main__':
    main()
