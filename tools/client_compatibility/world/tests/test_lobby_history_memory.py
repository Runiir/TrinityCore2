"""Latest owned lobby state survives a streaming read without old payload retention."""
from tools.client_compatibility.interaction_lobby_idle import session_history


class Cursor:
    def __init__(self,rows):self.rows=rows
    def poll(self):yield from self.rows


def auth(session,account=1):return {'event':'world_authenticated','session':session,'account_id':account}
def enum(session,direction='to_client'):
    return {'name':'SMSG_ENUM_CHARACTERS_RESULT','session':session,'direction':direction}
def closed(session):return {'event':'world_connection_closed','session':session}


def test_foreign_account_does_not_replace_owned_lobby():
    a=auth('owned');assert session_history(Cursor([a,enum('owned'),auth('foreign',2),closed('foreign')]),1)==(a,False,True)


def test_closed_owned_session_is_retained():
    a=auth('owned');assert session_history(Cursor([a,enum('owned'),closed('owned')]),1)==(a,True,True)


def test_new_owned_authentication_resets_prior_lobby_flags():
    b=auth('new');assert session_history(Cursor([auth('old'),enum('old'),closed('old'),b,enum('new')]),1)==(b,False,True)


def test_old_enum_or_wrong_direction_does_not_prove_new_selection():
    b=auth('new');assert session_history(Cursor([auth('old'),enum('old'),b,enum('new','from_client')]),1)==(b,False,False)


def test_missing_owned_authentication_has_no_lobby():
    assert session_history(Cursor([auth('foreign',2),enum('foreign')]),1)==(None,False,False)


def test_diagnostic_payloads_do_not_accumulate_with_history_length():
    counts={'live':0,'peak':0}
    class Record(dict):
        def __init__(self):
            super().__init__(event='diagnostic',session='owned')
            counts['live']+=1;counts['peak']=max(counts['peak'],counts['live'])
        def __del__(self):counts['live']-=1
    class Stream:
        def poll(self):
            yield auth('owned');yield enum('owned')
            for _ in range(2500):yield Record()
    assert session_history(Stream(),1)==(auth('owned'),False,True)
    assert counts['peak']<=2 and counts['live']==0
