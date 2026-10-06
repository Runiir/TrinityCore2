"""A read-only retry must never replace the failed receipt or borrow another source."""
import hashlib
import pytest
from tools.client_compatibility.interaction_parked_bridge import bound_restoration


@pytest.mark.parametrize('name',['scout_parked_after','scout_parked_after2'])
def test_deployment_resolves_only_its_exact_successful_restoration(tmp_path,name):
    p=tmp_path/name/'episode.json';p.parent.mkdir();p.write_text('{}\n')
    attempt={'episode':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'completed':True,'failure':None}
    report={'parked_reconnect_attempt':{'scout':attempt}}
    assert bound_restoration(tmp_path,report)==p


@pytest.mark.parametrize('change',['failed','error','hash','missing','outside','unbounded','wrong_filename'])
def test_deployment_rejects_failed_changed_foreign_or_unbounded_receipt(tmp_path,change):
    directory=tmp_path/'deploy';directory.mkdir()
    p=directory/'scout_parked_after2/episode.json';p.parent.mkdir();p.write_text('{}\n')
    attempt={'episode':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'completed':True,'failure':None}
    if change=='failed':attempt['completed']=False
    elif change=='error':attempt['failure']='failed review'
    elif change=='hash':attempt['sha256']='0'*64
    elif change=='missing':p.unlink()
    else:
        target={'outside':tmp_path/'foreign/scout_parked_after2/episode.json',
            'unbounded':directory/'scout_parked_after3/episode.json',
            'wrong_filename':p.parent/'other.json'}[change]
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());attempt['episode']=str(target)
    with pytest.raises(RuntimeError):bound_restoration(directory,{'parked_reconnect_attempt':{'scout':attempt}})
