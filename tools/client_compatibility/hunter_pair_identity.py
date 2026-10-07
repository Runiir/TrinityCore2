"""Pure saved/public identity checks for the frozen owned Hunter pair."""
import time


def identities(before,after,slots=None,active=None,summoned=None):
    b={r['id']:r for r in before};a={r['id']:r for r in after}
    if len(before)!=2 or len(after)!=2 or set(b)!={4,6} or set(a)!={4,6}:return False
    for number in b:
        old,new=b[number],a[number]
        if set(old)!=set(new):return False
        if old['owner']!=6 or new['owner']!=6:return False
        if not 0<old['savetime']<=new['savetime']<=time.time():return False
        expected=dict(old);expected['savetime']=new['savetime']
        if slots is not None:expected['slot']=slots[number]
        if active is not None:expected['active']=active[number]
        if summoned==number:
            if old['CreatedBySpell'] not in (883,13481):return False
            expected['CreatedBySpell']=883
        if expected!=new:return False
    return True


def public_rows(probe):
    return sorted([{k:r.get(k) for k in ('slot','name','level','display_id')} for r in probe.get('pets',[])],key=lambda r:r['slot'])


def expected_rows(retained):
    return sorted([{'slot':r['slot']+1,'name':r['name'],'level':r['level'],'display_id':r['modelid']}
        for r in retained],key=lambda r:r['slot'])
