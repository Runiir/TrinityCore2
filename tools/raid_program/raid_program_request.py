"""Resolve raid-level requests such as ``implement bwd 10n bots``.

Every alias comes from data: each prerequisite file
``experiments/configs/raid_prerequisites/<raid>.json`` contributes its raid key,
``name`` (with and without a leading "the"), native ``script_header`` (BWD, BoT,
FL, DS ...), the initials of its significant name words (``tofw``), its first
significant name word (``bastion``) and an optional ``aliases`` list. Raids that
only appear in the strategy catalog contribute their key. An alias that names
two raids is dropped, and a request that names both a raid and a boss is
refused. A request that is not a raid alias returns None, so boss-level
requests keep their unchanged resolution in ``scenario_catalog.resolve``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from tools.raid_program.development_graph import GraphError
from tools.raid_program.scenario_catalog import ALIASES as BOSS_ALIASES
from tools.raid_program.scenario_catalog import STRATEGIES, mode_name, words

PREREQUISITES = Path('experiments/configs/raid_prerequisites')
MODE_PATTERN = re.compile(r'(?<!\w)(10|25)\s*(?:(?:player|man)\s*)?(normal|heroic|hc|n|h)(?!\w)')
LEADING_VERBS = re.compile(r'^(?:implement|continue|resume|start|tune|run)\s+')
TRAILING = re.compile(r'\s+(?:raid\s+)?bots?$|\s+raid$')
ARTICLES = {'the'}
MINIMUM_FIRST_WORD = 4


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _raid_names(doc: dict, raid: str) -> set[str]:
    names = {words(raid)}
    name = words(str(doc.get('name') or ''))
    significant = [word for word in name.split() if word not in ARTICLES]
    if name:
        names |= {name, ' '.join(significant)}
    if len(significant) >= 2:
        names.add(''.join(word[0] for word in significant))
    if significant and len(significant[0]) >= MINIMUM_FIRST_WORD:
        names.add(significant[0])
    header = words(str(doc.get('script_header') or ''))
    if len(header) >= 2:
        names.add(header.replace(' ', ''))
    for alias in doc.get('aliases') or []:
        if isinstance(alias, str) and words(alias):
            names.add(words(alias))
    return {value for value in names if value}


def raid_alias_index(root: Path) -> dict[str, set[str]]:
    """Normalized alias -> raids it names (more than one means ambiguous)."""
    raids: dict[str, set[str]] = {}
    directory = root / PREREQUISITES
    for path in sorted(directory.glob('*.json')) if directory.is_dir() else []:
        doc = _read(path)
        raid = str(doc.get('raid') or path.stem)
        raids.setdefault(raid, set()).update(_raid_names(doc, raid))
    for raid in (_read(root / STRATEGIES).get('raids') or {}):
        raids.setdefault(str(raid), set()).add(words(str(raid)))
    index: dict[str, set[str]] = {}
    for raid, names in raids.items():
        for name in names:
            index.setdefault(name, set()).add(raid)
    return index


def raid_aliases(root: Path, raid: str) -> list[str]:
    return sorted(alias for alias, raids in raid_alias_index(root).items() if raids == {raid})


def _boss_names(root: Path) -> set[str]:
    names = {words(alias) for alias in BOSS_ALIASES}
    for raid in (_read(root / STRATEGIES).get('raids') or {}).values():
        for row in (raid.get('bosses') or []) if isinstance(raid, dict) else []:
            if isinstance(row, dict) and row.get('boss_slug'):
                names.add(words(str(row['boss_slug'])))
    return names


def _request_subject(request: str) -> tuple[str, list[re.Match]]:
    text = words(request)
    matches = list(MODE_PATTERN.finditer(text))
    if matches:
        text = text[:matches[0].start()] + ' ' + text[matches[0].end():]
    text = re.sub(r'\s+', ' ', text).strip()
    text = LEADING_VERBS.sub('', text)
    text = TRAILING.sub('', text).strip()
    return text, matches


def _supported_modes(root: Path, raid: str) -> set[str]:
    doc = _read(root / PREREQUISITES / f'{raid}.json')
    modes = {mode_name(token) for token in doc.get('difficulties') or [] if isinstance(token, str)}
    if modes:
        return modes
    raid_row = (_read(root / STRATEGIES).get('raids') or {}).get(raid) or {}
    return {mode for row in raid_row.get('bosses') or [] for mode in row.get('modes') or []}


def resolve_raid_request(root: Path, request: str, mode: str | None = None) -> dict | None:
    """``{'raid', 'mode'}`` for a raid-level request, None when the request names no raid."""
    subject, matches = _request_subject(request)
    raids = raid_alias_index(root).get(subject)
    if not raids:
        return None
    if len(raids) != 1:
        raise GraphError('ambiguous raid request: ' + subject + ' names ' + ', '.join(sorted(raids)))
    if subject in _boss_names(root):
        raise GraphError('request names both a raid and a boss: ' + subject + '; name the boss or the raid explicitly')
    if len(matches) > 1:
        raise GraphError('request contains multiple difficulties; select one scenario')
    embedded = mode_name(matches[0][0]) if matches else None
    chosen = mode_name(mode) if mode else embedded
    if not chosen or (embedded and embedded != chosen):
        raise GraphError('missing or conflicting raid size/difficulty')
    raid = next(iter(raids))
    if chosen not in _supported_modes(root, raid):
        raise GraphError('unsupported raid difficulty: ' + raid + ':' + chosen)
    return {'raid': raid, 'mode': chosen}
