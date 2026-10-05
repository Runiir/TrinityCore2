"""Select one read-only settings page, then restore the passive observer cycle."""
from .interaction_operations import command
from .interaction_settings_booleans import detail


def snapshot(t,label):
    # A brief hidden settings page can be missed by screenshot sampling. This
    # selects only the observer's fixed read-only page, never a game setter.
    t.receipt.setdefault('quest_settings_diagnostics',[]).append({'label':label,
        'commands':['/tcui settings','/tcui'],'read_only':True,'qualified':False})
    t.persist()
    command(t,'/tcui settings')
    try:return detail(t,label)
    finally:
        command(t,'/tcui')
        t.observe(label+'_passive_cycle_restored')
