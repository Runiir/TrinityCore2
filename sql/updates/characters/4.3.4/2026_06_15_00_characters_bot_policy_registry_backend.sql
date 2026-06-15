ALTER TABLE `bot_policy_models`
  ADD COLUMN IF NOT EXISTS `backend` varchar(64) NOT NULL DEFAULT '' AFTER `model_type`;

ALTER TABLE `bot_policy_evaluations`
  ADD COLUMN IF NOT EXISTS `backend` varchar(64) NOT NULL DEFAULT '' AFTER `model_type`;
