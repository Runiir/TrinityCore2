"""Round review and user decisions of a raid program, and their build gates.

Review (stage ``review``, between the last handoff and the build):

* ``round_diff`` is the round's source diff from the round base (the plan
  commit) to either the working tree (untracked, non-ignored files included) or
  a commit. Program bookkeeping (the state file and ``raid_programs/**``) is
  excluded, so committing the reviewed tree plus the state gives the same bytes
  and the same sha256 as the diff reviewed before the commit.
* ``program review-diff --output PATH`` writes the working-tree diff and prints
  its sha256 (read-only).
* ``program review --verdict accept|reject ...`` records one review. An accept
  moves the round to ``build``; a reject keeps (or puts) it in ``review``.
  ``--empty-diff`` records the automatic accept of a round with no source change.
* ``review_gate``: the build needs the latest review to be an accept whose sha256
  equals the committed round diff.

User decisions: a handoff may carry ``needs_user_decision`` items
``{id, question, options[], recommendation, context}``. They are recorded in the
round; ``resume`` then says ASK THE USER; ``program decide`` records the user's
exact words (source ``user``, with the date). ``decision_gate`` blocks the build
until every decision of the round is answered.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.raid_program import raid_program_packets as packets
from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError, utc_now

EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
BOOKKEEPING = (store.STATE_PATH.as_posix(), 'artifacts/cata_raid_program/raid_programs')
VERDICTS = ('accept', 'reject')
REVIEW_STAGES = ('review', 'build')
DECISION_FIELDS = {'id': str, 'question': str, 'options': list}
DECISION_TEXT = ('recommendation', 'context')
# Deterministic diff text whatever the user's git configuration.
_CONFIG = ['-c', 'diff.noprefix=false', '-c', 'diff.mnemonicPrefix=false', '-c', 'diff.relative=false',
           '-c', 'core.quotePath=true', '-c', 'color.ui=false', '-c', 'diff.external=']
_DIFF = ['diff', '--binary', '--full-index', '--no-renames', '--no-color', '--no-ext-diff', '--no-textconv',
         '--diff-algorithm=myers', '--src-prefix=a/', '--dst-prefix=b/']


def _git(root: Path, *args: str, env: dict | None = None, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(['git', '-C', str(root), *_CONFIG, *args], capture_output=True, text=text, check=False,
                          env=env)


def _tree(root: Path, commit: str) -> str:
    completed = _git(root, 'rev-parse', '--verify', '-q', commit + '^{tree}')
    if completed.returncode:
        raise GraphError(f'cannot resolve {commit} to a tree')
    return completed.stdout.strip()


def worktree_tree(root: Path) -> str:
    """The tree of the working tree (tracked changes and untracked, non-ignored files) via a scratch index."""
    head = rounds.git_head(root)
    index = _git(root, 'rev-parse', '--git-path', 'index').stdout.strip()
    source = Path(index) if Path(index).is_absolute() else root / index
    with tempfile.TemporaryDirectory(prefix='raid-program-review-') as folder:
        scratch = Path(folder) / 'index'
        if source.is_file():
            shutil.copy2(source, scratch)  # keeps the stat cache: only changed files are hashed again
        env = os.environ | {'GIT_INDEX_FILE': str(scratch)}
        steps = [('read-tree', head or '--empty'), ('add', '-A', '--', '.'), ('write-tree',)]
        for step in steps:
            completed = _git(root, *step, env=env)
            if completed.returncode:
                raise GraphError(f"git {step[0]} failed while snapshotting the working tree: {completed.stderr[-300:]}")
        return completed.stdout.strip()


def round_base(program: dict) -> str:
    return rounds.current_round(program).get('plan_commit') or EMPTY_TREE


def round_diff(root: Path, base: str, commit: str | None = None) -> bytes:
    """Diff bytes base..commit (``commit`` None: the working tree), bookkeeping excluded."""
    if commit is None:
        target = worktree_tree(root)
    else:
        target = _tree(root, commit) if rounds.git_head(root) or commit != 'HEAD' else EMPTY_TREE
    left = base if base == EMPTY_TREE else _tree(root, base)
    excludes = [f':(exclude){path}' for path in BOOKKEEPING]
    completed = _git(root, *_DIFF, left, target, '--', '.', *excludes, text=False)
    if completed.returncode:
        raise GraphError('git diff of the round failed: ' + completed.stderr.decode(errors='replace')[-300:])
    return completed.stdout


def diff_files(diff: bytes) -> list[str]:
    return sorted({line[len(b'diff --git a/'):].split(b' b/', 1)[0].decode(errors='replace')
                   for line in diff.splitlines() if line.startswith(b'diff --git a/')})


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def committed_sha(root: Path, program: dict, commit: str = 'HEAD') -> str:
    return sha256(round_diff(root, round_base(program), commit))


def review_diff(root: Path, output: Path) -> dict:
    """Write the round's working-tree diff to ``output`` (outside the source tree) and return its sha256."""
    _, program, _ = rounds.load_active(root)
    rounds.require(program, 'implement', *REVIEW_STAGES)
    target = output.expanduser().resolve()
    inside = target.is_relative_to(root.resolve())
    if inside and not target.is_relative_to((root / BOOKKEEPING[1]).resolve()):
        raise GraphError('write the review diff outside the source tree (for example ~/.cache/...): a file in the '
                         'tree would become part of the next diff')
    base = round_base(program)
    diff = round_diff(root, base)
    committed = round_diff(root, base, 'HEAD')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(diff)
    return {'schema': 'raid_program_review_diff_v1', 'program_id': program['program_id'], 'round': program['round'],
            'base': base, 'output': str(target), 'diff_sha256': sha256(diff), 'bytes': len(diff),
            'files': diff_files(diff), 'committed_diff_sha256': sha256(committed),
            'committed': sha256(committed) == sha256(diff),
            'excluded': list(BOOKKEEPING),
            'next_action': ('Give this file to a reviewer in a separate session; record the verdict with program review '
                            f'--verdict accept|reject --diff-sha256 {sha256(diff)} --reviewer NAME --report PATH '
                            '--expect <state_sha256>. Commit the reviewed tree before program build; the sha256 stays '
                            'the same after the commit.')}


def latest_review(holder: dict) -> dict | None:
    return (holder.get('reviews') or [None])[-1]


def record_review(root: Path, verdict: str | None, diff_sha256: str | None, reviewer: str | None,
                  report: Path | None, expected_sha256: str | None = None, empty_diff: bool = False) -> dict:
    """Record one review of the round diff; accept -> build, reject -> review."""
    _, program, data = rounds.load_active(root)
    rounds.require(program, *REVIEW_STAGES)
    rounds.check_expected(data, expected_sha256)
    base = round_base(program)
    worktree, committed = sha256(round_diff(root, base)), sha256(round_diff(root, base, 'HEAD'))
    if empty_diff:
        if worktree != sha256(b'') or committed != sha256(b''):
            raise GraphError('--empty-diff needs a round with no source change (bookkeeping excluded); run '
                             'program review-diff and have the diff reviewed')
        verdict, diff_sha256, reviewer, report_ref = 'accept', committed, 'none (empty round diff)', None
    else:
        if verdict not in VERDICTS or not diff_sha256 or not reviewer or report is None:
            raise GraphError('program review needs --verdict accept|reject, --diff-sha256, --reviewer and --report '
                             '(or --empty-diff)')
        if not report.expanduser().is_file():
            raise GraphError(f'review report {report} does not exist')
        report_ref = rounds.repo_ref(root, report.expanduser())
        if verdict == 'accept' and diff_sha256 not in (worktree, committed):
            raise GraphError('the accepted diff sha256 matches neither the working tree nor HEAD: the round changed '
                             'after the review; run program review-diff again and re-review')
    record = {'verdict': verdict, 'diff_sha256': diff_sha256, 'reviewer': reviewer, 'report': report_ref,
              'base': base, 'recorded_utc': utc_now(), 'automatic': empty_diff,
              'matches': {'worktree': diff_sha256 == worktree, 'committed': diff_sha256 == committed}}

    def reducer(state: dict) -> dict:
        target = rounds.active(state)
        rounds.require(target, *REVIEW_STAGES)
        rounds.current_round(target).setdefault('reviews', []).append(record)
        target['stage'] = 'build' if verdict == 'accept' else 'review'
        store.history(target, 'review', round=target['round'], verdict=verdict, reviewer=reviewer,
                      diff_sha256=diff_sha256)
        return state
    return store.update(root, reducer, expected_sha256)


def review_gate(root: Path, program: dict, commit: str = 'HEAD') -> dict:
    """The latest review must accept exactly the committed round diff (base..commit)."""
    holder = rounds.current_round(program)
    review = latest_review(holder)
    try:
        committed = committed_sha(root, program, commit)
    except GraphError as error:
        return {'ok': False, 'problem': str(error), 'committed_diff_sha256': None, 'review': review}
    problem = None
    if review is None:
        problem = 'no review of this round is recorded'
    elif review['verdict'] != 'accept':
        problem = f"the latest review ({review['reviewer']}) rejected the round"
    elif review['diff_sha256'] != committed:
        problem = ('the committed round diff changed since the accepted review (reviewed '
                   f"{review['diff_sha256'][:12]}, committed {committed[:12]}); run program review-diff and re-review")
    return {'ok': problem is None, 'problem': problem, 'committed_diff_sha256': committed,
            'review': {key: review.get(key) for key in ('verdict', 'reviewer', 'diff_sha256', 'recorded_utc')}
            if review else None}


def validate_decisions(items) -> list[dict]:
    """Normalized needs_user_decision items of a handoff (the field is optional)."""
    if items is None:
        return []
    if not isinstance(items, list):
        raise GraphError('needs_user_decision must be a list of {id, question, options, recommendation, context}')
    normalized, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or any(not isinstance(item.get(name), kind) for name, kind in DECISION_FIELDS.items()):
            raise GraphError('each needs_user_decision item needs id (str), question (str) and options (list)')
        if not item['id'].strip() or not item['question'].strip() or item['id'] in seen:
            raise GraphError('needs_user_decision ids and questions must be non-empty and ids unique')
        if any(not isinstance(option, str) for option in item['options']) or \
                any(not isinstance(item.get(name, ''), str) for name in DECISION_TEXT):
            raise GraphError('needs_user_decision options, recommendation and context must be strings')
        seen.add(item['id'])
        normalized.append({'id': item['id'], 'question': item['question'], 'options': list(item['options'])}
                          | {name: item.get(name, '') for name in DECISION_TEXT})
    return normalized


def merge_decisions(holder: dict, packet_id: str, items: list[dict]) -> None:
    """Add a handoff's decisions to the round (reducer helper); answered ones keep their answer."""
    existing = holder.setdefault('user_decisions', [])
    for item in items:
        row = next((row for row in existing if row['id'] == item['id']), None)
        if row is not None and row['packet_id'] != packet_id:
            raise GraphError(f"decision id {item['id']} is already used by {row['packet_id']}; use a unique id")
        if row is None:
            existing.append(item | {'packet_id': packet_id, 'asked_utc': utc_now(), 'answer': None})
        elif row.get('answer') is None:
            row.update(item)


def open_decisions(program: dict) -> list[dict]:
    holder = program['rounds'][-1] if program['rounds'] and program['rounds'][-1]['round'] == program['round'] else {}
    return [row for row in holder.get('user_decisions') or [] if row.get('answer') is None]


def decide(root: Path, decision_id: str, answer: str, expected_sha256: str | None = None) -> dict:
    """Record the user's answer verbatim (source user, with the date)."""
    if not isinstance(answer, str) or not answer.strip():
        raise GraphError('program decide needs --answer with the user\'s exact words')

    def reducer(state: dict) -> dict:
        target = rounds.active(state)
        holder = rounds.current_round(target)
        row = next((row for row in holder.get('user_decisions') or [] if row['id'] == decision_id), None)
        if row is None:
            raise GraphError(f"no user decision {decision_id} in round {target['round']}")
        if row.get('answer') is not None:
            row.setdefault('previous_answers', []).append(row['answer'])
        now = utc_now()
        row['answer'] = {'text': answer, 'source': 'user', 'answered_utc': now, 'date': now[:10]}
        store.history(target, 'user_decision', round=target['round'], decision=decision_id)
        return state
    return store.update(root, reducer, expected_sha256)


def decision_gate(program: dict) -> dict:
    pending = open_decisions(program)
    return {'ok': not pending, 'open': [row['id'] for row in pending],
            'problem': ('ASK THE USER first: ' + ', '.join(row['id'] for row in pending)) if pending else None}


def decision_prompt(rows: list[dict]) -> str:
    return ' '.join(f"[{row['id']}] {row['question']} Options: {'; '.join(row['options']) or 'free answer'}."
                    + (f" Recommendation: {row['recommendation']}." if row.get('recommendation') else '')
                    + (f" Context: {row['context']}" if row.get('context') else '') for row in rows)


def handoff_save_as(program: dict, packet_id: str) -> str:
    return f'{packets.handoff_directory(program)}/{packets.packet_file(packet_id)}.handoff.json'
