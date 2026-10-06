"""Game screenshots must receive the same archive attribution checks as PNGs."""
import pytest
import copy,json
from tools.client_compatibility.review_interaction_archive import frame_members


@pytest.mark.parametrize('suffix',['png','jpg','jpeg'])
def test_game_image_is_attributed_and_digest_checked(suffix):
    member='evidence/run/actor/screenshot.'+suffix
    manifest={member:{'sha256':'a'*64}}
    frame={'file':'screenshot.'+suffix,'sha256':'a'*64}
    assert frame_members(frame,'evidence/run/actor','evidence/run',manifest)=={member:'a'*64}
    with pytest.raises(ValueError,match='digest differs'):
        frame_members({**frame,'sha256':'b'*64},'evidence/run/actor','evidence/run',manifest)


def test_sibling_lobby_frame_resolves_its_exact_member_and_digest():
    member='evidence/run/realm/next_screen.png'
    manifest={member:{'sha256':'a'*64},'evidence/run/other/next_screen.png':{'sha256':'a'*64}}
    frame={'file':'../realm/next_screen.png','sha256':'a'*64}
    assert frame_members(frame,'evidence/run/before','evidence/run',manifest)=={member:'a'*64}
    with pytest.raises(ValueError,match='digest differs'):
        frame_members({**frame,'sha256':'b'*64},'evidence/run/before','evidence/run',manifest)


@pytest.mark.parametrize('name',['../missing/next_screen.png','../../outside/next_screen.png',
    '../../../run/realm/next_screen.png','../realm/next_screen.png'])
def test_sibling_frame_cannot_escape_or_borrow_a_basename(name):
    manifest={'evidence/run/realm/next_screen.png':{'sha256':'a'*64}}
    frame={'file':name}
    if name!='../realm/next_screen.png':frame['sha256']='a'*64
    with pytest.raises(ValueError):frame_members(frame,'evidence/run/before','evidence/run',manifest)


@pytest.mark.parametrize('source_hash',['c'*64,'d'*64])
def test_copied_lobby_frame_uses_its_hash_bound_source_review(monkeypatch,tmp_path,source_hash):
    from tools.client_compatibility import review_interaction_archive as review
    monkeypatch.setattr(review.lab,'ROOT',tmp_path)
    origin='evidence/run/selection/next_screen.png';later='evidence/run/enter/next_screen.png'
    source='evidence/run/selection/review.json'
    manifest={origin:{'sha256':'a'*64},later:{'sha256':'b'*64},source:{'sha256':'c'*64}}
    copied={'path':str(tmp_path/source),'sha256':source_hash,
        'frame':{'file':'next_screen.png','sha256':'a'*64}}
    if source_hash=='c'*64:
        assert frame_members(copied,'evidence/run/enter','evidence/run',manifest)=={origin:'a'*64}
    else:
        with pytest.raises(ValueError,match='referenced frame review is absent or changed'):
            frame_members(copied,'evidence/run/enter','evidence/run',manifest)


def historical_fixture(monkeypatch,tmp_path):
    from tools.client_compatibility import review_interaction_archive as review
    monkeypatch.setattr(review.lab,'ROOT',tmp_path);monkeypatch.setattr(review.lab,'REPO',tmp_path/'repo')
    source=tmp_path/'evidence/prior/spell/episode.json';source.parent.mkdir(parents=True)
    baseline={'auras':{},'frame':{'file':'baseline.png','sha256':'a'*64}}
    source.write_text(json.dumps({'completed':False,'finished_at':1,'failure':'cleanup failed','spell_baseline':baseline}))
    pointer='artifacts/client_harness/442_prior.tar.gz.dvc';target=tmp_path/'repo'/pointer
    target.parent.mkdir(parents=True);target.write_text('outs: []\n')
    path=tmp_path/'evidence/prior_review.json'
    report={'schema':'client442_qualification_archive_review_v1','cloud_verified':True,'pointer':pointer,
        'archive_sha256':'b'*64,'receipts':[{'member':'evidence/prior/spell/episode.json','sha256':review.lab.sha256(source),'verified':True}],
        'frames':[{'member':'evidence/prior/spell/baseline.png','sha256':'a'*64,'verified':True}]}
    path.write_text(json.dumps(report));value={'original_failure':{'path':str(source),'sha256':review.lab.sha256(source)},
        'spell_baseline':copy.deepcopy(baseline),'bridge_recovery_sources':[{'path':str(path),'sha256':review.lab.sha256(path)}]}
    return review,value,path,report,source


def test_historical_failure_frame_retains_its_prior_archive_and_does_not_mutate_receipt(monkeypatch,tmp_path):
    review,value,path,_,_=historical_fixture(monkeypatch,tmp_path);before=copy.deepcopy(value)
    local,frames=review.historical_baseline(value,[path]);assert value==before
    assert 'frame' not in local['spell_baseline'] and frames[0]['member']=='evidence/prior/spell/baseline.png'
    assert frames[0]['pointer']=='artifacts/client_harness/442_prior.tar.gz.dvc' and frames[0]['verified']


@pytest.mark.parametrize('fault',['source_hash','changed_baseline','escaping_frame','unbound_review','changed_review',
    'not_cloud_verified','wrong_source_member','wrong_frame_digest','unverified_frame','duplicate_review','open_failure'])
def test_historical_frame_cannot_borrow_an_unbound_or_changed_external_proof(monkeypatch,tmp_path,fault):
    review,value,path,report,source=historical_fixture(monkeypatch,tmp_path);paths=[path]
    if fault=='source_hash':value['original_failure']['sha256']='c'*64
    elif fault=='changed_baseline':value['spell_baseline']['auras']={'0':{}}
    elif fault=='escaping_frame':
        value['spell_baseline']['frame']['file']='../outside.png'
        d=json.loads(source.read_text());d['spell_baseline']=value['spell_baseline'];source.write_text(json.dumps(d))
        value['original_failure']['sha256']=review.lab.sha256(source)
    elif fault=='unbound_review':value['bridge_recovery_sources']=[]
    elif fault=='changed_review':path.write_text(path.read_text()+' ')
    elif fault=='duplicate_review':paths.append(path)
    elif fault=='open_failure':
        d=json.loads(source.read_text());d['finished_at']=None;source.write_text(json.dumps(d))
        value['original_failure']['sha256']=review.lab.sha256(source)
    else:
        if fault=='not_cloud_verified':report['cloud_verified']=False
        elif fault=='wrong_source_member':report['receipts'][0]['member']='evidence/foreign/spell/episode.json'
        elif fault=='wrong_frame_digest':report['frames'][0]['sha256']='c'*64
        else:report['frames'][0]['verified']=False
        path.write_text(json.dumps(report));value['bridge_recovery_sources'][0]['sha256']=review.lab.sha256(path)
    with pytest.raises(ValueError):review.historical_baseline(value,paths)
