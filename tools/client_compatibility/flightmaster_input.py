"""Locate a nearby, faced flight master through a fresh ordinary tooltip."""
import time


def hover_points():
    # At close interaction range, a faced NPC can be above the old search's
    # y=220 limit. Cover the central vertical strip before a wider scene scan.
    central=[(640+dx,y) for dx in [0,-16,16,-32,32,-48,48]
             for y in range(160,513,16)]
    wide=[(x,y) for x in range(384,897,32) for y in range(160,577,32)]
    wide.sort(key=lambda p:(p[0]-640)**2+(p[1]-280)**2)
    return list(dict.fromkeys([*central,*wide]))


def locate(inputs,path,expected):
    from PIL import Image
    from .archaeology_inputs import screenshot
    deadline=time.monotonic()+45
    for x,y in hover_points():
        if time.monotonic()>deadline:break
        inputs.move(x,y);time.sleep(.2)
        _,hover=screenshot(path)
        if hover['tooltip_name_checksum']!=expected:continue
        # A tooltip persisting after leaving an NPC is not a localization.
        inputs.move(400,100)
        for _ in range(6):
            time.sleep(.25);_,cleared=screenshot(path)
            if cleared['tooltip_name_checksum']==0:break
        if cleared['tooltip_name_checksum']!=0:continue
        inputs.move(x,y);time.sleep(.3)
        _,confirmed=screenshot(path)
        if confirmed['tooltip_name_checksum']!=expected:continue
        with Image.open(path) as image:image.save(path.parent/'localized_flightmaster.webp',lossless=True)
        return [x,y]
    raise RuntimeError('no fresh matching flight-master tooltip in bounded mouse search')
