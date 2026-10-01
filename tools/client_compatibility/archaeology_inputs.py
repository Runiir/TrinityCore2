"""Physical inputs and tooltip-guided find localization for the owned client."""
import contextlib
import io
import math
import time
from PIL import Image
from tools.second_client import ctl
from . import lab_runtime as lab
from .observation import telemetry,travel

FIND_NAMES=['Night Elf Archaeology Find','Nerubian Archaeology Find','Dwarf Archaeology Find',
    'Fossil Archaeology Find','Troll Archaeology Find','Orc Archaeology Find','Draenei Archaeology Find',
    'Vrykul Archaeology Find',"Tol'vir Archaeology Find"]
FIND_CHECKSUMS={telemetry.checksum(name.encode()) for name in FIND_NAMES}


def screenshot(path):
    ctl._launcher_env=lab.client_environment
    with contextlib.redirect_stdout(io.StringIO()):ctl.shot(str(path))
    with Image.open(path) as image:
        movement=telemetry.decode_image(image,x=15,y=15,cell_size=3.75)
        extra=travel.decode_image(image)
    return movement,extra


def locate_find(inputs,path):
    # Search the ordinary 3D view with cursor hover, then verify the game's
    # tooltip against known find names. No teacher pixel or private coordinates.
    preferred=[(655,331),(640,360),(655,400),(620,400)]
    grid=[(x,y) for x in range(500,781,20) for y in range(240,541,20)]
    grid.sort(key=lambda p:(p[0]-655)**2+(p[1]-370)**2)
    for x,y in [*preferred,*grid]:
        inputs.move(x,y);time.sleep(.15)
        _,extra=screenshot(path)
        if extra['tooltip_name_checksum'] in FIND_CHECKSUMS:return (x,y)
    raise RuntimeError('no archaeology find tooltip in the bounded screen search')


def execute(action,tcp,path):
    ctl._launcher_env=lab.client_environment;inputs=ctl.Input();hold=None;pixel=None
    if action=='survey':inputs.key('2')
    elif action.startswith('turn_'):
        if not tcp['tool']:raise ValueError('turn without a survey observation')
        hold=min(.55,max(.025,abs(tcp['tool']['turn_error_radians'])/math.pi))
        inputs.key('a' if action=='turn_left' else 'd',hold=hold)
    elif action.startswith('forward_'):
        if not tcp['tool']:raise ValueError('walk without a survey observation')
        short,long={'red':(2,6),'yellow':(1,3),'green':(.5,1)}[tcp['tool']['color']]
        hold=short if action=='forward_short' else long;inputs.key('w',hold=hold)
    elif action=='loot':
        if not tcp['finds']:raise ValueError('loot without a visible owned find')
        pixel=locate_find(inputs,path);inputs.click(*pixel,button=3)
    elif action!='observe':raise ValueError('unknown physical action')
    time.sleep(2.5 if action in ['survey','loot'] else .5)
    return {'hold_seconds':hold,'mouse_pixel':pixel,'pixel_source':'ordinary_game_tooltip_hover' if pixel else None}
