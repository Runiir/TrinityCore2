"""Temporary, narrow RBAC permissions for code fixture preparation in the private lab."""
from contextlib import contextmanager
import re,time
from . import lab_runtime as lab


def permission_rows(account,permission):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT granted,realmId FROM client442_auth.rbac_account_permissions WHERE accountId=%s AND permissionId=%s',(account,permission))
        return q.fetchall()


@contextmanager
def item_fixture_permission(trial):
    # RBAC_PERM_COMMAND_ADDITEM=488 in the current native RBAC.h. No GM security,
    # combat exemption, instant logout or other administrative role is granted.
    account=trial.fixture['account_id'];permission=488
    baseline=permission_rows(account,permission)
    if baseline:raise RuntimeError('item fixture requires no pre-existing direct add-item permission')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT username FROM client442_auth.account WHERE id=%s',(account,));row=q.fetchone()
    if not row or not re.fullmatch('[A-Z0-9_]+',row[0]):raise RuntimeError('invalid owned fixture account name')
    name=row[0];trial.receipt['fixture_permission']={'source':'code_fixture','account_id':account,'permission':permission,'realm':-1,'baseline':baseline,'security_level_changed':False};trial.persist()
    try:
        lab.server_command(f'rbac account grant {name} {permission} -1');lab.server_command('reload rbac')
        deadline=time.monotonic()+5
        while permission_rows(account,permission)!=((1,-1),):
            if time.monotonic()>deadline:raise RuntimeError('temporary fixture permission was not granted')
            time.sleep(.1)
        yield
    finally:
        if permission_rows(account,permission):
            lab.server_command(f'rbac account revoke {name} {permission} -1');lab.server_command('reload rbac')
        deadline=time.monotonic()+5
        while permission_rows(account,permission)!=baseline:
            if time.monotonic()>deadline:raise RuntimeError('temporary fixture permission was not restored')
            time.sleep(.1)
        trial.receipt['fixture_permission']['restored']=True;trial.persist()
