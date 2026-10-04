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
