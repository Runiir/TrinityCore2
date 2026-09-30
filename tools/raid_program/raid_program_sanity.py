"""Run-sanity findings in ``program assess``.

``program assess`` imports ``tools.raid_program.run_sanity.sanity_findings``
(``(root, scenario, label) -> list[{check, severity, kill_id, detail, evidence}]``)
and runs it for every boss unit with a raid target that ran this round. A unit
with any ``blocking`` finding is not accepted, even when its verdict passes;
the next round's ``next_action`` and boss packet say "investigate before
tuning". A missing module fails ``assess`` loudly; a check that raises, or a
malformed finding, becomes a blocking finding so it can never pass silently.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from tools.raid_program.development_graph import GraphError

SEVERITIES = ('blocking', 'warn')
EVIDENCE_LIMIT = 2000
Check = Callable[[Path, str, str], list]


def load_sanity() -> Check:
    """The sanity check, or GraphError: assess never skips it."""
    try:
        from tools.raid_program.run_sanity import sanity_findings
    except ImportError as error:
        raise GraphError('program assess needs tools.raid_program.run_sanity.sanity_findings(root, scenario, label) '
                         f'and cannot import it ({error}); restore that module, then assess again') from error
    return sanity_findings


def _finding(check: str, detail: str, severity: str = 'blocking', kill_id=None, evidence=None) -> dict:
    return {'check': check, 'severity': severity, 'kill_id': kill_id, 'detail': detail, 'evidence': evidence or {}}


def _normalize(row) -> dict:
    if not isinstance(row, dict) or not isinstance(row.get('check'), str) or row.get('severity') not in SEVERITIES:
        return _finding('sanity_finding_malformed', 'run_sanity returned a malformed finding: ' + repr(row)[:300])
    evidence = row.get('evidence') if isinstance(row.get('evidence'), dict) else {}
    encoded = json.dumps(evidence, sort_keys=True, default=str)
    if len(encoded) > EVIDENCE_LIMIT:
        evidence = {'truncated': True, 'bytes': len(encoded)}
    kill_id = row.get('kill_id')
    return _finding(row['check'], str(row.get('detail') or ''), row['severity'],
                    kill_id if isinstance(kill_id, str) else None, json.loads(json.dumps(evidence, default=str)))


def unit_findings(check: Check, root: Path, scenario: str, label: str) -> list[dict]:
    try:
        rows = check(root, scenario, label)
    except Exception as error:  # noqa: BLE001 - a broken check keeps the unit open, it never passes it
        return [_finding('sanity_check_failed', f'run_sanity raised {type(error).__name__}: {error}'[:400])]
    if not isinstance(rows, list):
        return [_finding('sanity_finding_malformed', 'run_sanity did not return a list')]
    return [_normalize(row) for row in rows]


def blocking(findings: list[dict] | None) -> list[dict]:
    return [row for row in findings or [] if row.get('severity') == 'blocking']


def describe(row: dict) -> str:
    kill = f" [{row['kill_id']}]" if row.get('kill_id') else ''
    return f"{row['check']}{kill}: {row.get('detail') or 'no detail'}"


def assessment_lines(assessment: dict | None) -> tuple[list[str], list[str]]:
    """(blocking, warn) lines of one round assessment, 'boss: check [kill]: detail'."""
    blocked, warned = [], []
    for boss, result in ((assessment or {}).get('units') or {}).items():
        for row in result.get('sanity') or []:
            (blocked if row.get('severity') == 'blocking' else warned).append(f'{boss}: {describe(row)}')
    return blocked, warned
