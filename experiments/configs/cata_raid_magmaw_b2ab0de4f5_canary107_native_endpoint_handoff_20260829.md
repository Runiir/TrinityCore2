# Magmaw Canary107 native endpoint handoff

## Identity

- Source commit: `b2ab0de4f555db3f12d8fe6da1c96a2b36abfd58`
- Worldserver SHA-256: `bcfa366deede77747c6b5598c2b3d862d6fd866b6cd37f127a021a15dcc06f1e`
- Scenario: `blackwing_descent_10n_magmaw_diagnostic`
- Completion policy: completion watchdog, 5-second heartbeat, 300-second semantic no-progress window, no fixed success timer
- Terminal result: `semantic_progress_plateau_watchdog` after 605 seconds; `timed_out=false`

## Progress and first broken edge

The current-standard route cleared entrance regroup, Chainwielder, and both Drudges. It recorded three trash kills and two DPS deaths during Drudges; all ten roster members were alive in the final diagnosis. Magmaw was never engaged.

The first run-blocking edge was formation staging at route generation 4. Fire mage `30006` and hunter `30009` repeatedly received complete, floor-valid native paths whose X/Y endpoints exactly matched the requested point. MMAP normalized only Z:

| Bot | Endpoint 3D delta | Horizontal delta | Vertical delta | Result |
| --- | ---: | ---: | ---: | --- |
| `30006` | 0.882904 | 0 | 0.882904 | `route_destination_endpoint_mismatch` |
| `30009` | 0.811676 | 0 | 0.811676 | `route_destination_endpoint_mismatch` |

The shared endpoint proof used a 0.5-yard 3D tolerance, so valid walkable-floor normalization was misclassified as a different destination. The action trace also labeled formation suppression as `prepull_health_recovery`, hiding the actual cause. This is a distinct child signature under the already architecture-stopped same-level native-path proof family; it does not reset prior recurrence history.

## Prior repair result

The Canary106 intermediate floor-observation repair was exercised through all trash nodes: 25 complete matched native proofs were accepted, with no `SampleFloorGap`, `SampleFloorUnavailable`, or `same_level_movement_path_floor_false_negative` marker. It is not closed because the required two full-route clears have not occurred.

## Combat signal

| Node | Party DPS | Party HPS |
| --- | ---: | ---: |
| Chainwielder | 101,801 | 3,361 |
| Drudges | 105,668 | 31,141 |
| Magmaw prepull | 0 | 85,351 |

No future-pack contamination, forbidden assistance, death loop, or fixed timeout occurred.

## Artifact hashes

- `report.json`: `7f89e54443e5b10c7fa5b9af56890bdc903dd4e06686734f35c74fcbea0a12a6`
- `latest.json`: `e5796bfa3b6d9f09f1d92bafda6d79a075a7334e8ba72fb60852165e2a06b5ed`
- `heartbeat_events.jsonl`: `ac6587bff5bb645611f63a3c0561074fa651f50540990956601c530704417c2a`
- `combat_analysis.json`: `8098ddc597d6c31aa416e141b58609f421d50be18561d8c8f1ffeb5bf9b5b583`
- `combat_log.json`: `897e40c0d1811012ed8955a5737f920de5e49e9ee96c5eef4b8f62ff49397c15`
- `worldserver_output.log`: `26ca11149276f6b1755b67fb423195ced44d3c188a1d6e1f6dcd020bd56fc6e9`

## Retained regression contract

Admit a complete normal native path only when its horizontal endpoint is within 0.5 yards, its vertical endpoint delta is within the existing 1.5-yard native point-floor tolerance, and its endpoint floor is valid. Keep incomplete, shortcut, off-mesh, cross-level, and invalid-floor paths rejected. Emit horizontal and vertical deltas separately. Formation staging, health recovery, and pull-owner waiting must have distinct trace actions.

Closure still requires two consecutive full current-standard Magmaw route clears with this signature and the earlier floor-observation signature absent.
