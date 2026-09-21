import subprocess

import pytest

from tools.raid_program.module_size import main, staged_violations


@pytest.fixture
def repo(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty',
                    '-qm', 'base'], check=True)
    return tmp_path


def stage(repo, name, count):
    (repo/name).write_text('// line\n' * count)
    subprocess.run(['git', '-C', str(repo), 'add', '--', name], check=True)


@pytest.mark.parametrize('name', ['unit.cpp', 'unit.h', 'unit.c', 'unit.hpp', 'space name.cxx'])
def test_exact_boundary(repo, name):
    stage(repo, name, 999)
    assert staged_violations(repo) == []
    stage(repo, name, 1000)
    assert staged_violations(repo) == [{'path': name, 'lines': 1000, 'maximum_allowed': 999}]
    assert main(['--root', str(repo)]) == 1


def test_uses_index_not_worktree(repo):
    stage(repo, 'unit.cpp', 1000)
    (repo/'unit.cpp').write_text('// small unstaged version\n')
    assert staged_violations(repo)[0]['lines'] == 1000
    stage(repo, 'unit.cpp', 999)
    (repo/'unit.cpp').write_text('// large unstaged version\n' * 1001)
    assert staged_violations(repo) == []


def test_unmodified_legacy_and_deleted_files_do_not_block(repo):
    stage(repo, 'legacy.cpp', 1200)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test',
                    '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'legacy'], check=True)
    stage(repo, 'notes.md', 2000)
    assert staged_violations(repo) == []
    subprocess.run(['git', '-C', str(repo), 'rm', '-q', 'legacy.cpp'], check=True)
    assert staged_violations(repo) == []


def test_unterminated_last_line_counts(repo):
    stage(repo, 'unit.cpp', 999)
    with (repo/'unit.cpp').open('a') as stream:
        stream.write('// last line')
    subprocess.run(['git', '-C', str(repo), 'add', 'unit.cpp'], check=True)
    assert staged_violations(repo)[0]['lines'] == 1000


def test_native_symlink_cannot_hide_oversized_target(repo):
    (repo/'payload').write_text('// line\n'*1001)
    (repo/'unit.cpp').symlink_to('payload')
    subprocess.run(['git', '-C', str(repo), 'add', 'unit.cpp'], check=True)
    assert staged_violations(repo) == [{'path': 'unit.cpp',
        'reason': 'native module must be a regular staged file'}]


def test_native_submodule_cannot_bypass_staged_file_guard(repo):
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    subprocess.run(['git', '-C', str(repo), 'update-index', '--add', '--cacheinfo',
                    '160000', head, 'unit.cpp'], check=True)
    assert staged_violations(repo)[0]['reason'] == 'native module must be a regular staged file'
