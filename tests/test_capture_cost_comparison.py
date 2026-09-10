from tools.raid_program.compare_capture_cost import compare


def test_shorter_run_does_not_masquerade_as_lower_capture_rate():
    def report(seconds, size):
        return {"log_bytes": size,
                "resource_sampling": {"summary": {"elapsed_seconds": seconds}}}
    result = compare(report(200, 200000), report(100, 100000))
    assert result["change_percent"]["native_log_bytes"] == -50
    assert result["change_percent"]["native_log_bytes_per_second"] == 0
    assert result["candidate"]["trace_parse_seconds"] is None
    assert result["change_percent"]["mean_worldserver_cpu_percent_one_core"] is None


def test_missing_sampling_duration_is_not_zero_overhead():
    result = compare({}, {"log_bytes": 1000})
    assert result["candidate"]["native_log_bytes_per_second"] is None
    assert result["change_percent"]["native_log_bytes_per_second"] is None
