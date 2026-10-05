"""Read current live movement from the owned screenshot's public addon pixels."""
import argparse
import json
import time
from pathlib import Path
from PIL import Image
from tools.client_compatibility.observation.telemetry import decode_image
from . import runtime


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
                state = decode_image(frame, **calibration)
            row = {'observed_at': started, 'runtime': owner, 'movement': state,
                   'frame': str(output), 'server': 'Whitemane live realm',
                   'source': 'normal_public_addon_api_rendered_pixels', 'calibration': calibration}
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
