# Magmaw canary 97 infrastructure handoff

- Source commit: `31322fb541e7f3125465a856905c7016d5723acd`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Binary SHA-256: `6e27dd39b3437e06153510748d44bad84f0c547418c13cfb8cf4f58a62815ca8`
- Report SHA-256: `e14f8ab5bd0b6e73a51324cb000a9e233c2b2ebfe7b26dbf601a61a2c8d2d4b5`
- Heartbeat stream SHA-256: `7699e1ef53407eb26bc49c713bae331da356d671cfd0f127da784602d3ee1153`
- Worldserver log SHA-256: `672ae2c23b258b1bcb11c1a2351a3679021171f24ba1370a91f0dc7db25ee068`

## Result

The matched patrol-safety replay cleared the Chainwielder and both Drudges. The recorded unsafe null-profile `combat_range` destination did not recur. One Affliction Warlock death during Drudges recovered through native release and instance runback, and the route advanced to Magmaw generation 4.

The run is not acceptance evidence. During the first Magmaw attempt, after 105 originated-combat seconds, the worldserver exited from signal 7 (`SIGBUS`, controller return code `-7`). The process had made 12,312,564 party damage, retained nine initially surviving members plus the recovered warlock, and had not reached a typed gameplay watchdog. No assertion, explicit fatal log, OOM, disk exhaustion, or kernel crash record was present. The terminal classification is `worldserver_nonzero_return`, separate from the verified patrol-safety gameplay result.

## Exact next action

Freshly provision and replay the same exact clean commit and binary once under the completion watchdog. Do not change gameplay code for this infrastructure-only noncompletion. If `SIGBUS` repeats at the same command or native event, close the replay and route the first reproducible crash edge to a bounded runtime/crash work unit. If it does not repeat, classify canary 97 as a transient infrastructure noncompletion and continue from the replay's first gameplay edge.
