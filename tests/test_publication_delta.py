from pathlib import Path
import subprocess

import pytest

from tools.raid_program.development_graph import GraphError, source_binding
from tools.raid_program.publication_delta import publication_paths


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def commit(root):
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
    return git(root, 'rev-parse', 'HEAD')


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, 'init', '-q')
    (tmp_path/'code.cpp').write_text('source')
    folder=tmp_path/'artifacts/cata_raid_program'
    folder.mkdir(parents=True)
    (folder/'.gitignore').write_text('/older.tar.gz\n')
    base=commit(tmp_path)
    return tmp_path, folder, base


def add_pointer(folder, target='run.tar.gz'):
    path=folder/'run.tar.gz.dvc'
    path.write_text(f'outs:\n- md5: 123abc\n  size: 42\n  path: {target}\n')
    return path


@pytest.mark.parametrize('change', ['native', 'old_pointer', 'wildcard', 'traversal', 'symlink', 'executable', 'selected_input'])
def test_publication_cannot_hide_source_or_reference_changes(repo, change):
    root, folder, base=repo
    pointer=add_pointer(folder)
    if change == 'old_pointer':
        base=commit(root)
        pointer.write_text(pointer.read_text().replace('123abc','456def'))
    elif change == 'native': (root/'unowned.cpp').write_text('changed')
    elif change == 'wildcard': (folder/'.gitignore').write_text('/older.tar.gz\n*\n')
    elif change == 'traversal': add_pointer(folder, '../../runtime')
    elif change == 'symlink':
        pointer.unlink(); pointer.symlink_to(root/'code.cpp')
    elif change == 'executable': pointer.chmod(0o755)
    head=commit(root)
    assignment={'base_commit':base,'owned_files':['code.cpp']}
    if change == 'selected_input':
        assignment['validation_identity']={'reference':{'path':pointer.relative_to(root).as_posix()}}
    with pytest.raises(GraphError, match='source delta'):
        source_binding(root, assignment, base)


def test_exact_added_output_is_metadata_but_existing_ignore_rules_are_preserved(repo):
    root, folder, base=repo
    pointer=add_pointer(folder)
    (folder/'.gitignore').write_text('/older.tar.gz\n/run.tar.gz\n')
    head=commit(root)
    assert publication_paths(root,base,head) == {str(pointer.relative_to(root)),str((folder/'.gitignore').relative_to(root))}
    assert source_binding(root, {'base_commit':base,'owned_files':['code.cpp']},base) == head


@pytest.mark.parametrize('committed', [False, True])
@pytest.mark.parametrize('owned', [False, True])
@pytest.mark.parametrize('after_tests', [False, True])
def test_selected_artifact_json_is_protected_even_when_nested_or_owned(repo, committed, owned, after_tests):
    root, folder, _=repo
    path=folder/'runtime.json'
    path.write_text('{"input":1}')
    base=commit(root)
    name=path.relative_to(root).as_posix()
    assignment={'base_commit':base, 'owned_files':['code.cpp']+([name] if owned else []),
                'validation_identity':{'dependencies':[{'path':name}]}}
    path.write_text('{"input":2}')
    if committed: commit(root)
    with pytest.raises(GraphError, match='source'):
        source_binding(root, assignment, base if after_tests else None)
