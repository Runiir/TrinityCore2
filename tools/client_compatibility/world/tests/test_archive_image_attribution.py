"""Game screenshots must receive the same archive attribution checks as PNGs."""
import pytest
from tools.client_compatibility.review_interaction_archive import frame_members


@pytest.mark.parametrize('suffix',['png','jpg','jpeg'])
def test_game_image_is_attributed_and_digest_checked(suffix):
    member='evidence/run/actor/screenshot.'+suffix
    manifest={member:{'sha256':'a'*64}}
    frame={'file':'screenshot.'+suffix,'sha256':'a'*64}
    assert frame_members(frame,'evidence/run/actor','evidence/run',manifest)=={member:'a'*64}
    with pytest.raises(ValueError,match='digest differs'):
        frame_members({**frame,'sha256':'b'*64},'evidence/run/actor','evidence/run',manifest)


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
