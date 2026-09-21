"""Enforce the native module limit against staged blobs, not unstaged files."""
from pathlib import Path
import argparse
import json
import subprocess

NATIVE_SUFFIXES = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx', '.inl'}
LIMIT = 1000  # AGENTS.md says below 1,000, so 1,000 itself fails.


def staged_violations(root: Path) -> list[dict]:
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args])
    paths = git('diff', '--cached', '--name-only', '--diff-filter=ACMRT',
                '--no-renames', '-z').decode().split('\0')
    violations = []
    for name in paths:
        if not name or Path(name).suffix.lower() not in NATIVE_SUFFIXES:
            continue
        mode = git('ls-files', '--stage', '-z', '--', name).split(b' ', 1)[0]
        if mode not in {b'100644', b'100755'}:
            violations.append({'path': name, 'reason': 'native module must be a regular staged file'})
            continue
        data = git('show', ':' + name)
        count = len(data.splitlines())
        if count >= LIMIT:
            violations.append({'path': name, 'lines': count, 'maximum_allowed': LIMIT - 1})
    return violations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    violations = staged_violations(args.root)
    if violations:
        print(json.dumps({'module_size': 'blocked', 'violations': violations}))
        print('Split changed C/C++ sources and headers by concern; each must be below 1,000 lines.')
    return int(bool(violations))


if __name__ == '__main__':
    raise SystemExit(main())
