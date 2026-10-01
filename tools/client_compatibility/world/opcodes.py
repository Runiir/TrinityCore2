import json
from pathlib import Path

TABLES = json.loads(Path(__file__).with_name("opcodes.json").read_text())
MODERN = TABLES["modern"]
LEGACY = TABLES["legacy"]
MODERN_NAMES = {value: name for name, value in MODERN.items()}
LEGACY_NAMES = {value: name for name, value in LEGACY.items()}
