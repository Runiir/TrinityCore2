"""Pinned decision service identity, independent of the gameplay actor's name."""
import json
from . import runtime
from .ui_choice import MODEL, REVISION

VISION_MODEL = 'thaitea/laya-vision'
VISION_REVISION = 'f2fe3c12cb6d04c59d8a190250bf3fb40fc828dc'
VISION_CODE_REVISION = '9e1e2419d855ad3e1a2af4d4bd1ef6be5418842c'


def selected():
    path = runtime.ROOT / 'run/decision_backend.json'
    if not path.exists():
        return {'kind': 'text', 'model': MODEL, 'revision': REVISION, 'adapter': None}
    value = json.loads(path.read_text())
    if value != {'kind': 'vision', 'model': VISION_MODEL, 'revision': VISION_REVISION,
                 'code_revision': VISION_CODE_REVISION, 'adapter': None}:
        raise RuntimeError('unrecognized owned decision backend')
    return value


def vision_enabled():
    return selected()['kind'] == 'vision'


def identity(response):
    expected = selected()
    return {key: response.get(key, expected.get(key)) for key in
            ('model', 'revision', 'adapter', 'code_revision') if key in response or key in expected}


def validate(response, expected):
    if any(response.get(key) != expected.get(key) for key in ('model', 'revision', 'adapter')):
        raise RuntimeError('decision model identity changed')
    if expected['kind'] == 'vision' and (
            response.get('code_revision') != VISION_CODE_REVISION
            or response.get('model_saw_pixels') is not True):
        raise RuntimeError('vision code identity or image input changed')
