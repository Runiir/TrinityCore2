"""Create the user-requested camera macro through the stock /m UI."""
import json
import time
from pathlib import Path
from . import runtime,camera_zoom,inputs,laya_ui
from .observe import observe
from .farm_actions import command_choice,click_choice,stationary

NAME='ArchaeologyView'
PRESET=3
ZOOM=20
BODY='/run MouselookStop();ResetView(3);SetView(3)\n/run CameraZoomOut(20)'


def use(folder,row):
    return click_choice(folder,row,('camera_macros',),
        'Click ArchaeologyView to recover a poor camera angle and restore a wide view')


def edit_choice(folder,row,field,value):
    folder.mkdir(parents=True,exist_ok=False)
    current=row['farm_ui']['macro'][field]
    choice,request,response=laya_ui.choose({'goal':'Enter the requested camera macro '+field,
        'field':current['label'],'text':value,'focused':current.get('focused')},
        'Type into the focused stock macro field or wait.',
        {'type':'Replace this macro field with the requested text','wait':'Wait without input'})
    result={'choice':choice,'request':request,'response':response,'executed':False}
    runtime.write(folder/'decision.json',result)
    if choice=='type':
        fresh=observe(folder/'precheck.png');stationary(row,fresh)
        ui=fresh['farm_ui'].get('macro') or {};entry=ui.get(field) or {}
        if not entry.get('focused') or entry!=current:
            raise RuntimeError('selected client action invalidated: focused macro field changed')
        if field=='body' and ui.get('selected_name')!=NAME:
            raise RuntimeError('selected client action invalidated: camera macro selection changed')
        result['input']=inputs.execute('World of Warcraft','edit_text',{
            'text':value,'frame_period_seconds':1/max(1,fresh['farm_ui'].get('frame_rate') or 30)})
        result['executed']=True
    runtime.write(folder/'decision.json',result);return result


def place_choice(folder,row):
    folder.mkdir(parents=True,exist_ok=False)
    slots=row['farm_ui'].get('empty_actionbars') or []
    options={f'slot_{i}':'Place ArchaeologyView in empty action slot '+str(s['slot'])
        for i,s in enumerate(slots) if s['enabled']}
    options['wait']='Wait without replacing any existing action'
    if len(options)==1:return {'executed':False,'reason':'no empty visible action slot'}
    choice,request,response=laya_ui.choose({'goal':'Put the camera recovery macro on an empty action-bar slot',
        'macro':NAME,'empty_slots':{key:label for key,label in options.items() if key!='wait'}},
        'Select an empty slot for the user-requested camera macro, or wait.',options)
    result={'choice':choice,'request':request,'response':response,'executed':False}
    if choice!='wait':
        destination=slots[int(choice.split('_')[1])]
        source=row['farm_ui']['macro'].get('selected_icon')
        fresh=observe(folder/'precheck.png');stationary(row,fresh)
        ui=fresh['farm_ui'].get('macro') or {}
        if (not source or ui.get('selected_icon')!=source or ui.get('selected_name')!=NAME
                or destination not in fresh['farm_ui'].get('empty_actionbars',[])):
            raise RuntimeError('selected client action invalidated: macro drag source or empty slot changed')
        point=lambda c:[round(c['x']*runtime.WIDTH),round(c['y']*runtime.HEIGHT)]
        result['input']=inputs.execute('World of Warcraft','drag',{'from':point(source),'to':point(destination),
            'frame_period_seconds':1/max(1,fresh['farm_ui'].get('frame_rate') or 30)})
        result.update(executed=True,slot=destination['slot'])
    runtime.write(folder/'decision.json',result);return result


def apply_request(folder,row):
    path=runtime.ROOT/'run/camera_macro_request.json'
    if not path.exists():return False
    request=json.loads(path.read_text());a,m=row['archaeology'],row['movement']
    if request.get('runtime')!=row.get('runtime'):return False
    ui=row['farm_ui'].get('macro') or {}
    if (not m['in_world'] or m['dead'] or m['in_combat'] or m.get('speed',0)>0
            or any(a.get(k) for k in ('casting','flying','falling'))):return False
    if ui.get('schema')!='stock_macro_ui_v2':return False
    if time.time()-request.get('last_attempt',0)<.5:
        time.sleep(.25)
        return bool(ui.get('visible'))
    request['last_attempt']=time.time()
    installed=ui.get('installed') or {}
    character_tab=installed.get('character',True) if installed.get('name')==NAME else True
    def click(kind):
        return click_choice(folder/('macro_'+kind),row,('macro','controls'),
            {'character':'Choose character-specific macros','general':'Choose general macros',
             'new':'Create a new camera recovery macro','select':'Select ArchaeologyView',
             'accept':'Confirm the new macro named ArchaeologyView','close':'Close and save the camera macro',
             'save':'Save the camera macro commands'}[kind],expected={'kind':kind},matching_only=True)
    try:
        bars=row['farm_ui'].get('camera_macros') or []
        if installed.get('name')==NAME and installed.get('body')==BODY and bars and not ui.get('visible'):
            request['macro_confirmed']=installed
            request['bar_confirmed']=bars
            selection=click_choice(folder/'camera_macro_reset',row,('camera_macros',),
                'Click ArchaeologyView to restore the camera angle and wider view')
            if selection['executed']:
                fresh=observe(folder/'camera_macro_feedback.png')
                request['zoom_feedback']=camera_zoom.restore(folder/'camera_macro_zoom',fresh,ZOOM)
                request['completed']=request['zoom_feedback']['confirmed']
        elif not ui.get('visible'):
            selection=command_choice(folder/'macro_open',row,'/m',
                'Create the camera recovery macro in the Macro window','Open the stock Macro window')
        elif ui.get('popup_visible'):
            field=ui.get('name') or {}
            if field.get('value')==NAME:selection=click('accept')
            elif not field.get('focused'):
                selection=click_choice(folder/'macro_name_focus',row,('macro','name'),
                    'Focus the new macro name field')
            else:selection=edit_choice(folder/'macro_name_text',row,'name',NAME)
        elif bool(ui.get('character_tab'))!=bool(character_tab):
            selection=click('character' if character_tab else 'general')
        elif installed.get('name')!=NAME:selection=click('new')
        elif ui.get('selected_name')!=NAME:selection=click('select')
        elif (ui.get('body') or {}).get('value')!=BODY:
            if not (ui.get('body') or {}).get('focused'):
                selection=click_choice(folder/'macro_body_focus',row,('macro','body'),
                    'Focus ArchaeologyView macro commands')
            else:selection=edit_choice(folder/'macro_body_text',row,'body',BODY)
        elif not bars and (ui.get('body') or {}).get('value')==BODY:
            selection=place_choice(folder/'macro_place',row)
        else:
            has_save=any(c.get('kind')=='save' and c['enabled'] for c in ui.get('controls') or [])
            selection=click('save' if has_save and installed.get('body')!=BODY else 'close')
        request['selection']=selection
    except RuntimeError as error:
        request['retry_reason']=str(error);selection={'executed':False}
    runtime.write(Path(request['receipt']),request)
    if request.get('completed'):path.unlink(missing_ok=True)
    else:runtime.write(path,request)
    # Do not type gameplay commands into a visible macro editor on a UI wait.
    return selection['executed'] or bool(ui.get('visible'))
