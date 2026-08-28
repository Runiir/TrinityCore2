# Magmaw canary 99 `map::at` abort handoff

- Runtime source commit: `946f48e676d2db47469c96e72563e1baffea3ead`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Binary SHA-256: `6d10bd97d44626581b683862196c53943fc955f56b61d5a125b1aa965c0962e5`
- Gate-bearing build receipt SHA-256: `89d588cc48f2933ae8dd0db4bde292720e3db1a47ce348adc19a5b8691b06ec7`
- Report: `/tmp/trinity-magmaw-946f48e676-canary99.ADPeoJ/run/report.json`
- Report SHA-256: `40987f795f4bb0c868557cdd0234f5ba1c39b30ba83fa7674ddce252263ed190`
- Heartbeat stream SHA-256: `547d37e4013905d248911d9534f5d77053865bf1db969f790c2a3f4d7708ba71`
- Worldserver log SHA-256: `dde7a4e823028de1b9b96e4be9251090cdf54de845feac40695508847c3ed035`

## Closed result

Canary 99 cleared the Chainwielder and both Drudges in order with no bot deaths, then reached and engaged Magmaw. The prior dead-leader native-runback failure did not recur, but no bot died on trash, so the new dead-position witness remains pending a matched live recovery case.

During Magmaw, one fire mage died, native pincer interaction occurred, and the party produced `11,846,800` originated damage over `105` active seconds (`112,826.667` DPS) plus `1,910,473` healing (`18,194.981` HPS). Affliction produced `2,573,104` damage (`24,505.752` DPS); its primary pet contributed `740,040`, or `28.8%`.

The worldserver then terminated before the controller could collect the complete combat-log/calibration receipts. The worldserver log records:

```text
terminate called after throwing an instance of 'std::out_of_range'
  what():  map::at
Caught signal 6
```

The controller recorded return code `-11`, `worldserver_process_exit`, and `worldserver_nonzero_return`. No core dump or stack trace was retained. This is an infrastructure/runtime abort, not a trash-route failure or a qualifying Magmaw gameplay verdict.

## Bounded repair hypothesis

Find the exact uncaught `std::map::at` lookup exercised by the controller's status, diagnosis, trace, combat-log, or experiment-summary evidence path while Magmaw metrics are changing. The bot runtime contains only a few direct `map::at` calls, including calibration spell/event-count joins and selected-cohort access. Replace only the proven unsafe lookup with a total, typed outcome that preserves valid evidence and cannot terminate the worldserver.

Do not change combat behavior, class tuning, encounter mechanics, route geometry, watchdog thresholds, or suppress evidence collection. Add a focused counterexample for a missing map key or missing selected cohort, whichever the trace and call graph prove is the first broken edge.
