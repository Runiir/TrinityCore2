"""Shortest straight segments above a sampled flight surface envelope."""
import math


def envelope(columns,start,margin,*,local_floor=False):
    hull=[]
    for column in columns:
        if local_floor:
            heights=[z for z in (column.get('terrain_height'),column.get('support_height')) if z is not None]
            if not heights:return None
            floor=max(heights)
        else:floor=column['highest_surface']
        distance=math.hypot(column['north']-start[0],column['west']-start[1])
        point={'north':column['north'],'west':column['west'],
            'height_yards':max(start[2],floor+margin) if distance<.01 else floor+margin,
            'along_yards':distance}
        if hull and distance-hull[-1]['along_yards']<.001:continue
        while len(hull)>=2:
            a,b=hull[-2:];cross=(b['along_yards']-a['along_yards'])*(point['height_yards']-a['height_yards'])-(
                b['height_yards']-a['height_yards'])*(point['along_yards']-a['along_yards'])
            if cross<0:break
            hull.pop()
        hull.append(point)
    return hull


def checked(path,start,map_id,check_segment):
    if not path:return False
    xyz=lambda p:[p['north'],p['west'],p['height_yards']]
    if not check_segment(map_id,start,xyz(path[0])):return False
    for a,b in zip(path,path[1:]):
        distance=math.dist(xyz(a),xyz(b))
        count=max(1,math.ceil(distance/40))
        previous=xyz(a)
        for index in range(1,count+1):
            point=[x+(y-x)*index/count for x,y in zip(xyz(a),xyz(b))]
            if not check_segment(map_id,previous,point):return False
            previous=point
    return True


def aim(path,world,height,speed,age):
    first,last=path[0],path[-1];length=last['along_yards']
    if length<.01:return {'pitch_radians':0,'height_yards':height,'lookahead_yards':0}
    dn=(last['north']-first['north'])/length;dw=(last['west']-first['west'])/length
    along=(world['north']-first['north'])*dn+(world['west']-first['west'])*dw
    lookahead=max(5,speed*max(.3,age+.2))
    target_along=min(length,max(0,along)+lookahead)
    a,b=next(((a,b) for a,b in zip(path,path[1:]) if b['along_yards']>=target_along),(first,last))
    fraction=(target_along-a['along_yards'])/max(.001,b['along_yards']-a['along_yards'])
    z=a['height_yards']+(b['height_yards']-a['height_yards'])*fraction
    north=first['north']+dn*target_along;west=first['west']+dw*target_along
    horizontal=math.hypot(north-world['north'],west-world['west'])
    return {'pitch_radians':math.atan2(z-height,max(.01,horizontal)),
        'height_yards':z,'lookahead_yards':horizontal,'along_yards':along}
