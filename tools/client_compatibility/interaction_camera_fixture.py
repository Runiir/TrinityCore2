"""Reversible ordinary mouse-wheel camera setup, separate from model results."""
import time
from PIL import Image
from .observation.travel import decode_image


def zoom(t, label):
    _, frame = t.observe(label)
    with Image.open(t.out / frame['file']) as image:
        value = decode_image(image)['camera_zoom']
    return value, frame


def set_zoom(t, target, label):
    value, frame = zoom(t, label + '_before')
    row = {'source': 'code_fixture_mouse_wheel', 'target': target,
           'before': value, 'before_frame': frame, 'inputs': []}
    t.receipt.setdefault('camera_fixture', []).append(row); t.persist()
    for index in range(40):
        if abs(value - target) <= .1:
            row.update(after=value, restored_or_set=True); t.persist(); return
        button = 4 if value > target else 5
        t.io.click(1000, 360, button=button); time.sleep(.5)
        after, frame = zoom(t, label + f'_{index:02d}')
        row['inputs'].append({'button': button, 'before': value, 'after': after, 'frame': frame})
        t.persist()
        if abs(after - value) < .01:
            raise RuntimeError('camera fixture wheel made no progress')
        if (value - target) * (after - target) < 0 and abs(after - target) > .1:
            raise RuntimeError('camera target is not reachable by whole mouse-wheel steps')
        value = after
    raise RuntimeError('camera fixture exceeded its bounded wheel count')
