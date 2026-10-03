"""Attribute choices using the persisted controller names in trial receipts."""


def choice_counts(episodes):
    totals={kind+'_choices_'+stage:0 for kind in ['code','model'] for stage in ['selected','executed']}
    for episode in episodes:
        controller=episode['controller']
        if controller in ['code','code_diagnostic_ordinary_inputs']:kind='code'
        elif controller in ['laya','laya_candidate_selection']:kind='model'
        else:raise ValueError('unknown persisted interaction controller: '+controller)
        for case in episode['cases']:
            if 'selected' not in case:continue
            totals[kind+'_choices_selected']+=1
            # A choice can be persisted before a failed input lease. Input
            # completion or a subsequent observation confirms submission.
            if 'input_transport' in case or 'after_frame' in case:
                totals[kind+'_choices_executed']+=1
    return totals
