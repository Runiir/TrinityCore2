-- Canonicalize the legacy control category to the runtime stun_cc taxonomy.
-- This is content migration after the immutable snapshot schema update; the
-- exact pre-Phase-4 profile hashes remain recorded in
-- experiments/configs/all_spec_phase4_previous_profile_hashes_v1.json.

UPDATE `bot_rotation_action`
SET `category` = 'stun_cc'
WHERE `enabled` = 1 AND `category` = 'control';
