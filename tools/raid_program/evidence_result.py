"""Small outcome/gate projection. Never promotes a repair or reconstructs missing data."""
from tools.raid_program.evidence_inputs import select_path


def mapping(value, name):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('result_field_requires_object: ' + name)
    return value


def gate(value, status_key='passed', reasons_key='failure_reasons'):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('result gate must be an object')
    checks = value.get('checks')
    if checks is not None and not isinstance(checks, dict):
        raise ValueError('result gate checks must be an object')
    return {status_key: value.get(status_key), reasons_key: value.get(reasons_key),
            'failed_checks': [k for k, v in checks.items() if v is False] if checks is not None else None,
            'unknown_checks': [k for k, v in checks.items() if v is None] if checks is not None else None}


def result_view(document, metric_paths=(), section='outcome'):
    if not isinstance(document, dict) or not any(k in document for k in (
            'completion_reason', 'role_calibration_evaluation', 'combat_calibration', 'native_gameplay_outcome')):
        raise ValueError('result requires a native validation/calibration report; use compare for a normalized timeline')
    record = mapping(document.get('role_calibration_record'), 'role_calibration_record')
    calibration = mapping(document.get('combat_calibration'), 'combat_calibration')
    native = mapping(document.get('native_gameplay_outcome'), 'native_gameplay_outcome')
    metrics = mapping(record.get('metrics'), 'role_calibration_record/metrics')
    reference = record.get('reference_condition_compatibility')
    mapping(reference, 'role_calibration_record/reference_condition_compatibility')
    window = mapping(record.get('window'), 'role_calibration_record/window')
    controller = mapping(document.get('status'), 'status')
    if section == 'reference':
        return {'schema': 'evidence_reference_result_v1',
                'reference_gate': gate(reference, 'conditions_compatible', 'reasons')}
    selected = {}
    for path in metric_paths:
        value = select_path(document, path, 0, 1)['value']
        if isinstance(value, (dict, list)):
            raise ValueError('result_metric_requires_scalar: select a metric field under ' + path)
        selected[path] = value
    return {
        'schema': 'evidence_run_result_v1',
        'completion_reason': document.get('completion_reason'),
        'returncode': document.get('returncode'), 'timed_out': document.get('timed_out'),
        'failure_labels': document.get('failure_labels'),
        'native_clear': native.get('native_clear'),
        'native_certification_status': native.get('certification_status'),
        'role_identity': document.get('role_calibration_identity'),
        'scored_seconds': window.get('scored_duration_seconds', calibration.get('scored_seconds')),
        'window_complete': calibration.get('window_complete'),
        'cleanup_verified': document.get('cleanup_verified'),
        'controller_snapshot': {key: controller.get(key) for key in ('active', 'bots', 'lease_count')},
        'role_gate': gate(document.get('role_calibration_evaluation')),
        'reference_gate': {'conditions_compatible': reference.get('conditions_compatible'),
                           'reason_count': len(reference['reasons']) if isinstance(reference.get('reasons'), list) else None}
                          if reference is not None else None,
        'role_metrics': {k: v for k, v in metrics.items() if not isinstance(v, (dict, list))},
        'selected_metrics': selected,
        'missing_observations': [k for k in ('completion_reason', 'role_calibration_evaluation', 'role_calibration_identity', 'cleanup_verified')
                                 if document.get(k) is None],
        'interpretation': 'Reported outcomes only. Repair, actor, performance and parent acceptance remain separate decisions.',
    }
