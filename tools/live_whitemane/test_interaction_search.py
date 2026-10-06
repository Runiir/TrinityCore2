from . import interaction_search, runtime


def row():
    return {'runtime':{'pid':7,'start_ticks':'20'},
        'archaeology':{'world':{'instance':1,'north':10,'west':20}},
        'movement':{'facing_radians':0},'farm_ui':{'camera_zoom':8},
        'visible_find':{'guid':'find-1'}}


def test_partial_search_resumes_only_for_the_same_view_and_owned_target(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    points=[(640,400),(640,420),(640,440)]
    r=row();search=interaction_search.resume(r,{'Find'},points)
    interaction_search.save(search,2)
    assert interaction_search.resume(r,{'Find'},points)['index']==2
    r['archaeology']['world']['north']+=3
    assert interaction_search.resume(r,{'Find'},points)['index']==0
    r=row();r['visible_find']['guid']='find-2'
    assert interaction_search.resume(r,{'Find'},points)['index']==0
    r=row();r['movement']['facing_radians']=.3
    assert interaction_search.resume(r,{'Find'},points)['index']==0
    assert interaction_search.resume(row(),{'Find'},list(reversed(points)))['index']==0


def test_completed_search_clears_progress_and_storage_is_bounded(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    points=[(640,400),(640,420)]
    for i in range(12):
        interaction_search.save(interaction_search.resume(row(),{str(i)},points),1)
    search=interaction_search.resume(row(),{'11'},points)
    assert len(search['saved'])==8 and search['index']==1
    interaction_search.save(search,0,completed=True)
    assert interaction_search.resume(row(),{'11'},points)['index']==0


def test_zoom_roundoff_preserves_search_progress_but_a_changed_view_restarts(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    points=[(640,400),(640,420),(640,440)]
    before=row();before['farm_ui']['camera_zoom']=5.5499997138977
    interaction_search.save(interaction_search.resume(before,{'Portal to Orgrimmar'},points),2)
    after=row();after['farm_ui']['camera_zoom']=5.5500001907349
    assert interaction_search.resume(after,{'Portal to Orgrimmar'},points)['index']==2
    after['farm_ui']['camera_zoom']=6
    assert interaction_search.resume(after,{'Portal to Orgrimmar'},points)['index']==0
